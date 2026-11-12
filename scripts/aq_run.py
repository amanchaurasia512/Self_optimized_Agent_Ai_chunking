"""Answer-quality check (spec v1.2, AQ).
Stage 'sample': 20% of each PDF's questions (rounded up, at least 1), seed 42; tuning and held-out from the main certain
span questions shared by both parsers, scanned from all MP-DocVQA questions.
Stage 'answer': for every sampled question and setup, hybrid retrieval and reading up to 1,250 tokens exactly as the
scorer does, then the fixed answer prompt to the research LLM (src/chunk/llm.py). Answers are appended as they arrive,
so a stopped run continues where it stopped.
Stage 'f1': token F1 and 'gold contained' of every answer against its reference (no API).
Stage 'judge-check': 40 tuning cases for blind human labelling; 'judge-check-score': the judge on those cases, with
agreement, Cohen's kappa and the 80% pass mark. Prints counts only."""
import argparse
import asyncio
import json
import math
import re
import string
import time
from collections import Counter, defaultdict
from functools import cache

import numpy as np
import pandas as pd
from google.genai import errors

from scripts.p3_score import CHUNKS, EXTRACTED, GOLD, load_chunks
from scripts.p4_analyse import resampled_means
from scripts.rq5_parser_compare import holm
from src.eval.stats import LEVEL
from src.chunk.llm import complete, llm_info, take_calls
from src.common.cost_logger import CostLogger
from src.common.manifest import PROJECT_ROOT, build_manifest, new_run_id, write_manifest
from src.eval.embed import EMBEDDER, load_cache, text_key
from src.eval.score import BM25, dense_ranking, hybrid_ranking, read_ranking


EXTERNAL = PROJECT_ROOT / "data" / "external"
OUTPUT = PROJECT_ROOT / "data" / "results" / "aq"
SAMPLE_FILE, ANSWERS_FILE, F1_FILE = OUTPUT / "sample.csv", OUTPUT / "answers.jsonl", OUTPUT / "answers_f1.csv"
JUDGE_JOBS, JUDGEMENTS = OUTPUT / "judge_jobs.jsonl", OUTPUT / "judgements.jsonl"
CHECK_FILE, CHECK_KEYS, CHECK_SCORED = OUTPUT / "judge_check.csv", OUTPUT / "judge_check_keys.csv", OUTPUT / "judge_check_scored.csv"
SHARE, SEED, BUDGET, CHECK_CASES = 0.20, 42, 1250, 40
INTERVAL = 60 / 14  # free tier allows 15 requests per minute per model; one start every 4.3 s stays under it
HELD_OUT = {"held_out", "held_out_c", "held_out_ood"}
DIGITAL = [("docling", setting) for setting in [
    "method1_tree_T256_noprefix", "method1_tree_T384_noprefix", "langchain_recursive_size256_overlap0_noprefix",
    "langchain_recursive_size512_overlap0_noprefix", "recursive_size512_overlap0_noprefix",
    "fixed_token_size1024_overlap0_noprefix", "langchain_default_noprefix"]]
SCANNED = [(parser, setting) for parser in ["docling", "docling_ocr_tesseract"] for setting in [
    "method1_tree_T256_noprefix", "method1_tree_T384_noprefix", "recursive_size256_overlap0_noprefix",
    "langchain_recursive_size256_overlap0_noprefix", "fixed_token_size256_overlap0_noprefix"]]
ANSWER_PROMPT = ("Answer the question using only the context below, which comes from one document. "
                 "If the context does not contain the answer, reply exactly: not found\n\n"
                 "Context:\n{context}\n\nQuestion: {question}\nAnswer (briefly):")
JUDGE_PROMPT = ("You are grading an answer against a reference answer to the same question.\n"
                "Score 1 if the answer contains all the key facts of the reference (extra wording or a different phrasing is fine).\n"
                "Score 0.5 if it contains some but not all of the key facts, or is partly wrong.\n"
                "Score 0 if it is wrong, contradicts the reference, or says the answer was not found.\n"
                "If the reference lists alternatives separated by ' | ', matching any one of them counts as all key facts.\n"
                "Reply with only the number: 1, 0.5 or 0.\n\n"
                "Question: {question}\nReference answer: {reference}\nAnswer to grade: {answer}\nScore:")
