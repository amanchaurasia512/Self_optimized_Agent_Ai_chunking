"""Gold drop rate (spec v1.2, reporting): for every gold file, how many questions scoring keeps and why the others are
left out: page-level gold (by design), placed but not certain, or not placed. Kept uses p3_score.gold_questions,
so the counts match what scoring used. Held-out documents only with --final."""
import argparse
import json

import pandas as pd

from scripts.p3_score import GOLD, gold_questions
from src.common.manifest import PROJECT_ROOT

OUT = PROJECT_ROOT / "data" / "results" / "p3"
SEALED = "held_out"
OUTCOMES = ["kept", "page_level", "placed_not_certain", "not_placed"]


def outcome(records, kept):
    if kept:
        return "kept"
    if all(record["kind"] != "span" or record["method"] == "page" for record in records):
        return "page_level"
    if any(record["start"] is not None for record in records):
        return "placed_not_certain"
    return "not_placed"


def drop_table(name, docs):
    by_question = {}
    for line in (GOLD / f"spans_{name}.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record["doc_id"] in docs:
            by_question.setdefault(record["question_id"], []).append(record)
    kept = gold_questions(name, docs)[0]
    return pd.DataFrame([{"gold_file": name, "split": records[0]["split"], "source": records[0]["source"],
                          "doc_id": records[0]["doc_id"], "question_id": question,
                          "outcome": outcome(records, question in kept)} for question, records in by_question.items()])


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--final", action="store_true", help="include held-out documents (counts only)")
    args = arg_parser.parse_args()

    splits = pd.read_csv(PROJECT_ROOT / "pdfs" / "split.csv")
    open_docs = splits.loc[~splits["split"].str.startswith(SEALED), "doc_id"]
    docs = set(splits["doc_id"] if args.final else open_docs)
    names = sorted(path.stem.removeprefix("spans_") for path in GOLD.glob("spans_*.jsonl"))
    questions = pd.concat([drop_table(name, docs) for name in names], ignore_index=True)

    counts = (questions.pivot_table(index=["gold_file", "split", "source"], columns="outcome", values="question_id",
                                    aggfunc="count", fill_value=0).reindex(columns=OUTCOMES, fill_value=0))
    counts["total"] = counts.sum(axis=1)
    scorable = (counts["total"] - counts["page_level"]).replace(0, float("nan"))
    counts["drop_rate"] = ((counts["placed_not_certain"] + counts["not_placed"]) / scorable).round(3)

    has_kept = questions.assign(kept=questions["outcome"] == "kept").groupby(["gold_file", "doc_id"])["kept"].any()
    empty_docs = has_kept[~has_kept].reset_index()[["gold_file", "doc_id"]]

    label = "final" if args.final else "tuning"
    OUT.mkdir(parents=True, exist_ok=True)
    counts.reset_index().to_csv(OUT / f"gold_drop_{label}.csv", index=False)
    empty_docs.to_csv(OUT / f"gold_drop_empty_docs_{label}.csv", index=False)
    print(counts.to_string())
    print(f"\ndocuments with no kept question:\n{empty_docs.to_string(index=False)}")

if __name__ == "__main__":
    main()