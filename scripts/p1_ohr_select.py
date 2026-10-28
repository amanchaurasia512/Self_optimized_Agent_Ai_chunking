"""Tuning B: choose OHR-Bench v2 documents. Only text and table questions count (the evidence types placeable as spans).
Per dense domain: keep documents in the top 10% by usable questions (cut-off from the data), then a seeded draw of 3."""
import json

import pandas as pd

from src.common.manifest import PROJECT_ROOT

OHR_DIR = PROJECT_ROOT / "data" / "external" / "ohr_bench"
DOMAINS = ["academic", "administration", "finance", "law", "manual"]
USABLE_SOURCES = ["text", "table"]
SEED, PER_DOMAIN, TOP_SHARE = 42, 3, 0.10


def draw(documents):
    cutoff = documents["usable_questions"].quantile(1 - TOP_SHARE)
    eligible = documents[documents["usable_questions"] >= cutoff]
    return eligible.sample(n=min(PER_DOMAIN, len(eligible)), random_state=SEED).assign(cutoff=cutoff, eligible=len(eligible))


def main():
    summary = pd.read_csv(OHR_DIR / "document_summary.csv")
    summary["usable_questions"] = summary[USABLE_SOURCES].sum(axis=1)
    selected = pd.concat([draw(summary[summary["domain"] == domain]) for domain in DOMAINS], ignore_index=True)
    selected.to_csv(OHR_DIR / "selected_documents.csv", index=False)

    questions = json.loads((OHR_DIR / "qas_v2.json").read_text(encoding="utf-8"))
    chosen = [question for question in questions
              if question["doc_name"] in set(selected["doc_name"]) and question["evidence_source"] in USABLE_SOURCES]
    (OHR_DIR / "selected_questions.json").write_text(json.dumps(chosen, ensure_ascii=False, indent=1), encoding="utf-8")

    print(selected[["domain", "doc_name", "pages", "usable_questions", "text", "table", "cutoff", "eligible"]].to_string(index=False))
    print(f"\ndocuments: {len(selected)} | usable questions: {len(chosen)} | total pages: {selected['pages'].sum()}")


if __name__ == "__main__":
    main()