ARTICLES = {"a", "an", "the"}
RECALL_RUNS = {"tuning": "P3-LOCAL-20261105-4", "held_out": "P3-FINAL-20261106-1", "scanned": "P3-RQ5S-20261111-1"}
RESULTS = PROJECT_ROOT / "data" / "results"


def export_judge_jobs():
    """Every answer with its question and reference, plus the ready-made judge prompt, for the Kaggle judge."""
    rows = answered()
    with JUDGE_JOBS.open("w", encoding="utf-8") as output:
        for row in rows.to_dict("records"):
            record = {key: row[key] for key in ["set", "doc_id", "question_id", "parser", "setting"]}
            output.write(json.dumps({**record, "prompt": judge_prompt(row)}, ensure_ascii=False) + "\n")
    print(f"{len(rows):,} judge jobs written to {JUDGE_JOBS}")

def gold_rows(parser):
    return [json.loads(line) for line in (GOLD / f"spans_{parser}.jsonl").read_text(encoding="utf-8").splitlines()]


def certain_main(parser):
    """(doc_id, question_id) -> (question, source) for certain span questions outside QASPER."""
    return {(row["doc_id"], str(row["question_id"])): (row["question"], row["source"]) for row in gold_rows(parser)
            if str(row["certain"]) == "True" and row["kind"] == "span" and row["method"] != "page" and row["source"] != "QASPER"}


def scanned_items():
    return json.loads((EXTERNAL / "mpdocvqa" / "selected_questions.json").read_text(encoding="utf-8"))


def references():
    """question_id -> each source's own reference answer (MP-DocVQA: accepted alternatives joined by ' | ')."""
    cuad = defaultdict(set)
    for row in gold_rows("docling"):
        if row["source"] == "CUAD" and row["gold"]:
            cuad[str(row["question_id"])].add(row["gold"])
    reference = {key: "; ".join(sorted(values)) for key, values in cuad.items()}
    for path in (EXTERNAL / "indian_regulatory").glob("*_GOLDEN_200.json"):
        reference.update({str(item["id"]): str(item["answer"]) for item in json.loads(path.read_text(encoding="utf-8"))})
    for item in json.loads((EXTERNAL / "ohr_bench" / "qas_v2.json").read_text(encoding="utf-8")):
        values = item["answers"] if isinstance(item["answers"], list) else [item["answers"]]
        reference[str(item["ID"])] = "; ".join(str(value) for value in values)
    for record in map(json.loads, (EXTERNAL / "financebench" / "financebench_merged.jsonl").read_text(encoding="utf-8").splitlines()):
        reference[str(record["financebench_id"])] = str(record["answer"])
    reference.update({str(item["question_id"]): " | ".join(item["answers"]) for item in scanned_items()})
    return reference


def build_sample():
    split = pd.read_csv(PROJECT_ROOT / "pdfs" / "split.csv").set_index("doc_id")["split"].to_dict()
    plumber = certain_main("pdfplumber")
    pools = {name: defaultdict(dict) for name in ["tuning", "held_out", "scanned"]}
    for key, value in certain_main("docling").items():
        name = "tuning" if split.get(key[0]) == "tuning" else "held_out" if split.get(key[0]) in HELD_OUT else None
        if name and key in plumber:
            pools[name][key[0]][key[1]] = value
    for item in scanned_items():
        pools["scanned"][item["doc_id"]][str(item["question_id"])] = (item["question"], "MP-DocVQA")
    reference, rng, rows = references(), np.random.default_rng(SEED), []
    for name, docs in pools.items():
        for doc in sorted(docs):
            ids = sorted(docs[doc])
            chosen = sorted(rng.choice(ids, size=max(1, math.ceil(SHARE * len(ids))), replace=False))
            rows += [{"set": name, "doc_id": doc, "question_id": question_id, "source": docs[doc][question_id][1],
                      "question": docs[doc][question_id][0], "reference": reference.get(question_id)} for question_id in chosen]
    return pd.DataFrame(rows)


