"""Robustness (spec v1.2, 2026-11-14): P4 (best single, ties, gap) with and without the Indian documents, and on
tuning also the RQ2 size result. --split tuning reads P3-LOCAL-20261105-4; --split held_out reads the existing scores
P3-FINAL-20261106-1 only (no chunk or document file) and needs --final. Writes a run record."""
import argparse

import numpy as np
import pandas as pd

from scripts.p3_size_by_source import measured_sizes
from scripts.p4_analyse import LEVEL, SEED, analyse, in_scope, question_matrix, resampled_means
from scripts.rq5_chunker_compare import FAMILIES, tuned_setting
from src.common.cost_logger import CostLogger
from src.common.manifest import build_manifest, new_run_id, write_manifest
from src.common.paths import PROJECT_ROOT, RESULTS

RUNS = {"tuning": ("P3-LOCAL-20261105-4", "NOINDIAN"), "held_out": ("P3-FINAL-20261106-1", "FINAL-NOINDIAN")}
ORIGINAL_RUN, SEALED = "P3-LOCAL-20261105-2", "held_out"
SPLIT_FILE = PROJECT_ROOT / "pdfs" / "split.csv"
PRIMARY_FILE = RESULTS / "p4" / "P4-FINAL-20261106-1_primary_setups.csv"
EXCLUDED_SOURCE = "Indian"


def p4_rows(frame, primary):
    """Same scopes and rng order as p4_analyse (full, original, primary), seed 42; zero cost tables (cost does not
    enter ties, best single, oracle or gap)."""
    frame, rng = frame[frame["budget"] == 1250], np.random.default_rng(SEED)
    original = set(in_scope(pd.read_csv(RESULTS / "p3" / f"{ORIGINAL_RUN}.csv.gz", usecols=["setting"])["setting"].unique()))
    full = in_scope(frame["setting"].unique())
    scopes = {"full": full, "original": [s for s in full if s in original], "primary": [s for s in full if s in set(primary)]}
    rows, setups_by_scope = [], {}
    for scope, settings in scopes.items():
        questions, left_out = question_matrix(frame, settings)
        zeros = pd.DataFrame(0.0, index=questions.index.get_level_values("doc_id").unique(), columns=questions.columns)
        single, per_doc, setups = analyse(questions, zeros, zeros, rng)
        low, high = np.quantile(resampled_means(per_doc[["gap"]].to_numpy(), rng)[:, 0], [(1 - LEVEL) / 2, (1 + LEVEL) / 2])
        setups_by_scope[scope] = setups
        rows.append({"scope": scope, "setups": questions.shape[1], "documents": len(per_doc), "questions": len(questions),
                     "best_single": single, "best_recall": setups.loc[single, "recall"],
                     "tied": int(setups["tied_with_best"].sum()), "oracle": per_doc["oracle"].mean(),
                     "gap": per_doc["gap"].mean(), "gap_low": low, "gap_high": high, "go": low > 0})
    return pd.DataFrame(rows), setups_by_scope


