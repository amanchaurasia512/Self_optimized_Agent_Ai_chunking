"""RQ5(a) analysis (spec v1.2): each parser variant against its default on the same sample and questions. Per
question, recall is averaged over the chunk settings of the run; per document, over its questions; the difference
(variant - default) gets a paired document bootstrap interval and a two-sided bootstrap p-value, Holm-corrected over
the variants of each default parser. A variant beats its default if the interval lies above 0 and Holm p < 0.05."""
import argparse

import numpy as np
import pandas as pd

from scripts.p4_analyse import resampled_means
from src.common.cost_logger import CostLogger
from src.common.manifest import PROJECT_ROOT, build_manifest, new_run_id, write_manifest
from src.eval.stats import LEVEL, RESAMPLES, SEED

RESULTS = PROJECT_ROOT / "data" / "results"


def default_of(parser):
    return parser.split("_", 1)[0]


def compare(frame, variant, rng):
    base = default_of(variant)
    pair = frame[frame["parser"].isin([base, variant])]
    per_question = pair.groupby(["parser", "doc_id", "question_id"])["recall"].mean().unstack("parser").dropna()
    docs = per_question.groupby(level="doc_id").mean()
    difference = docs[variant] - docs[base]
    means = resampled_means(difference.to_numpy()[:, None], rng)[:, 0]
    low, high = np.quantile(means, [(1 - LEVEL) / 2, (1 + LEVEL) / 2])
    p_value = min(1.0, 2 * min((means <= 0).mean(), (means >= 0).mean()))
    return {"variant": variant, "default": base, "documents": len(docs), "questions": len(per_question),
            "default_recall": docs[base].mean(), "variant_recall": docs[variant].mean(),
            "difference": difference.mean(), "low": low, "high": high, "p": p_value}


def holm(p_values):
    order, count, running = np.argsort(p_values), len(p_values), 0.0
    adjusted = np.empty(count)
    for rank, index in enumerate(order):
        running = max(running, (count - rank) * p_values[index])
        adjusted[index] = min(1.0, running)
    return adjusted


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--run", required=True, help="P3 score run id of one sample")
    arg_parser.add_argument("--sample", required=True)
    arg_parser.add_argument("--retriever", default="hybrid")
    arg_parser.add_argument("--budget", type=int, default=1250)
    args = arg_parser.parse_args()

    scores = RESULTS / "p3" / f"{args.run}.csv.gz"
    frame = pd.read_csv(scores)
    frame = frame[(frame["retriever"] == args.retriever) & (frame["budget"] == args.budget)]
    rng, logger = np.random.default_rng(SEED), CostLogger()
    with logger.stage(f"compare:{args.sample}"):
        variants = sorted(parser for parser in frame["parser"].unique() if parser != default_of(parser))
        table = pd.DataFrame([compare(frame, variant, rng) for variant in variants])
        table["holm_p"] = np.concatenate([holm(group["p"].to_numpy()) for name, group in table.groupby("default", sort=False)])
        table["beats_default"] = (table["low"] > 0) & (table["holm_p"] < 0.05)
    run_id = new_run_id(5, "LOCAL")
    output = RESULTS / "rq5" / f"{run_id}_{args.sample}.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(output, index=False)
    stack = {"analysis": "rq5a_compare", "scores_run": args.run, "sample": args.sample, "retriever": args.retriever,
             "budget": args.budget, "resamples": RESAMPLES, "level": LEVEL, "seed": SEED}
    manifest_path = write_manifest(build_manifest(run_id, "v1.2", stack, [scores], [output], logger.summary(), "laptop"))
    print(f"\nRQ5(a) {args.sample}: variant vs default (hybrid, Recall@{args.budget}, mean over chunkers)\n"
          f"{table.round(3).to_string(index=False)}\n\nrun {run_id} | manifest: {manifest_path}")


if __name__ == "__main__":
    main()