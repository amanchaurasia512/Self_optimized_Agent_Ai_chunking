"""RQ5(a) digital sample (spec v1.2): per source group, the tuning PDF with the most certain span questions found on
both parsers; ties by doc_id. Writes pdfs/rq5_digital_picks.csv. Prints ids and counts only."""
import json

import pandas as pd

from src.common.manifest import PROJECT_ROOT
from src.common.split import tuning_ids

GROUPS = {"CUAD": ("cuad_",), "Indian": ("indian_",), "OHR finance": ("ohr_finance_",),
          "OHR administration or manual": ("ohr_administration_", "ohr_manual_"), "OHR academic": ("ohr_academic_",)}
PICKS_FILE = PROJECT_ROOT / "pdfs" / "rq5_digital_picks.csv"


def certain_questions(parser, docs):
    lines = (PROJECT_ROOT / "data" / "gold" / f"spans_{parser}.jsonl").read_text(encoding="utf-8").splitlines()
    return {(row["doc_id"], row["question_id"]) for row in map(json.loads, lines)
            if row["doc_id"] in docs and str(row["certain"]) == "True" and row["kind"] == "span" and row["method"] != "page"}


def main():
    tuning = tuning_ids()
    both = certain_questions("docling", tuning) & certain_questions("pdfplumber", tuning)
    counts = pd.Series([doc for doc, question in both]).value_counts()
    picks = []
    for group, prefixes in GROUPS.items():
        ranked = sorted(((doc, count) for doc, count in counts.items() if doc.startswith(prefixes)), key=lambda item: (-item[1], item[0]))
        picks.append({"group": group, "doc_id": ranked[0][0], "questions": int(ranked[0][1]), "candidates": len(ranked)})
    table = pd.DataFrame(picks)
    table.to_csv(PICKS_FILE, index=False)
    print(f"{table.to_string(index=False)}\nsaved {PICKS_FILE}")


if __name__ == "__main__":
    main()