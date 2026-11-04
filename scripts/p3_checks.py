"""P3 checks against code mistakes, run on a scorer result file: rules every row must obey, the budget always filled
unless the whole document was read, BM25 recomputed term by term (textbook formula, plain loops) for a sample, and a
random ranking scoring clearly lower than dense on the same chunks."""
import argparse
import json
import math
import random
from collections import Counter

import numpy as np
import pandas as pd

from scripts.p3_score import CHUNKS, EXTRACTED, gold_questions, load_chunks
from src.common.manifest import PROJECT_ROOT
from src.eval.embed import load_cache, text_key
from src.eval.score import BM25, SCORER, WORD, Gold, dense_ranking, measure


def row_rules(frame):
    question = ["parser", "setting", "doc_id", "question_id"]
    one = 1 - 1e-12
    return {"recall between 0 and 1": frame["recall"].between(0, 1).all(),
            "full => recall 1": (~frame["full"] | (frame["recall"] > one)).all(),
            "recall 1 => full": (~(frame["recall"] > one) | frame["full"]).all(),
            "hit <=> recall > 0": (frame["hit"] == (frame["recall"] > 0)).all(),
            "ndcg between 0 and 1": frame["ndcg"].between(0, 1 + 1e-9).all(),
            "geom = sqrt(ndcg x recall)": np.allclose(frame["geom"], np.sqrt(frame["ndcg"] * frame["recall"])),
            "hit5 => hit10": (~frame["hit5"] | frame["hit10"]).all(),
            "hit5 <=> mrr >= 1/5": (frame["hit5"] == (frame["mrr"] >= 0.2 - 1e-12)).all(),
            "first-hit tokens known <=> mrr > 0": (frame["tokens_to_first_hit"].notna() == (frame["mrr"] > 0)).all(),
            "tokens read <= budget": (frame["tokens_read"] <= frame["budget"]).all(),
            "coverage same for every retriever and budget": frame.groupby(question)["coverage"].nunique().max() == 1,
            "ranking metrics same for every budget": frame.groupby(question + ["retriever"])[["mrr", "hit5", "hit10"]].nunique().max().max() == 1}


def budget_filled(frame):
    """Rows reading less than the budget must have read the whole document (overlap settings left out: their total
    counts overlapping text twice)."""
    short = frame[(frame["tokens_read"] < frame["budget"]) & ~frame["setting"].str.contains("overlap(?:8|32|64)", regex=True)]
    totals = {key: sum(chunk["tokens"] + chunk["prefix_tokens"] for chunk in load_chunks(CHUNKS / key[0] / key[1] / f"{key[2]}.json"))
              for key in short[["parser", "setting", "doc_id"]].drop_duplicates().itertuples(index=False, name=None)}
    wrong = sum(row.tokens_read != totals[(row.parser, row.setting, row.doc_id)] for row in short.itertuples(index=False))
    return len(short), wrong


def textbook_bm25(question, texts):
    """BM25 with plain loops: score = sum over question words of idf x tf x (k1 + 1) / (tf + k1 x (1 - b + b x len / avg))."""
    k1, b = SCORER["bm25"]["k1"], SCORER["bm25"]["b"]
    documents = [WORD.findall(text.lower()) for text in texts]
    average = max(sum(len(words) for words in documents) / len(documents), 1.0)
    scores = []
    for words in documents:
        counts, score = Counter(words), 0.0
        for term in set(WORD.findall(question.lower())):
            holders = sum(term in other for other in documents)
            if holders and counts[term]:
                idf = math.log((len(documents) - holders + 0.5) / (holders + 0.5) + 1)
                score += idf * counts[term] * (k1 + 1) / (counts[term] + k1 * (1 - b + b * len(words) / average))
        scores.append(score)
    return scores


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--results", required=True)
    arg_parser.add_argument("--setting", default="method1_tree_T512_noprefix")
    args = arg_parser.parse_args()
    frame = pd.read_csv(args.results)
    print(f"rows {len(frame):,}")
    for name, passed in row_rules(frame).items():
        print(f"{'PASS' if passed else 'FAIL'}  {name}")
    short, wrong = budget_filled(frame)
    print(f"{'PASS' if wrong == 0 else 'FAIL'}  budget filled unless the whole document was read ({short:,} short rows, {wrong} unexplained)")

    questions = gold_questions("docling", set(frame["doc_id"]))[0]
    sample = random.Random(42).sample(sorted(questions), 50)
    differing = 0
    for question_id in sample:
        question = questions[question_id]
        texts = [chunk["index_text"] for chunk in load_chunks(CHUNKS / "docling" / args.setting / f"{question['doc_id']}.json")]
        textbook = np.argsort(-np.array(textbook_bm25(question["question"], texts)), kind="stable")[:10]
        differing += not np.array_equal(textbook, BM25(texts).ranking(question["question"])[:10])
    print(f"{'PASS' if differing == 0 else 'FAIL'}  BM25 top 10 equals the textbook loop for 50 questions ({differing} differ)")

    cached, vectors = load_cache(PROJECT_ROOT / "data" / "embeddings" / "bge-m3")
    shuffler, dense, chance = random.Random(0), [], []
    for question_id, question in questions.items():
        doc = question["doc_id"]
        text = json.loads((EXTRACTED / "docling" / f"{doc}.json").read_text(encoding="utf-8"))["text"]
        nonspace = np.concatenate([[0], np.cumsum([not char.isspace() for char in text])])
        chunks = load_chunks(CHUNKS / "docling" / args.setting / f"{doc}.json")
        gold = Gold(question["pieces"], nonspace)
        if not gold.total:
            continue
        chunk_gold = [gold.inside(chunk["start"], chunk["end"]) for chunk in chunks]
        order = dense_ranking(vectors[cached[text_key(question["question"])]], vectors[[cached[text_key(chunk["index_text"])] for chunk in chunks]])
        shuffled = list(range(len(chunks)))
        shuffler.shuffle(shuffled)
        dense.append(measure(order, chunks, text, gold, 1250, chunk_gold)["recall"])
        chance.append(measure(shuffled, chunks, text, gold, 1250, chunk_gold)["recall"])
    print(f"{'PASS' if np.mean(dense) > 2 * np.mean(chance) else 'FAIL'}  dense clearly above a random ranking "
          f"({args.setting}, docling, 1,250): dense {np.mean(dense):.3f} vs random {np.mean(chance):.3f}")


if __name__ == "__main__":
    main()