@cache
def encoder():
    import torch
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMBEDDER["name"], revision=EMBEDDER["revision"], device="cpu", model_kwargs={"dtype": torch.float32})
    model.max_seq_length = EMBEDDER["max_length"]
    return model


def question_vector(question, cached, vectors):
    key = text_key(question)
    return vectors[cached[key]] if key in cached else encoder().encode([question], normalize_embeddings=True)[0]


def contexts(sample, setups, cached, vectors):
    """(parser, setting, doc_id, question_id) -> (context, tokens read), retrieved and read exactly as the scorer does."""
    found = {}
    for parser, setting in setups:
        for doc, group in sample.groupby("doc_id"):
            text = json.loads((EXTRACTED / parser / f"{doc}.json").read_text(encoding="utf-8"))["text"]
            chunks = load_chunks(CHUNKS / parser / setting / f"{doc}.json")
            bm25 = BM25([chunk["index_text"] for chunk in chunks])
            chunk_vectors = vectors[[cached[text_key(chunk["index_text"])] for chunk in chunks]]
            for row in group.itertuples(index=False):
                order = hybrid_ranking(bm25.ranking(row.question), dense_ranking(question_vector(row.question, cached, vectors), chunk_vectors))
                taken, used = read_ranking(order, chunks, text, BUDGET)
                found[(parser, setting, doc, row.question_id)] = ("\n\n".join(text[start:end] for position, start, end in taken), used)
    return found


async def paced(items, make_prompt, output_path, record_keys, result_key, parse=None, what="items"):
    """Send one request per item, one start every INTERVAL seconds, appending each result to output_path as it arrives.
    A daily-quota error stops cleanly; everything saved so far is kept."""
    gate, last_start = asyncio.Lock(), 0.0

    async def one(item):
        nonlocal last_start
        async with gate:
            await asyncio.sleep(max(0.0, last_start + INTERVAL - time.monotonic()))
            last_start = time.monotonic()
        return item, await complete(make_prompt(item))

    tasks = [asyncio.ensure_future(one(item)) for item in items]
    with output_path.open("a", encoding="utf-8") as output:
        for count, task in enumerate(asyncio.as_completed(tasks), start=1):
            try:
                item, reply = await task
            except errors.APIError as error:
                if error.code == 429 and "per day" in str(error):
                    print(f"daily free-tier limit reached after {count - 1:,} new {what}; run the same command again tomorrow")
                    for pending in tasks:
                        pending.cancel()
                    return
                raise
            record = {key: item[key] for key in record_keys if key in item}
            extra = {"score": parse(reply)} if parse else {}
            output.write(json.dumps({**record, result_key: reply, **extra}, ensure_ascii=False) + "\n")
            output.flush()
            if count % 100 == 0 or count == len(items):
                print(f"{what} {count:,} of {len(items):,}", flush=True)


def answered():
    sample = pd.read_csv(SAMPLE_FILE, dtype=str)
    answers = pd.DataFrame([json.loads(line) for line in ANSWERS_FILE.read_text(encoding="utf-8").splitlines()])
    return answers.merge(sample[["question_id", "question", "reference"]], on="question_id")


def normal_tokens(text):
    """Lower-case word tokens without punctuation and articles (SQuAD-style normalisation)."""
    cleaned = str(text).lower().translate(str.maketrans("", "", string.punctuation))
    return [token for token in cleaned.split() if token not in ARTICLES]


def token_f1(answer, reference):
    """Token F1 of the answer against the reference; with ' | ' alternatives, the best alternative counts."""
    best = 0.0
    for alternative in str(reference).split(" | "):
        predicted, expected = normal_tokens(answer), normal_tokens(alternative)
        common = sum((Counter(predicted) & Counter(expected)).values())
        if common:
            precision, recall = common / len(predicted), common / len(expected)
            best = max(best, 2 * precision * recall / (precision + recall))
    return best


