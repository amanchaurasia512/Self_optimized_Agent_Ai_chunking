"""P1-R07: review sample of uncertain gold placements (fuzzy and segment_fuzzy), stratified by word coverage."""
import argparse
import json

import pandas as pd

from src.common.manifest import PROJECT_ROOT

GOLD_DIR = PROJECT_ROOT / "data" / "gold"
EXTRACTED = PROJECT_ROOT / "data" / "extracted"
SEED = 42
PER_BAND = 5
BANDS = 10


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--parser", default="docling")
    args = arg_parser.parse_args()

    spans = pd.read_json(GOLD_DIR / f"spans_{args.parser}.jsonl", lines=True)
    uncertain = spans[spans["method"].isin(["fuzzy", "segment_fuzzy"]) & spans["start"].notna()].copy()
    uncertain["band"] = pd.qcut(uncertain["word_coverage"].rank(method="first"), BANDS, labels=range(1, BANDS + 1))
    sample = uncertain.groupby("band", observed=True).sample(n=PER_BAND, random_state=SEED).sort_values(["band", "word_coverage"])

    texts = {doc_id: json.loads((EXTRACTED / args.parser / f"{doc_id}.json").read_text(encoding="utf-8"))["text"]
             for doc_id in sample["doc_id"].unique()}
    sample["placed"] = [texts[row.doc_id][int(row.start):int(row.end)] for row in sample.itertuples()]
    sample["verdict"] = ""
    columns = ["band", "source", "question_id", "method", "score", "word_coverage", "gold", "placed", "verdict"]
    output = GOLD_DIR / f"review2_{args.parser}.csv"
    sample[columns].to_csv(output, index=False)
    print(f"{len(sample)} rows -> {output}")
    print(uncertain.groupby("band", observed=True)["word_coverage"].agg(["min", "max"]).round(2).to_string())


if __name__ == "__main__":
    main()