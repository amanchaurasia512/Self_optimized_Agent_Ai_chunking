"""RQ3 controls (spec v1.2, "RQ3 controls: budget sweep and random floor", with its amendment): do large chunks win
under fixed k only because they read more text? Tuning documents only, certain span-level main questions (QASPER
excluded), hybrid retrieval of scorer_v1 over the chunks and bge-m3 cache of P3-LOCAL-20261105-4.

Per question and setting: Recall@B (read_ranking, last chunk cut at B), Recall@k (top-k chunks, no budget, overlap
counted once, as p3_fixedk) with the tokens read, the same measures for a random chunk order (mean of 20
permutations, one numpy generator, seed 42, sorted processing order) and lift = measure - random floor. Analysis:
document means, then setting means, per parser; curves of recall against tokens read; per family and parser the paired
document bootstrap of (size 256 - size 1,024) at every cut, Holm over the 24 tested comparisons (Recall@1,250,
Recall@5, Lift@5); the crossover budget. There is no --final option: held-out documents are refused."""
import argparse
import json
import math
import re
import time
from collections import defaultdict
from datetime import datetime

import numpy as np
import pandas as pd

from scripts.p3_fixedk import TUNING_RUN, gold_share
from scripts.p3_score import CHUNKS, EXTRACTED, GOLD, OUTPUT, gold_questions, load_chunks
from scripts.p4_analyse import in_scope, resampled_means
from scripts.rq5_parser_compare import holm
from src.common.cost_logger import CostLogger
from src.common.manifest import PROJECT_ROOT, RUNS_DIR, build_manifest, new_run_id, write_manifest
from src.common.split import tuning_ids
from src.eval.embed import EMBEDDER, load_cache, text_key
from src.eval.score import BM25, SCORER, Gold, dense_ranking, hybrid_ranking, read_ranking
from src.eval.stats import LEVEL, RESAMPLES, SEED

FAMILIES = ("fixed_token", "recursive", "langchain_recursive", "method1_tree")
SIZES = (256, 384, 512, 640, 768, 896, 1024)
BUDGETS, KS, PERMUTATIONS = (250, 500, 750, 1250, 2000, 4000), (1, 3, 5, 10), 20
SMALL, LARGE = 256, 1024
TESTED = {("budget", 1250, "recall"), ("k", 5, "recall"), ("k", 5, "lift")}
PARSERS = ("docling", "pdfplumber")
SETTING = re.compile(r"^(fixed_token|recursive|langchain_recursive|method1_tree)_(?:size|T)(\d+)(?:_overlap0)?_noprefix$")
TEST_SETTINGS, TEST_DOCS = ("method1_tree_T256_noprefix", "method1_tree_T1024_noprefix"), 2


def setting_name(family, size):
    return f"method1_tree_T{size}_noprefix" if family == "method1_tree" else f"{family}_size{size}_overlap0_noprefix"


def design_settings():
    """The 28 size-swept settings of the design, kept only if p4_analyse.in_scope keeps them."""
    return in_scope(setting_name(family, size) for family in FAMILIES for size in SIZES)


def cut_scores(order, chunks, text, gold):
    """{(measure, cut): (recall, tokens read)} for every budget B and every k of one ranking."""
    scores = {}
    for budget in BUDGETS:
        taken, used = read_ranking(order, chunks, text, budget)
        scores[("budget", budget)] = (gold_share(taken, gold), used)
    for k in KS:
        taken, used = read_ranking(order[:k], chunks, text, math.inf)
        scores[("k", k)] = (gold_share(taken, gold), used)
    return scores


def score_question(order, chunks, text, gold, rng):
    """Hybrid scores and the random floor (mean over PERMUTATIONS random chunk orders) at every cut."""
    hybrid = cut_scores(order, chunks, text, gold)
    floors = [cut_scores(rng.permutation(len(chunks)), chunks, text, gold) for permutation in range(PERMUTATIONS)]
    return {cut: {"recall": recall, "tokens_read": used,
                  "random_recall": np.mean([floor[cut][0] for floor in floors]),
                  "random_tokens_read": np.mean([floor[cut][1] for floor in floors])}
            for cut, (recall, used) in hybrid.items()}