def contained(answer, reference):
    """True if any ' | ' alternative of the reference appears as a whole token sequence inside the answer."""
    predicted = normal_tokens(answer)
    return any(expected and any(predicted[start:start + len(expected)] == expected for start in range(len(predicted) - len(expected) + 1))
               for expected in map(normal_tokens, str(reference).split(" | ")))

def score_f1():
    rows = answered()
    rows["f1"] = [token_f1(answer, reference) for answer, reference in zip(rows["answer"], rows["reference"])]
    rows["contained"] = [contained(answer, reference) for answer, reference in zip(rows["answer"], rows["reference"])]
    rows["not_found"] = rows["answer"].str.strip().str.lower().str.startswith("not found")
    rows.drop(columns=["question", "reference", "answer"]).to_csv(F1_FILE, index=False)
    per_doc = rows.groupby(["set", "parser", "setting", "doc_id"])[["f1", "contained", "not_found"]].mean()
    table = per_doc.groupby(["set", "parser", "setting"]).mean().round(3)
    pd.set_option("display.width", 200)
    print(f"Answer scores, document means then setup means\n{table.to_string()}\n\nsaved {F1_FILE}")


def analyse_answers():
    """Per set and setup: answer F1, contained, not-found, the secondary judge score and Recall@1,250 on the same questions
    (document means first); Spearman rank correlation between setups' answer scores and Recall, on the answers that have a
    Recall score; paired document bootstrap of the best F1 setup against every other setup, with a two-sided bootstrap
    p-value, Holm-corrected over the comparisons of each set."""
    keys = ["parser", "setting", "doc_id", "question_id"]
    answers = pd.read_csv(F1_FILE, dtype={"question_id": str})
    judged = pd.DataFrame([json.loads(line) for line in JUDGEMENTS.read_text(encoding="utf-8").splitlines()]).rename(columns={"score": "judge_secondary"})
    answers = answers.merge(judged[keys + ["judge_secondary"]], on=keys, how="left")
    pd.set_option("display.width", 220)
    rng = np.random.default_rng(SEED)
    for name, run in RECALL_RUNS.items():
        part = answers[answers["set"] == name]
        recall = pd.read_csv(RESULTS / "p3" / f"{run}.csv.gz", usecols=keys + ["retriever", "budget", "recall"], dtype={"question_id": str})
        recall = recall[(recall["retriever"] == "hybrid") & (recall["budget"] == BUDGET)]
        merged = part.merge(recall[keys + ["recall"]], on=keys, how="left")
        measures = ["f1", "contained", "not_found", "judge_secondary", "recall"]
        docs = merged.groupby(["parser", "setting", "doc_id"])[measures].mean()
        setups = docs.groupby(["parser", "setting"]).mean()
        # Spearman on the answers that have a Recall score only, so both columns cover the same questions
        scored = merged[merged["recall"].notna()]
        scored_setups = scored.groupby(["parser", "setting", "doc_id"])[measures].mean().groupby(["parser", "setting"]).mean()
        spearman = scored_setups[["f1", "contained", "judge_secondary", "recall"]].corr(method="spearman").loc["recall"]
        print(f"\n=== {name}: {part['question_id'].nunique()} questions | {docs.index.get_level_values('doc_id').nunique()} documents | "
              f"answers with a Recall score: {len(scored):,} of {len(merged):,}\n"
              f"All questions (recall: on the answers that have one)\n{setups.round(3).to_string()}\n"
              f"Spearman with Recall@{BUDGET} across setups, on the {len(scored):,} answers with a Recall score "
              f"({scored['question_id'].nunique()} questions): F1 {spearman['f1']:.2f} | contained {spearman['contained']:.2f} | "
              f"judge {spearman['judge_secondary']:.2f}")
        best = setups["f1"].idxmax()
        by_doc = docs["f1"].unstack(["parser", "setting"])
        rows = []
        for rival in [setup for setup in setups.index if setup != best]:
            pair = by_doc[[best, rival]].dropna()
            difference = pair[best] - pair[rival]
            means = resampled_means(difference.to_numpy()[:, None], rng)[:, 0]
            low, high = np.quantile(means, [(1 - LEVEL) / 2, (1 + LEVEL) / 2])
            rows.append({"parser": rival[0], "setting": rival[1], "documents": len(pair), "difference": difference.mean(),
                         "low": low, "high": high, "p": min(1.0, 2 * min((means <= 0).mean(), (means >= 0).mean()))})
        comparisons = pd.DataFrame(rows)
        comparisons["holm_p"] = holm(comparisons["p"].to_numpy())
        print(f"\nF1, best setup {best[1]} ({best[0]}) minus each other setup, paired document bootstrap, "
              f"{LEVEL:.0%} CI, two-sided p, Holm over {len(comparisons)} comparisons\n"
              f"{comparisons.set_index(['parser', 'setting']).round(3).to_string()}")
        setups.round(4).to_csv(OUTPUT / f"analysis_{name}.csv")
        comparisons.round(4).to_csv(OUTPUT / f"analysis_{name}_vs_best.csv", index=False)
    print(f"\nsaved analysis_<set>.csv in {OUTPUT}")

