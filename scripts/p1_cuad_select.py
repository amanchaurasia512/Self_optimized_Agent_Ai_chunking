"""P1-R01: choose CUAD contracts.
1. Drop ambiguous gold spans: answer text occurring more than once in its contract.
2. Leave out contracts in the bottom quarter by usable spans (cut-off computed from the data).
3. Draw contracts at random per length quartile, with a fixed seed."""
import json

import pandas as pd

from src.common.manifest import PROJECT_ROOT

OUTPUT_DIR = PROJECT_ROOT / "data" / "external" / "cuad"
CUAD_JSON = OUTPUT_DIR / "CUAD_v1" / "CUAD_v1.json"
SEED = 42
PER_GROUP = 2
GROUP_LABELS = ["short", "medium", "long", "very_long"]


def gold_spans(contracts):
    return pd.DataFrame([{"contract": contract["title"], "category": qa["id"].rsplit("__", 1)[-1],
                          "question": qa["question"], "answer_start": answer["answer_start"],
                          "answer_text": answer["text"], "occurrences": paragraph["context"].count(answer["text"])}
                         for contract in contracts for paragraph in contract["paragraphs"]
                         for qa in paragraph["qas"] for answer in qa["answers"]])


def contract_table(contracts, usable):
    words = pd.DataFrame([{"contract": contract["title"],
                           "words": sum(len(paragraph["context"].split()) for paragraph in contract["paragraphs"])}
                          for contract in contracts])
    counts = usable.groupby("contract").agg(usable_spans=("category", "size"), usable_categories=("category", "nunique"))
    table = words.merge(counts, on="contract", how="left").fillna({"usable_spans": 0, "usable_categories": 0})
    table["length_group"] = pd.qcut(table["words"], len(GROUP_LABELS), labels=GROUP_LABELS)
    return table


def main():
    contracts = json.loads(CUAD_JSON.read_text(encoding="utf-8"))["data"]
    spans = gold_spans(contracts)
    usable = spans[spans["occurrences"] == 1]
    table = contract_table(contracts, usable)
    floor = table["usable_spans"].quantile(0.25)
    eligible = table[table["usable_spans"] >= floor]
    selected = eligible.groupby("length_group", observed=True).sample(n=PER_GROUP, random_state=SEED)

    selected.to_csv(OUTPUT_DIR / "selected_contracts.csv", index=False)
    usable[usable["contract"].isin(selected["contract"])].to_csv(OUTPUT_DIR / "selected_gold_spans.csv", index=False)

    print("spans:", len(spans), "| ambiguous (occur > 1):", (spans["occurrences"] > 1).sum(),
          "| not found in text:", (spans["occurrences"] == 0).sum(), "| usable:", len(usable))
    print("usable-span floor (25th percentile):", floor, "| eligible contracts:", len(eligible), "\n")
    print(selected[["length_group", "contract", "words", "usable_spans", "usable_categories"]].to_string(index=False))


if __name__ == "__main__":
    main()