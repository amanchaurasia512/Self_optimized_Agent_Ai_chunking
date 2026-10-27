"""P1-R01: summarise CUAD v1 per contract: length, expert-labelled spans, answered categories."""
import json
from pathlib import Path

import pandas as pd
from huggingface_hub import hf_hub_download

from src.common.manifest import PROJECT_ROOT

REPO_ID = "theatticusproject/cuad"
OUTPUT_DIR = PROJECT_ROOT / "data" / "external" / "cuad"


def load_cuad():
    path = hf_hub_download(REPO_ID, "CUAD_v1/CUAD_v1.json", repo_type="dataset", local_dir=OUTPUT_DIR)
    return json.loads(Path(path).read_text(encoding="utf-8"))["data"]


def span_rows(contracts):
    return [{"contract": contract["title"], "category": qa["id"].rsplit("__", 1)[-1],
             "answer_start": answer["answer_start"], "answer_words": len(answer["text"].split())}
            for contract in contracts for paragraph in contract["paragraphs"]
            for qa in paragraph["qas"] for answer in qa["answers"]]


def contract_rows(contracts):
    return [{"contract": contract["title"],
             "words": sum(len(paragraph["context"].split()) for paragraph in contract["paragraphs"])}
            for contract in contracts]


def main():
    contracts = load_cuad()
    spans = pd.DataFrame(span_rows(contracts))
    per_contract = spans.groupby("contract").agg(spans=("category", "size"), categories=("category", "nunique"),
                                                 median_span_words=("answer_words", "median"),
                                                 max_span_words=("answer_words", "max"))
    summary = pd.DataFrame(contract_rows(contracts)).merge(per_contract, on="contract", how="left").fillna({"spans": 0, "categories": 0})
    spans.to_csv(OUTPUT_DIR / "spans.csv", index=False)
    summary.to_csv(OUTPUT_DIR / "contract_summary.csv", index=False)

    print("contracts:", len(summary), "| spans:", len(spans), "| categories in data:", spans["category"].nunique(), "\n")
    print(summary[["words", "spans", "categories", "median_span_words", "max_span_words"]].describe().round(1), "\n")
    print("example category ids:", sorted(spans["category"].unique())[:5])


if __name__ == "__main__":
    main()