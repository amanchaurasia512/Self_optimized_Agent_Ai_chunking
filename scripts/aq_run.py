"""Answer-quality check (spec v1.2, AQ). Stage 'sample': 20% of each PDF's questions (rounded up, at least 1), seed 42;
tuning and held-out from the main certain span questions shared by both parsers, scanned from all MP-DocVQA questions.
Stage 'answer': for every sampled question and setup, hybrid retrieval and reading up to 1,250 tokens exactly as the
scorer does, then the fixed answer prompt to the research LLM (src/chunk/llm.py). Answers are appended as they arrive,
so a stopped run continues where it stopped. Prints counts only."""
import argparse
import asyncio
import json
import math
from collections import defaultdict
from functools import cache

import numpy as np
import pandas as pd

from scripts.p3_score import CHUNKS, EXTRACTED, GOLD, load_chunks
from src.chunk.llm import complete, llm_info, take_calls
from src.common.cost_logger import CostLogger
from src.common.manifest import PROJECT_ROOT, build_manifest, new_run_id, write_manifest
from src.eval.embed import EMBEDDER, load_cache, text_key
from src.eval.score import BM25, dense_ranking, hybrid_ranking, read_ranking

EXTERNAL = PROJECT_ROOT / "data" / "external"
OUTPUT = PROJECT_ROOT / "data" / "results" / "aq"
SAMPLE_FILE, ANSWERS_FILE = OUTPUT / "sample.csv", OUTPUT / "answers.jsonl"
SHARE, SEED, BUDGET, CONCURRENCY = 0.20, 42, 1250, 4
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


async def answer_all(jobs):
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def one(job):
        async with semaphore:
            return job, await complete(ANSWER_PROMPT.format(context=job["context"], question=job["question"]))

    with ANSWERS_FILE.open("a", encoding="utf-8") as output:
        for count, task in enumerate(asyncio.as_completed([one(job) for job in jobs]), start=1):
            job, answer = await task
            record = {key: job[key] for key in ["set", "doc_id", "question_id", "parser", "setting", "context_tokens"]}
            output.write(json.dumps({**record, "answer": answer}, ensure_ascii=False) + "\n")
            output.flush()
            if count % 100 == 0 or count == len(jobs):
                print(f"answered {count:,} of {len(jobs):,}", flush=True)


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--stage", required=True, choices=["sample", "answer"])
    args = arg_parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)

    if args.stage == "sample":
        sample = build_sample()
        sample.to_csv(SAMPLE_FILE, index=False)
        print(sample.groupby(["set", "source"]).agg(documents=("doc_id", "nunique"), questions=("question_id", "size")).to_string())
        print(f"\ntotal {len(sample)} questions | without a reference answer: {int(sample['reference'].isna().sum())} | saved {SAMPLE_FILE}")
        return

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
        asyncio.run(answer_all(jobs))
        calls = take_calls()
        stage.update(calls=len(calls), input_tokens=sum(call["input_tokens"] for call in calls),
                     output_tokens=sum(call["output_tokens"] for call in calls))
    stack = {"analysis": "aq_answer", "llm": llm_info(), "answer_prompt": ANSWER_PROMPT, "budget": BUDGET,
             "retriever": "hybrid", "digital_setups": DIGITAL, "scanned_setups": SCANNED, "concurrency": CONCURRENCY}
    manifest_path = write_manifest(build_manifest(new_run_id(6, "LOCAL"), "v1.2", stack, [SAMPLE_FILE], [ANSWERS_FILE],
                                                  logger.summary(), "laptop"))
    print(f"run record: {manifest_path}")


if __name__ == "__main__":
    main()