def parse_score(text):
    match = re.search(r"(?<![\d.])(1|0\.5|0)(?![\d.])", text.strip())
    return float(match.group(1)) if match else None


def cohen_kappa(first, second):
    """Cohen's kappa for two label lists (categories = the labels seen)."""
    labels = sorted(set(first) | set(second))
    observed = sum(one == two for one, two in zip(first, second)) / len(first)
    expected = sum((first.count(label) / len(first)) * (second.count(label) / len(second)) for label in labels)
    return (observed - expected) / (1 - expected) if expected < 1 else 1.0


def draw_check_cases():
    """40 tuning cases, seed 42, for blind human labelling: the human sees question, reference and answer only."""
    cases = answered().query("set == 'tuning'").sample(CHECK_CASES, random_state=SEED).reset_index(drop=True)
    cases.index.name = "case"
    cases[["parser", "setting", "doc_id", "question_id"]].to_csv(CHECK_KEYS)
    cases[["question", "reference", "answer"]].assign(human="").to_csv(CHECK_FILE)
    print(f"{len(cases)} cases written to {CHECK_FILE}\nFill the 'human' column with 1, 0.5 or 0 for every case, save, then run --stage judge-check-score")

def label_cases():
    """Terminal labelling of the check cases: shows question, reference and answer; saves after every label; resumable."""
    cases = pd.read_csv(CHECK_FILE, index_col="case")
    pending = cases[cases["human"].isna()]
    print(f"{len(pending)} of {len(cases)} cases to label | type 1, 0.5 or 0 (s = skip, q = quit)")
    for case, row in pending.iterrows():
        print(f"\n--- case {case} ---\nQ:   {row['question']}\nREF: {row['reference']}\nANS: {row['answer']}")
        while True:
            label = input("human [1 / 0.5 / 0 / s / q]: ").strip().lower()
            if label in {"1", "0.5", "0", "s", "q"}:
                break
        if label == "q":
            break
        if label != "s":
            cases.loc[case, "human"] = float(label)
            cases.to_csv(CHECK_FILE)
    print(f"\nlabelled {int(cases['human'].notna().sum())} of {len(cases)} | saved {CHECK_FILE}")

def judge_prompt(row):
    return JUDGE_PROMPT.format(question=row["question"], reference=row["reference"], answer=row["answer"])


