"""P1-R07: fit the drop rule for uncertain gold placements on reviewed sheets, or check the locked rule on a fresh sheet."""
import argparse
import json

import pandas as pd

from src.gold.matching import DROP_RULE_FILE, word_coverage

VERDICTS = {"correct": False, "partial": False, "wrong": True}

def load_review(path):
    review = pd.read_csv(path, dtype={"verdict": str}).dropna(subset=["verdict"])
    if review.empty:
        raise SystemExit(f"{path}: no verdicts filled in yet")
    review["verdict"] = review["verdict"].str.strip().str.lower()
    unknown = sorted(set(review["verdict"]) - set(VERDICTS))
    if unknown:
        raise SystemExit(f"{path}: unknown verdicts {unknown}; use correct / partial / wrong")
    review["wrong"] = review["verdict"].map(VERDICTS)
    review["coverage"] = [word_coverage(row.gold, row.placed) for row in review.itertuples()]
    return review   


def errors(review, threshold):
    return int(((review["coverage"] < threshold) != review["wrong"]).sum())


def fit(review):
    """Midpoint between neighbouring coverage values with the fewest errors; ties go to the widest gap."""
    values = sorted(set(review["coverage"]))
    candidates = [((low + high) / 2, high - low) for low, high in zip(values, values[1:])]
    best = min(candidates, key=lambda candidate: (errors(review, candidate[0]), -candidate[1]))
    return round(best[0], 3)


def report(review, threshold):
    decision = review["coverage"].lt(threshold).map({True: "dropped", False: "kept"})
    print(pd.crosstab(review["verdict"], decision).to_string())
    print(f"threshold {threshold}: {errors(review, threshold)} of {len(review)} rows misclassified")


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    mode = arg_parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fit", nargs="+", help="reviewed sheets to fit the threshold on")
    mode.add_argument("--check", help="fresh reviewed sheet to test the locked threshold on, without refitting")
    args = arg_parser.parse_args()

    if args.fit:
        review = pd.concat([load_review(path) for path in args.fit], ignore_index=True)
        threshold = fit(review)
        DROP_RULE_FILE.parent.mkdir(exist_ok=True)
        DROP_RULE_FILE.write_text(json.dumps({"rule": "drop fuzzy/segment_fuzzy placements with word_coverage below threshold",
                                              "threshold": threshold, "fitted_on": args.fit, "rows": len(review)}, indent=2))
        print(f"rule written to {DROP_RULE_FILE}")
    else:
        review = load_review(args.check)
        threshold = json.loads(DROP_RULE_FILE.read_text())["threshold"]
    report(review, threshold)


if __name__ == "__main__":
    main()