"""P3 scorer v1 runner (spec v1.2): every discovered chunk setting x parser x tuning document x certain question x
retriever (BM25, dense, hybrid) x budget (750, 1,250, 2,000). Writes one row per question, retriever and budget to
data/results/p3/<run id>.csv.gz, a run record, and a short summary: Recall@1,250, document means then setting means,
main questions (QASPER separately in the file)."""
import argparse
import json
from collections import defaultdict

import numpy as np
import pandas as pd

from src.common.cost_logger import CostLogger
from src.common.manifest import PROJECT_ROOT, build_manifest, new_run_id, write_manifest
from src.common.split import tuning_ids
from src.eval.embed import EMBEDDER, load_cache, text_key
from src.eval.score import BM25, SCORER, Gold, dense_ranking, hybrid_ranking, measure, rank_metrics

CHUNKS, EXTRACTED, GOLD = (PROJECT_ROOT / "data" / name for name in ("chunks", "extracted", "gold"))
OUTPUT = PROJECT_ROOT / "data" / "results" / "p3"


def gold_questions(parser, docs):
    """Certain span-level questions with their pieces (D3: page-level gold left out and counted)."""
    questions, page_level = defaultdict(lambda: {"pieces": []}), 0
    for line in (GOLD / f"spans_{parser}.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record["doc_id"] not in docs or str(record["certain"]) != "True":
            continue
        if record["kind"] != "span" or record["method"] == "page":
            page_level += 1
            continue
        question = questions[record["question_id"]]
        question.update(doc_id=record["doc_id"], question=record["question"], source=record["source"])
        question["pieces"].append((int(record["start"]), int(record["end"])))
    return questions, page_level


def load_chunks(path):
    return [{"start": chunk["start_char"], "end": chunk["end_char"], "tokens": chunk["token_count"],
             "prefix_tokens": chunk["prefix_token_count"], "index_text": (chunk["prefix"] or "") + chunk["text"]}
            for chunk in json.loads(path.read_text(encoding="utf-8"))["chunks"]]


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--parsers", nargs="+", default=["docling", "pdfplumber"])
    arg_parser.add_argument("--settings", nargs="*", help="setting folder names; default: every complete setting")
    arg_parser.add_argument("--docs", nargs="+", help="doc ids; default: every tuning document in pdfs/split.csv")
    arg_parser.add_argument("--final", action="store_true", help="allow held-out documents (final evaluation only)")
    arg_parser.add_argument("--budgets", nargs="+", type=int, default=[750, 1250, 2000])
    arg_parser.add_argument("--cache", default=PROJECT_ROOT / "data" / "embeddings" / "bge-m3")
    arg_parser.add_argument("--machine", default="laptop")
    arg_parser.add_argument("--run-source", default="LOCAL")
    args = arg_parser.parse_args()

    tuning = tuning_ids()
    docs = set(args.docs or tuning)
    if docs - tuning and not args.final:
        raise PermissionError(f"held-out documents need --final (final evaluation only): {sorted(docs - tuning)}")
    cached, vectors = load_cache(args.cache)
    run_id, logger, rows, largest, left_out = new_run_id(3, args.run_source), CostLogger(), [], {}, {}
    for parser in args.parsers:
        questions, left_out[parser] = gold_questions(parser, docs)
        by_doc = defaultdict(list)
        for question_id, question in questions.items():
            by_doc[question["doc_id"]].append((question_id, question))
        texts = {doc: json.loads((EXTRACTED / parser / f"{doc}.json").read_text(encoding="utf-8"))["text"] for doc in by_doc}
        nonspace = {doc: np.concatenate([[0], np.cumsum([not char.isspace() for char in text])]) for doc, text in texts.items()}
        folders = [folder for folder in sorted((CHUNKS / parser).iterdir())
                   if folder.is_dir() and all((folder / f"{doc}.json").exists() for doc in docs)
                   and (not args.settings or folder.name in args.settings)]
        print(f"{parser}: {len(questions)} questions on {len(by_doc)} documents | page-level gold left out: "
              f"{left_out[parser]} | settings: {len(folders)}")
        for folder in folders:
            with logger.stage(f"score:{parser}:{folder.name}"):
                for doc, doc_questions in by_doc.items():
                    chunks = load_chunks(folder / f"{doc}.json")
                    largest[(parser, folder.name)] = max(largest.get((parser, folder.name), 0),
                                                         max(chunk["tokens"] + chunk["prefix_tokens"] for chunk in chunks))
                    bm25 = BM25([chunk["index_text"] for chunk in chunks])
                    chunk_vectors = vectors[[cached[text_key(chunk["index_text"])] for chunk in chunks]]
                    for question_id, question in doc_questions:
                        gold = Gold(question["pieces"], nonspace[doc])
                        if not gold.total:
                            continue
                        chunk_gold = [gold.inside(chunk["start"], chunk["end"]) for chunk in chunks]
                        bm25_order = bm25.ranking(question["question"])
                        dense_order = dense_ranking(vectors[cached[text_key(question["question"])]], chunk_vectors)
                        for retriever, order in (("bm25", bm25_order), ("dense", dense_order),
                                                 ("hybrid", hybrid_ranking(bm25_order, dense_order))):
                            row = {"parser": parser, "setting": folder.name, "doc_id": doc, "question_id": question_id,
                                   "source": question["source"], "retriever": retriever, "coverage": gold.whole_in(chunks),
                                   **rank_metrics(order, chunks, chunk_gold, texts[doc])}
                            rows += [{**row, "budget": budget, **measure(order, chunks, texts[doc], gold, budget, chunk_gold)}
                                     for budget in args.budgets]

    frame = pd.DataFrame(rows)
    frame["fits_750"] = [largest[(parser, setting)] <= 750 for parser, setting in zip(frame["parser"], frame["setting"])]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    output = OUTPUT / f"{run_id}.csv.gz"
    frame.to_csv(output, index=False)
    stack = {"scorer": SCORER, "embedder": EMBEDDER, "budgets": args.budgets, "parsers": args.parsers,
             "page_level_gold_left_out": left_out}
    manifest_path = write_manifest(build_manifest(run_id, "v1.2", stack, sorted(GOLD.glob("spans_*.jsonl")), [output],
                                                  logger.summary(), args.machine))

    main_questions = frame[(frame["budget"] == 1250) & (frame["source"].str.lower() != "qasper")]
    table = (main_questions.groupby(["parser", "setting", "retriever", "doc_id"])["recall"].mean()
             .groupby(["parser", "setting", "retriever"]).mean().unstack("retriever").round(3))
    pd.set_option("display.width", 200)
    print(f"\nRecall@1,250, main questions (document means, then setting means)\n{table.to_string()}\n\n"
          f"rows {len(frame):,} | saved {output}\nrun {run_id} | manifest: {manifest_path}")


if __name__ == "__main__":
    main()