"""P3 fixed-k re-scoring (spec v1.2, diagnostic): the tuning run's settings re-ranked with scorer_v1's hybrid retrieval
and scored by number of chunks read instead of tokens: Recall@5, Recall@10 (no token budget, overlap counted once),
Hit@1, MRR, plus Recall@4,000 tokens. Tuning documents only, main questions (QASPER excluded), document means then
setting means; one table per parser sorted by measured chunk size, and where the best size falls under each measure."""
import argparse
import math
import re
from collections import defaultdict

import json
import numpy as np
import pandas as pd

from scripts.p3_score import CHUNKS, EXTRACTED, GOLD, OUTPUT, gold_questions, load_chunks
from src.common.cost_logger import CostLogger
from src.common.manifest import build_manifest, new_run_id, write_manifest
from src.common.split import tuning_ids
from src.eval.embed import EMBEDDER, load_cache, text_key
from src.eval.score import BM25, SCORER, Gold, dense_ranking, hybrid_ranking, read_ranking, rank_metrics

TUNING_RUN = "P3-LOCAL-20261105-4"
KS, BUDGET = (5, 10), 4000
MEASURES = ["recall5", "recall10", "hit1", "mrr", f"recall{BUDGET}"]
FAMILY = re.compile(r"^(fixed_token|langchain_recursive|recursive|method1_tree)_(?:size|T)\d+(?:_overlap0)?_noprefix$")


def gold_share(taken, gold):
    return sum(gold.inside(start, end) for position, start, end in taken) / gold.total


def score_question(order, chunks, text, gold, chunk_gold):
    """Fixed-k recall (top-k chunks, no budget), Hit@1, MRR and Recall at the token budget for one ranking."""
    scores = {f"recall{k}": gold_share(read_ranking(order[:k], chunks, text, math.inf)[0], gold) for k in KS}
    return {**scores, "hit1": chunk_gold[order[0]] > 0, "mrr": rank_metrics(order, chunks, chunk_gold, text)["mrr"],
            f"recall{BUDGET}": gold_share(read_ranking(order, chunks, text, BUDGET)[0], gold)}


def best_sizes(table):
    """Best setting under each measure, overall and within each size-swept family (no prefix, no overlap)."""
    families = table.assign(family=[(FAMILY.match(setting) or [None, None])[1] for setting in table.index])
    groups = [("all settings", families)] + list(families.dropna(subset=["family"]).groupby("family"))
    rows = [{"scope": scope, "measure": measure, "best setting": group[measure].idxmax(),
             "chunk tokens": round(group.loc[group[measure].idxmax(), "chunk_tokens"]), "score": round(group[measure].max(), 3)}
            for scope, group in groups for measure in MEASURES]
    return pd.DataFrame(rows).pivot(index="scope", columns="measure", values="chunk tokens")[MEASURES], pd.DataFrame(rows)


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--parsers", nargs="+", default=["docling", "pdfplumber"])
    arg_parser.add_argument("--cache", default=CHUNKS.parent / "embeddings" / "bge-m3")
    arg_parser.add_argument("--machine", default="laptop")
    args = arg_parser.parse_args()

    docs = tuning_ids()
    settings = (pd.read_csv(OUTPUT / f"{TUNING_RUN}.csv.gz", usecols=["parser", "setting"]).drop_duplicates()
                .groupby("parser")["setting"].apply(set).to_dict())
    cached, vectors = load_cache(args.cache)
    logger, rows = CostLogger(), []
    for parser in args.parsers:
        questions = {question_id: question for question_id, question in gold_questions(parser, docs)[0].items()
                     if question["source"].lower() != "qasper"}
        by_doc = defaultdict(list)
        for question_id, question in questions.items():
            by_doc[question["doc_id"]].append((question_id, question))
        texts = {doc: json.loads((EXTRACTED / parser / f"{doc}.json").read_text(encoding="utf-8"))["text"] for doc in by_doc}
        nonspace = {doc: np.concatenate([[0], np.cumsum([not char.isspace() for char in text])]) for doc, text in texts.items()}
        folders = sorted(CHUNKS / parser / setting for setting in settings[parser])
        print(f"{parser}: {len(questions)} main questions on {len(by_doc)} tuning documents | settings: {len(folders)}")
        for folder in folders:
            with logger.stage(f"fixedk:{parser}:{folder.name}"):
                for doc, doc_questions in by_doc.items():
                    chunks = load_chunks(folder / f"{doc}.json")
                    bm25 = BM25([chunk["index_text"] for chunk in chunks])
                    chunk_vectors = vectors[[cached[text_key(chunk["index_text"])] for chunk in chunks]]
                    chunk_tokens = np.mean([chunk["tokens"] + chunk["prefix_tokens"] for chunk in chunks])
                    for question_id, question in doc_questions:
                        gold = Gold(question["pieces"], nonspace[doc])
                        if not gold.total:
                            continue
                        chunk_gold = [gold.inside(chunk["start"], chunk["end"]) for chunk in chunks]
                        order = hybrid_ranking(bm25.ranking(question["question"]),
                                               dense_ranking(vectors[cached[text_key(question["question"])]], chunk_vectors))
                        rows.append({"parser": parser, "setting": folder.name, "doc_id": doc, "question_id": question_id,
                                     "source": question["source"], "chunk_tokens": chunk_tokens,
                                     **score_question(order, chunks, texts[doc], gold, chunk_gold)})

    frame = pd.DataFrame(rows)
    output = OUTPUT / "fixedk_tuning.csv"
    frame.to_csv(output, index=False)
    run_id = new_run_id(3, "FIXEDK")
    stack = {"scorer": SCORER, "embedder": EMBEDDER, "retriever": "hybrid", "ks": KS, "budget": BUDGET,
             "settings_from": TUNING_RUN, "parsers": args.parsers, "questions": "certain span, main (QASPER excluded)"}
    manifest_path = write_manifest(build_manifest(run_id, "v1.2", stack, sorted(GOLD.glob("spans_*.jsonl")), [output],
                                                  logger.summary(), args.machine))

    pd.set_option("display.width", 220, "display.max_rows", 200)
    for parser, part in frame.groupby("parser"):
        table = (part.groupby(["setting", "doc_id"])[["chunk_tokens"] + MEASURES].mean().astype(float)
                 .groupby("setting").mean().sort_values("chunk_tokens"))
        sizes, details = best_sizes(table)
        print(f"\n=== {parser}: {part['question_id'].nunique()} questions | {part['doc_id'].nunique()} documents | "
              f"document means, then setting means; sorted by mean chunk tokens\n{table.round(3).to_string()}\n"
              f"\nMean chunk tokens of the best setting under each measure (overall, and within each size-swept family)\n"
              f"{sizes.to_string()}\n\nBest setting overall per measure\n"
              f"{details[details['scope'] == 'all settings'].drop(columns='scope').to_string(index=False)}")
    print(f"\nrows {len(frame):,} | saved {output}\nrun {run_id} | manifest: {manifest_path}")


if __name__ == "__main__":
    main()
