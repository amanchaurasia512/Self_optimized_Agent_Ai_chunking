"""P3 scorer sanity tests 1 (floor) and 2 (damage) on a scorer result file, with the pass rules of spec v1.2 written
before the tests ran. Recall@1,250, main questions (QASPER apart), document means."""
import argparse
import json

import numpy as np
import pandas as pd

from scripts.p3_score import EXTRACTED, gold_questions
from src.eval.score import Gold
from src.eval.stats import bootstrap_interval, document_means

RANDOM, DAMAGED, BASE = "sanity_random_cut_size512_noprefix", "sanity_table_split_T512_noprefix", "method1_tree_T512_noprefix"


def table_questions(docs):
    """Docling question ids with at least half of their gold characters inside a table block."""
    questions, chosen = gold_questions("docling", docs)[0], set()
    for doc in docs:
        document = json.loads((EXTRACTED / "docling" / f"{doc}.json").read_text(encoding="utf-8"))
        nonspace = np.concatenate([[0], np.cumsum([not char.isspace() for char in document["text"]])])
        tables = [(element["start_char"], element["end_char"]) for element in document.get("elements", []) if element["label"] == "table"]
        for question_id, question in questions.items():
            if question["doc_id"] == doc:
                gold = Gold(question["pieces"], nonspace)
                if gold.total and 2 * sum(gold.inside(start, end) for start, end in tables) >= gold.total:
                    chosen.add(question_id)
    return chosen


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--results", required=True)
    args = arg_parser.parse_args()
    frame = pd.read_csv(args.results)
    main_rows = frame[(frame["budget"] == 1250) & (frame["source"].str.lower() != "qasper")]

    print("TEST 1 floor: random cut vs the best setting (Recall@1,250, mean [95% interval])")
    floor_passed = True
    for (parser, retriever), rows in main_rows.groupby(["parser", "retriever"]):
        intervals = {setting: bootstrap_interval(document_means(group)) for setting, group in rows.groupby("setting")}
        best = max((setting for setting in intervals if not setting.startswith("sanity_")), key=lambda setting: intervals[setting][0])
        random_mean, random_low, random_high = intervals[RANDOM]
        best_mean, best_low, best_high = intervals[best]
        passed = random_high < best_low
        floor_passed &= passed
        print(f"  {'PASS' if passed else 'FAIL'} {parser:<10} {retriever:<6} random {random_mean:.3f} [{random_low:.3f}-{random_high:.3f}] "
              f"vs best {best} {best_mean:.3f} [{best_low:.3f}-{best_high:.3f}]")

    docling = main_rows[main_rows["parser"] == "docling"]
    tables = table_questions(set(docling["doc_id"]))
    print(f"\nTEST 2 damage: table questions on Docling: {len(tables)} (documents: {docling[docling['question_id'].isin(tables)]['doc_id'].nunique()})")
    damage_passed = True
    for retriever, rows in docling.groupby("retriever"):
        on_tables, elsewhere = rows[rows["question_id"].isin(tables)], rows[~rows["question_id"].isin(tables)]
        damaged, base = (on_tables[on_tables["setting"] == name]["recall"].mean() for name in (DAMAGED, BASE))
        other_damaged, other_base = (elsewhere[elsewhere["setting"] == name]["recall"].mean() for name in (DAMAGED, BASE))
        passed = damaged < base
        damage_passed &= passed
        print(f"  {'PASS' if passed else 'FAIL'} {retriever:<6} table questions: split {damaged:.3f} vs method 1 {base:.3f} | "
              f"other questions: split {other_damaged:.3f} vs method 1 {other_base:.3f}")
    print(f"\nfloor {'PASS' if floor_passed else 'FAIL'} | damage {'PASS' if damage_passed else 'FAIL'}")


if __name__ == "__main__":
    main()