"""P3 S13: hand-check cases for the hit rule. Picks 20 cases (seed 42) from a scorer result file (dense, 1,250 tokens):
7 full hits, 7 partial hits, 6 misses; prints the question, the gold text and what was read within the budget, with the
scorer's Recall/Hit/Full and an independent recount (sets of non-space characters)."""
import argparse
import json

import numpy as np
import pandas as pd

from scripts.p3_score import CHUNKS, EXTRACTED, gold_questions, load_chunks
from src.common.manifest import PROJECT_ROOT
from src.eval.embed import load_cache, text_key
from src.eval.score import Gold, dense_ranking, measure, read_ranking

GROUPS = {"full": 7, "partial": 7, "miss": 6}


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--results", required=True)
    args = arg_parser.parse_args()

    frame = pd.read_csv(args.results)
    frame = frame[(frame["retriever"] == "dense") & (frame["budget"] == 1250)]
    frame["group"] = np.select([frame["recall"] == 1, frame["recall"] > 0], ["full", "partial"], "miss")
    cases = pd.concat([frame[frame["group"] == group].sample(n=min(count, (frame["group"] == group).sum()), random_state=42)
                       for group, count in GROUPS.items()])
    cached, vectors = load_cache(PROJECT_ROOT / "data" / "embeddings" / "bge-m3")
    questions = {parser: gold_questions(parser, set(cases["doc_id"]))[0] for parser in cases["parser"].unique()}

    for number, case in enumerate(cases.itertuples(index=False), start=1):
        question = questions[case.parser][case.question_id]
        text = json.loads((EXTRACTED / case.parser / f"{case.doc_id}.json").read_text(encoding="utf-8"))["text"]
        nonspace = np.concatenate([[0], np.cumsum([not char.isspace() for char in text])])
        chunks = load_chunks(CHUNKS / case.parser / case.setting / f"{case.doc_id}.json")
        gold = Gold(question["pieces"], nonspace)
        order = dense_ranking(vectors[cached[text_key(question["question"])]], vectors[[cached[text_key(chunk["index_text"])] for chunk in chunks]])
        taken, used = read_ranking(order, chunks, text, 1250)
        scored = measure(order, chunks, text, gold, 1250, [gold.inside(chunk["start"], chunk["end"]) for chunk in chunks])
        gold_set = {index for start, end in gold.pieces for index in range(start, end) if not text[index].isspace()}
        read_set = {index for position, start, end in taken for index in range(start, end) if not text[index].isspace()}
        recount = len(gold_set & read_set) / len(gold_set)

        print(f"\n===== case {number} ({case.group}) | {case.parser} | {case.setting} | {case.doc_id}")
        print(f"question: {question['question'][:200]}")
        for start, end in gold.pieces:
            print(f"gold [{start}-{end}]: {text[start:end][:200]!r}")
        for position, start, end in taken:
            inside = gold.inside(start, end)
            print(f"  read #{position} [{start}-{end}] {end - start} chars | gold chars inside: {inside}"
                  + (f" | {text[max(start, gold.pieces[0][0]):min(end, gold.pieces[0][1])][:120]!r}" if inside else ""))
        print(f"scorer: recall {scored['recall']:.3f} hit {scored['hit']} full {scored['full']} tokens {used} | "
              f"recount: recall {recount:.3f} | {'MATCH' if abs(recount - scored['recall']) < 1e-9 else 'MISMATCH'}")


if __name__ == "__main__":
    main()