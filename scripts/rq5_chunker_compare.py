"""RQ5(b) (spec v1.2): does tuning a chunker's size beat its default? Per chunker family and parser, the tuned
setting is the size with the highest mean document recall on the tuning run; the default is the library default
where one exists (LangChain), else the spec v1 starting size 512. Both are compared on the held-out run: paired
document bootstrap of (tuned - default) on shared questions, Holm-corrected over all comparisons."""
import argparse
import re

import numpy as np
import pandas as pd

from scripts.p4_analyse import resampled_means
from scripts.rq5_parser_compare import holm
from src.common.cost_logger import CostLogger
from src.common.manifest import PROJECT_ROOT, build_manifest, new_run_id, write_manifest
from src.eval.stats import LEVEL, RESAMPLES, SEED

RESULTS = PROJECT_ROOT / "data" / "results"
FAMILIES = {"langchain_recursive": (re.compile(r"langchain_recursive_size(\d+)_overlap0_noprefix"), "langchain_default_noprefix"),
            "recursive": (re.compile(r"recursive_size(\d+)_overlap0_noprefix"), "recursive_size512_overlap0_noprefix"),
            "fixed_token": (re.compile(r"fixed_token_size(\d+)_overlap0_noprefix"), "fixed_token_size512_overlap0_noprefix"),
            "method1_tree": (re.compile(r"method1_tree_T(\d+)_noprefix"), "method1_tree_T512_noprefix")}


def scores(run, retriever, budget):
    frame = pd.read_csv(RESULTS / "p3" / f"{run}.csv.gz")
    return frame[(frame["retriever"] == retriever) & (frame["budget"] == budget) & (frame["source"].str.lower() != "qasper")]


def document_recall(frame, parser, settings):
    """Documents x settings of mean recall, on the questions scored by every one of the settings."""
    part = frame[(frame["parser"] == parser) & frame["setting"].isin(settings)]
    per_question = part.pivot_table(index=["doc_id", "question_id"], columns="setting", values="recall").dropna()
    return per_question.groupby(level="doc_id").mean()


def tuned_setting(tuning, parser, pattern):
    settings = [setting for setting in tuning["setting"].unique() if pattern.fullmatch(setting)]
    return document_recall(tuning, parser, settings).mean().idxmax()


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--tuning-run", required=True)
    arg_parser.add_argument("--heldout-run", required=True)
    arg_parser.add_argument("--retriever", default="hybrid")
    arg_parser.add_argument("--budget", type=int, default=1250)
    args = arg_parser.parse_args()

    tuning, heldout = scores(args.tuning_run, args.retriever, args.budget), scores(args.heldout_run, args.retriever, args.budget)
    rng, logger, rows = np.random.default_rng(SEED), CostLogger(), []
    with logger.stage("compare"):
        for family, (pattern, default) in FAMILIES.items():
            for parser in ["docling", "pdfplumber"]:
                tuned = tuned_setting(tuning, parser, pattern)
                docs = document_recall(heldout, parser, list(dict.fromkeys([default, tuned])))
                difference = docs[tuned] - docs[default]
                means = resampled_means(difference.to_numpy()[:, None], rng)[:, 0]
                low, high = np.quantile(means, [(1 - LEVEL) / 2, (1 + LEVEL) / 2])
                rows.append({"family": family, "parser": parser, "default": default, "tuned": tuned,
                             "documents": len(docs), "default_recall": docs[default].mean(), "tuned_recall": docs[tuned].mean(),
                             "difference": difference.mean(), "low": low, "high": high,
                             "p": min(1.0, 2 * min((means <= 0).mean(), (means >= 0).mean()))})
        table = pd.DataFrame(rows)
        table["holm_p"] = holm(table["p"].to_numpy())
        table["beats_default"] = (table["low"] > 0) & (table["holm_p"] < 0.05)

    run_id = new_run_id(5, "LOCAL")
    output = RESULTS / "rq5" / f"{run_id}_chunker.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(output, index=False)
    stack = {"analysis": "rq5b_chunker_compare", "tuning_run": args.tuning_run, "heldout_run": args.heldout_run,
             "retriever": args.retriever, "budget": args.budget, "resamples": RESAMPLES, "level": LEVEL, "seed": SEED}
    inputs = [RESULTS / "p3" / f"{run}.csv.gz" for run in (args.tuning_run, args.heldout_run)]
    manifest_path = write_manifest(build_manifest(run_id, "v1.2", stack, inputs, [output], logger.summary(), "laptop"))
    pd.set_option("display.width", 240)
    print(f"RQ5(b): tuned size (chosen on tuning) vs default, on held-out (hybrid, Recall@{args.budget})\n"
          f"{table.round(3).to_string(index=False)}\n\nrun {run_id} | manifest: {manifest_path}")


if __name__ == "__main__":
    main()