def score(parsers, settings, docs, cache, embedder=EMBEDDER):
    """One row per parser, setting, document, question and cut; dense vectors from the cache of the given embedder."""
    cached, vectors = load_cache(cache, embedder)
    rng, logger, rows = np.random.default_rng(SEED), CostLogger(), []
    for parser in parsers:
        questions = {question_id: question for question_id, question in gold_questions(parser, docs)[0].items()
                     if question["source"].lower() != "qasper"}
        by_doc = defaultdict(list)
        for question_id in sorted(questions):
            by_doc[questions[question_id]["doc_id"]].append((question_id, questions[question_id]))
        texts = {doc: json.loads((EXTRACTED / parser / f"{doc}.json").read_text(encoding="utf-8"))["text"] for doc in by_doc}
        nonspace = {doc: np.concatenate([[0], np.cumsum([not char.isspace() for char in text])]) for doc, text in texts.items()}
        print(f"{parser}: {len(questions)} main questions on {len(by_doc)} tuning documents | settings: {len(settings)}")
        for setting in settings:
            family, size = SETTING.match(setting).groups()
            with logger.stage(f"sweep:{parser}:{setting}"):
                for doc in sorted(by_doc):
                    chunks = load_chunks(CHUNKS / parser / setting / f"{doc}.json")
                    missing = [chunk for chunk in chunks if text_key(chunk["index_text"]) not in cached]
                    if missing:
                        raise KeyError(f"{len(missing)} chunks of {parser}/{setting}/{doc} are not in the {embedder['name']} cache")
                    bm25 = BM25([chunk["index_text"] for chunk in chunks])
                    chunk_vectors = vectors[[cached[text_key(chunk["index_text"])] for chunk in chunks]]
                    chunk_tokens = np.mean([chunk["tokens"] + chunk["prefix_tokens"] for chunk in chunks])
                    for question_id, question in by_doc[doc]:
                        gold = Gold(question["pieces"], nonspace[doc])
                        if not gold.total:
                            continue
                        order = hybrid_ranking(bm25.ranking(question["question"]),
                                               dense_ranking(vectors[cached[text_key(question["question"])]], chunk_vectors))
                        rows += [{"parser": parser, "setting": setting, "family": family, "size": int(size), "doc_id": doc,
                                  "question_id": question_id, "source": question["source"], "chunk_tokens": chunk_tokens,
                                  "measure": measure, "cut": cut, **values}
                                 for (measure, cut), values in score_question(order, chunks, texts[doc], gold, rng).items()]
    frame = pd.DataFrame(rows)
    frame["lift"] = frame["recall"] - frame["random_recall"]
    frame["chunk_exceeds_budget"] = (frame["measure"] == "budget") & (frame["chunk_tokens"] > frame["cut"])
    return frame, logger


def setting_means(frame):
    """Document means, then setting means, per parser, setting and cut."""
    keys = ["parser", "family", "size", "setting", "measure", "cut"]
    values = ["chunk_tokens", "recall", "random_recall", "lift", "tokens_read", "random_tokens_read"]
    return (frame.groupby(keys + ["doc_id"])[values].mean().groupby(keys).mean().reset_index()
            .assign(chunk_exceeds_budget=lambda table: (table["measure"] == "budget") & (table["chunk_tokens"] > table["cut"])))


def compare(frame):
    """Per family, parser, cut and value (recall, lift): paired document bootstrap of (size 256 - size 1,024); the
    same seed and sorted document order give every comparison the same resamples. Holm over the TESTED cuts only."""
    rows = []
    pair = frame[frame["size"].isin([SMALL, LARGE])]
    for (parser, family, measure, cut), group in pair.groupby(["parser", "family", "measure", "cut"]):
        for value in ("recall", "lift"):
            docs = group.groupby(["doc_id", "size"])[value].mean().unstack("size").dropna().sort_index()
            if not {SMALL, LARGE} <= set(docs.columns):
                continue
            difference = (docs[SMALL] - docs[LARGE]).to_numpy()
            means = resampled_means(difference[:, None], np.random.default_rng(SEED))[:, 0]
            low, high = np.quantile(means, [(1 - LEVEL) / 2, (1 + LEVEL) / 2])
            tested = (measure, cut, value) in TESTED
            rows.append({"parser": parser, "family": family, "measure": measure, "cut": cut, "value": value,
                         "documents": len(docs), "difference": difference.mean(), "low": low, "high": high,
                         "tested": tested, "p": min(1.0, 2 * min((means <= 0).mean(), (means >= 0).mean())) if tested else np.nan})
    table = pd.DataFrame(rows)
    table["holm_p"] = np.nan
    table.loc[table["tested"], "holm_p"] = holm(table.loc[table["tested"], "p"].to_numpy())
    return table


def crossovers(means):
    """Per family and parser, the smallest budget at which size 1,024 is no longer below size 256 (reported, not tested)."""
    budgets = means[(means["measure"] == "budget") & means["size"].isin([SMALL, LARGE])]
    table = budgets.pivot_table(index=["parser", "family", "cut"], columns="size", values="recall").reset_index()
    return pd.DataFrame([{"parser": parser, "family": family,
                          "crossover_budget": next((int(row["cut"]) for index, row in group.sort_values("cut").iterrows()
                                                    if row[LARGE] >= row[SMALL]), None)}
                         for (parser, family), group in table.groupby(["parser", "family"])]).astype({"crossover_budget": "Int64"})