def size_rows(frame):
    """Pooled RQ2: per parser and budget, the size-recall Spearman over settings (document means pooled over all
    documents) and the best setting; per family and parser, the RQ5(b) tuned size at 1,250."""
    pooled, tuned = [], []
    for parser in ["docling", "pdfplumber"]:
        subset = frame[frame["parser"] == parser]
        matrices = {budget: question_matrix(subset[subset["budget"] == budget], in_scope(subset["setting"].unique()))[0]
                    for budget in sorted(subset["budget"].unique())}
        sizes = measured_sizes(matrices[1250])
        for budget, questions in matrices.items():
            recalls = questions.groupby(level=0).mean().mean()
            best = recalls.idxmax()
            pooled.append({"parser": parser, "budget": budget, "documents": questions.index.get_level_values(0).nunique(),
                           "best_setting": best.split("/", 1)[1], "best_size": round(sizes[best]), "best_recall": recalls[best],
                           "spearman": recalls.corr(sizes[recalls.index], method="spearman")})
        for family, (pattern, default) in FAMILIES.items():
            tuned.append({"family": family, "parser": parser,
                          "tuned": tuned_setting(frame[frame["budget"] == 1250], parser, pattern)})
    return pd.DataFrame(pooled), pd.DataFrame(tuned)


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--split", choices=list(RUNS), default="tuning")
    arg_parser.add_argument("--final", action="store_true", help="allow a run holding held-out documents")
    arg_parser.add_argument("--machine", default="laptop")
    args = arg_parser.parse_args()

    run, source = RUNS[args.split]
    scores_file = RESULTS / "p3" / f"{run}.csv.gz"
    primary = sorted({setup.split("/")[1] for setup in pd.read_csv(PRIMARY_FILE, index_col=0).index})
    scores = pd.read_csv(scores_file)
    scores = scores[(scores["retriever"] == "hybrid") & (scores["source"].str.lower() != "qasper")]
    splits = pd.read_csv(SPLIT_FILE).set_index("doc_id")["split"]
    if scores["doc_id"].map(splits).fillna("").str.startswith(SEALED).any() and not args.final:
        raise SystemExit(f"{run} holds held-out documents: rerun with --final")
    everything = "all tuning" if args.split == "tuning" else "all held-out"
    variants = {everything: scores, "without Indian": scores[scores["source"] != EXCLUDED_SOURCE]}
    excluded = sorted(scores.loc[scores["source"] == EXCLUDED_SOURCE, "doc_id"].unique())
    logger = CostLogger()
    with logger.stage("robust_no_indian"):  # the size part needs chunk files and is a tuning-only result: tuning only
        results = {name: (p4_rows(frame, primary), size_rows(frame) if args.split == "tuning" else None)
                   for name, frame in variants.items()}
    p4 = pd.concat({name: rows for name, ((rows, setups), sizes) in results.items()}, names=["variant"])
    setups = pd.DataFrame({name: setups["primary"]["recall"] for name, ((rows, setups), sizes) in results.items()})
    setups["tied_all"] = results[everything][0][1]["primary"]["tied_with_best"]
    setups["tied_without_indian"] = results["without Indian"][0][1]["primary"]["tied_with_best"]
    setups["rank_all"] = setups[everything].rank(ascending=False)
    setups["rank_without_indian"] = setups["without Indian"].rank(ascending=False)
    tables = {"p4": p4, "primary_setups": setups}
    if args.split == "tuning":
        tables["pooled_size"] = pd.concat({name: sizes[0] for name, (p4_part, sizes) in results.items()}, names=["variant"])
        tables["tuned_size"] = pd.concat({name: sizes[1] for name, (p4_part, sizes) in results.items()}, names=["variant"])

    run_id = new_run_id(4, source)
    outputs = [RESULTS / "p4" / f"{run_id}_{name}.csv" for name in tables]
    for path, table in zip(outputs, tables.values()):
        table.to_csv(path)
    stack = {"analysis": "robust_no_indian", "split": args.split, "scores_run": run, "original_run": ORIGINAL_RUN,
             "retriever": "hybrid", "budget_p4": 1250, "excluded_source": EXCLUDED_SOURCE, "excluded_documents": excluded,
             "primary_settings_from": PRIMARY_FILE.name, "final": args.final, "seed": SEED, "level": LEVEL,
             "summary": {f"{name} / {row.scope}": {"documents": row.documents, "questions": row.questions,
                                                    "best_single": row.best_single, "best_recall": row.best_recall,
                                                    "tied": row.tied, "gap": row.gap, "gap_interval": [row.gap_low, row.gap_high]}
                         for (name, index), row in p4.iterrows()}}
    manifest_path = write_manifest(build_manifest(run_id, "v1.2", stack, [scores_file, PRIMARY_FILE, SPLIT_FILE], outputs,
                                                  logger.summary(), args.machine))
    pd.set_option("display.width", 250)
    print(f"P4 ({args.split}, hybrid, Recall@1,250; left out: {excluded})\n{p4.round(3).to_string()}\n\nprimary setups\n"
          f"{setups.sort_values(everything, ascending=False).round(3).to_string()}")
    if args.split == "tuning":
        tuned = tables["tuned_size"].reset_index()
        print(f"\nRQ2 pooled size curve\n{tables['pooled_size'].round(3).to_string()}\n\nRQ5(b) tuned size per family\n"
              f"{tuned.pivot_table(index=['family', 'parser'], columns='variant', values='tuned', aggfunc='first').to_string()}")
    print(f"\nrun {run_id} | manifest: {manifest_path}")


if __name__ == "__main__":
    main()