def score_check():
    """Compare the judge's scores on the 40 check cases with the human labels: agreement, Cohen's kappa, confusion table."""
    keys = ["parser", "setting", "doc_id", "question_id"]
    cases = pd.read_csv(CHECK_FILE, index_col="case").join(pd.read_csv(CHECK_KEYS, index_col="case"))
    assert cases["human"].notna().all(), "every case needs a human label first"
    judged = pd.DataFrame([json.loads(line) for line in JUDGEMENTS.read_text(encoding="utf-8").splitlines()])
    compared = cases.reset_index().merge(judged, on=keys)
    assert len(compared) == len(cases), f"only {len(compared)} of {len(cases)} check cases found in {JUDGEMENTS}"
    human, judge = compared["human"].astype(float).tolist(), compared["score"].astype(float).tolist()
    agreed = sum(one == two for one, two in zip(human, judge))
    print(f"agreement {agreed / len(human):.0%} ({agreed} of {len(human)}) | Cohen's kappa {cohen_kappa(human, judge):.2f} | "
          f"unparsed judge replies: {int(compared['score'].isna().sum())}")
    print(pd.crosstab(compared["human"].astype(float), compared["score"].astype(float), rownames=["human"], colnames=["judge"]).to_string())
    print("\nPASS: judge may be used" if agreed / len(human) >= 0.80 else "\nFAIL: revise the guide once (spec) and re-check on 40 new cases")


def run_answers():
    sample = pd.read_csv(SAMPLE_FILE, dtype=str)
    done = {(row["parser"], row["setting"], row["doc_id"], row["question_id"])
            for row in map(json.loads, ANSWERS_FILE.read_text(encoding="utf-8").splitlines())} if ANSWERS_FILE.exists() else set()
    cached, vectors = load_cache(PROJECT_ROOT / "data" / "embeddings" / "bge-m3")
    logger, jobs = CostLogger(), []
    with logger.stage("retrieve"):
        for part, setups in ((sample[sample["set"] != "scanned"], DIGITAL), (sample[sample["set"] == "scanned"], SCANNED)):
            questions = part.set_index(["doc_id", "question_id"])
            for (parser, setting, doc, question_id), (context, used) in contexts(part, setups, cached, vectors).items():
                if (parser, setting, doc, question_id) not in done:
                    row = questions.loc[(doc, question_id)]
                    jobs.append({"set": row["set"], "doc_id": doc, "question_id": question_id, "parser": parser, "setting": setting,
                                 "context_tokens": used, "context": context, "question": row["question"]})
    print(f"answers already saved {len(done):,} | to ask now {len(jobs):,}", flush=True)
    with logger.stage("answer") as stage:
        asyncio.run(paced(jobs, lambda job: ANSWER_PROMPT.format(context=job["context"], question=job["question"]), ANSWERS_FILE,
                          ["set", "doc_id", "question_id", "parser", "setting", "context_tokens"], "answer", what="answered"))
        calls = take_calls()
        stage.update(calls=len(calls), input_tokens=sum(call["input_tokens"] for call in calls),
                     output_tokens=sum(call["output_tokens"] for call in calls))
    stack = {"analysis": "aq_answer", "llm": llm_info(), "answer_prompt": ANSWER_PROMPT, "budget": BUDGET,
             "retriever": "hybrid", "digital_setups": DIGITAL, "scanned_setups": SCANNED, "seconds_between_requests": INTERVAL}
    manifest_path = write_manifest(build_manifest(new_run_id(6, "LOCAL"), "v1.2", stack, [SAMPLE_FILE], [ANSWERS_FILE],
                                                  logger.summary(), "laptop"))
    print(f"run record: {manifest_path}")


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--stage", required=True,
                            choices=["sample", "answer", "f1", "judge-check", "label", "judge-export", "judge-check-score", "analyse"])
    args = arg_parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if args.stage == "sample":
        sample = build_sample()
        sample.to_csv(SAMPLE_FILE, index=False)
        print(sample.groupby(["set", "source"]).agg(documents=("doc_id", "nunique"), questions=("question_id", "size")).to_string())
        print(f"\ntotal {len(sample)} questions | without a reference answer: {int(sample['reference'].isna().sum())} | saved {SAMPLE_FILE}")
    elif args.stage == "answer":
        run_answers()
    elif args.stage == "f1":
        score_f1()
    elif args.stage == "judge-check":
        draw_check_cases()
    elif args.stage == "label":
        label_cases()
    elif args.stage == "judge-export":
        export_judge_jobs()
    elif args.stage == "judge-check-score":
        score_check()
    elif args.stage == "analyse":
        analyse_answers()


if __name__ == "__main__":
    main()