def write_test_manifest(manifest, stamp):
    path = RUNS_DIR / "tests" / f"test_budget_sweep_{stamp}.json"
    if path.exists():
        raise FileExistsError(f"test record already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--test", action="store_true",
                            help=f"{TEST_DOCS} tuning documents, 2 settings per parser; writes only test_ files under runs/tests/ "
                                 "and data/results/tests/")
    arg_parser.add_argument("--cache", default=PROJECT_ROOT / "data" / "embeddings" / "bge-m3")
    arg_parser.add_argument("--machine", default="laptop")
    args = arg_parser.parse_args()

    tuning = tuning_ids()
    tuned_settings = (pd.read_csv(OUTPUT / f"{TUNING_RUN}.csv.gz", usecols=["parser", "setting"]).drop_duplicates()
                      .groupby("parser")["setting"].apply(set).to_dict())
    settings = list(TEST_SETTINGS) if args.test else design_settings()
    absent = {parser: sorted(set(settings) - tuned_settings[parser]) for parser in PARSERS if set(settings) - tuned_settings[parser]}
    if absent:
        raise ValueError(f"settings not in {TUNING_RUN}: {absent}")
    docs = tuning
    if args.test:
        shared = set.intersection(*({question["doc_id"] for question in gold_questions(parser, tuning)[0].values()
                                     if question["source"].lower() != "qasper"} for parser in PARSERS))
        docs = set(sorted(shared)[:TEST_DOCS])
    if docs - tuning:
        raise PermissionError(f"only tuning documents may be used: {sorted(docs - tuning)}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder, prefix = ((PROJECT_ROOT / "data" / "results" / "tests", f"test_budget_sweep_{stamp}") if args.test
                      else (OUTPUT, "budget_sweep_tuning"))
    paths = {name: folder / f"{prefix}{suffix}" for name, suffix in
             (("rows", ".csv"), ("means", "_means.csv"), ("tests", "_tests.csv"), ("crossover", "_crossover.csv"))}
    existing = [path for path in paths.values() if path.exists()]
    if existing:
        raise FileExistsError(f"outputs already exist, never overwritten: {existing}")

    start = time.perf_counter()
    frame, logger = score(PARSERS, settings, docs, args.cache)
    with logger.stage("analyse"):
        means, tests = setting_means(frame), compare(frame)
        crossing = crossovers(means)
    folder.mkdir(parents=True, exist_ok=True)
    for name, table in (("rows", frame), ("means", means), ("tests", tests), ("crossover", crossing)):
        table.to_csv(paths[name], index=False)
    seconds = time.perf_counter() - start

    stack = {"analysis": "rq3_budget_sweep", "spec_note": "RQ3 controls: budget sweep and random floor (2026-11-18), amended",
             "scorer": SCORER, "embedder": EMBEDDER, "retriever": "hybrid", "settings_from": TUNING_RUN,
             "parsers": list(PARSERS), "settings": settings, "documents": sorted(docs), "budgets": list(BUDGETS),
             "ks": list(KS), "permutations": PERMUTATIONS, "seed": SEED, "resamples": RESAMPLES, "level": LEVEL,
             "holm_family": sorted(f"{measure}{cut}_{value}" for measure, cut, value in TESTED),
             "questions": "certain span, main (QASPER excluded)", "test": args.test}
    inputs = sorted(GOLD.glob("spans_*.jsonl")) + [OUTPUT / f"{TUNING_RUN}.csv.gz"]
    if args.test:
        manifest = build_manifest(f"test_budget_sweep_{stamp}", "v1.2", stack, inputs, list(paths.values()), logger.summary(), args.machine)
        manifest_path = write_test_manifest(manifest, stamp)
    else:
        run_id = new_run_id(3, "SWEEP")
        manifest_path = write_manifest(build_manifest(run_id, "v1.2", stack, inputs, list(paths.values()), logger.summary(), args.machine))

    pd.set_option("display.width", 240, "display.max_rows", 300, "display.max_columns", 40)
    for parser, part in means.groupby("parser"):
        part = part.assign(column=[f"B{cut}" if measure == "budget" else f"k{cut}" for measure, cut in zip(part["measure"], part["cut"])])
        order = [f"B{cut}" for cut in BUDGETS] + [f"k{cut}" for cut in KS]
        for value in ("recall", "lift", "tokens_read"):
            table = part.pivot_table(index=["family", "size"], columns="column", values=value)[order]
            print(f"\n=== {parser}: {value} (document means, then setting means)\n{table.round(3).to_string()}")
        flagged = sorted(set(zip(part.loc[part["chunk_exceeds_budget"], "setting"], part.loc[part["chunk_exceeds_budget"], "cut"])))
        print(f"flagged (mean chunk tokens > B; kept): {flagged or 'none'}")
    print(f"\n=== size 256 - size 1,024 (paired document bootstrap, {RESAMPLES} resamples; Holm over the "
          f"{int(tests['tested'].sum())} tested comparisons)\n{tests.round(3).to_string(index=False)}"
          f"\n\n=== crossover: smallest B where size 1,024 is no longer below 256 (reported, not tested)\n{crossing.to_string(index=False)}"
          f"\n\nrows {len(frame):,} | {seconds:.0f} s | saved {folder}/{prefix}*\nrecord: {manifest_path}")


if __name__ == "__main__":
    main()
