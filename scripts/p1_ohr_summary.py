"""Tuning B: summarise OHR-Bench v2 per document: pages, questions, and questions by evidence source."""
import json

import pandas as pd

from src.common.manifest import PROJECT_ROOT

OHR_DIR = PROJECT_ROOT / "data" / "external" / "ohr_bench"


def main():
    questions = pd.DataFrame(json.loads((OHR_DIR / "qas_v2.json").read_text(encoding="utf-8")))
    pages = pd.read_parquet(OHR_DIR / "OHR-Bench_v2.parquet", columns=["doc_name", "page_idx"]).groupby("doc_name").size().rename("pages")
    by_source = questions.pivot_table(index="doc_name", columns="evidence_source", values="ID", aggfunc="count", fill_value=0)
    summary = (questions.groupby("doc_name").agg(domain=("doc_type", "first"), questions=("ID", "size"))
               .join(pages).join(by_source).reset_index())
    summary.to_csv(OHR_DIR / "document_summary.csv", index=False)

    print("questions by evidence source:", questions["evidence_source"].value_counts().to_dict(), "\n")
    print(summary.groupby("domain").agg(documents=("doc_name", "size"), questions=("questions", "sum"),
                                        q75=("questions", lambda counts: counts.quantile(0.75)),
                                        q90=("questions", lambda counts: counts.quantile(0.9)),
                                        median_pages=("pages", "median"), max_pages=("pages", "max")).round(1))


if __name__ == "__main__":
    main()