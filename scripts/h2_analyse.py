"""Held-out set 2, step 4 analysis (spec v1.2 "Held-out set 2: step 4 code", implementing "step 4 analysis" and the
"gold rule amendment"). Four steps, one run record each (P4-H2-<date>-n); held-out data need --final; --test writes
to data/results/tests/ and runs/tests/. p4_analyse.py is reused, not changed.
  side       recorded primary scope of held-out 1 and of the held-out 2 P4 runs, side by side (nothing recomputed)
  exclusion  primary run, common set with and without questions on pages whose image/PDF shapes differ by > 5%
  pooled     tuning winner applied on held-out 1 + held-out 2: split-half oracle minus the tuning winner (not the
             p4_analyse gap, oracle minus each set's best single), bootstrap stratified by set
  rq2        size-recall Spearman per parser and budget (13 setups), for all and per corpus, document bootstrap
Prints counts and numbers only."""
import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.h2_embed_bundle import primary_settings
from scripts.heldout2_vidore_register import QUERIES_FILE
from scripts.p3_size_by_source import measured_sizes
from scripts.p4_analyse import analyse, question_matrix, resampled_means, split_half_oracle
from src.common.cost_logger import CostLogger
from src.common.manifest import PROJECT_ROOT, RUNS_DIR, build_manifest, new_run_id, new_test_run_id, project_path, write_manifest
from src.common.split import tuning_ids
from src.eval.stats import LEVEL, RESAMPLES, SEED

RESULTS = PROJECT_ROOT / "data" / "results"
PAGE_SIZES = PROJECT_ROOT / "data" / "heldout2" / "page_sizes.csv"
TUNING_WINNER = "docling/langchain_recursive_size256_overlap0_noprefix"  # P4-LOCAL-20261105-1, scope full
HELD_OUT_1_BEST = "pdfplumber/method1_tree_T384_noprefix"  # P4-FINAL-20261106-1, scope primary
BUDGETS, SHAPE_LIMIT, P4_BUDGET = (750, 1250, 2000), 0.05, 1250


# ---------- inputs ----------

def find(*paths):
    found = next((path for path in paths if path.exists()), None)
    if found is None:
        raise FileNotFoundError(f"none of: {', '.join(map(project_path, paths))}")
    return found


def scores_path(run):
    return find(RESULTS / "p3" / f"{run}.csv.gz", RESULTS / "tests" / f"test_p3_score_{run}.csv.gz")


def scores(run, budget, final, fits_750=True):
    """Hybrid rows at one budget with the p4_analyse filters (QASPER out; fits_750 at 750 unless fits_750 is False,
    as tuning RQ2); held-out needs --final."""
    frame = pd.read_csv(scores_path(run))
    if set(frame["doc_id"]) - tuning_ids() and not final:
        raise PermissionError(f"{run} holds held-out documents: rerun with --final")
    return frame[(frame["retriever"] == "hybrid") & (frame["budget"] == budget)
                 & (frame["source"].str.lower() != "qasper") & ((budget != 750) | (not fits_750) | frame["fits_750"])]


def p4_primary(run):
    """Recorded primary scope of a p4_analyse run: its summary and its setups table."""
    record = json.loads(find(RUNS_DIR / f"{run}.json", RUNS_DIR / "tests" / f"test_p4_{run}.json").read_text(encoding="utf-8"))
    setups = pd.read_csv(find(RESULTS / "p4" / f"{run}_primary_setups.csv",
                              RESULTS / "tests" / "p4" / f"{run}_primary_setups.csv"), index_col=0)
    return record, setups


def interval(values):
    return [float(value) for value in np.quantile(values, [(1 - LEVEL) / 2, (1 + LEVEL) / 2])]


# ---------- steps ----------

def side(held_out_1, runs, final):
    """One row per P4 run (held-out 1 first): the recorded primary scope, nothing recomputed."""
    rows = []
    for label, run in [("held-out 1", held_out_1), *[(f"held-out 2 #{number}", run) for number, run in enumerate(runs, 1)]]:
        record, setups = p4_primary(run)
        documents = set(pd.read_csv(scores_path(record["stack"]["scores_run"]), usecols=["doc_id"])["doc_id"])
        if documents - tuning_ids() and not final:
            raise PermissionError(f"{run} analyses held-out documents: rerun with --final")
        summary, ranks = record["stack"]["summary"]["primary"], setups["recall"].rank(ascending=False)
        applied = {f"{name}_{field}": value for name, setup in (("tuning_winner", TUNING_WINNER), ("held_out_1_best", HELD_OUT_1_BEST))
                   for field, value in (("recall", setups.loc[setup, "recall"]), ("rank", int(ranks[setup])),
                                        ("tied", bool(setups.loc[setup, "tied_with_best"])))}
        low, high = summary["gap_interval"]
        rows.append({"set": label, "p4_run": run, "scores_run": record["stack"]["scores_run"], "setups": summary["setups"],
                     "documents": summary["documents"], "questions": summary["questions"], **applied,
                     "best_single": summary["best_single"], "best_single_recall": summary["best_single_recall"],
                     "tied_with_best": summary["tied_with_best"], "oracle": summary["oracle"], "gap": summary["gap"],
                     "gap_low": low, "gap_high": high, "decision": "GO" if low > 0 else "NO-GO"})
    return pd.DataFrame(rows), {"held_out_1": held_out_1, "runs": runs}


def shape_questions(page_sizes):
    """Question ids with an evidence page whose image and PDF aspect ratios differ by more than 5% (gold-run formula)."""
    pages = pd.read_csv(page_sizes)
    shape_diff = ((pages["image_width"] / pages["image_height"]) / (pages["pdf_width"] / pages["pdf_height"]) - 1).abs()
    return set(pages.loc[shape_diff > SHAPE_LIMIT, "question_id"]), int((shape_diff > SHAPE_LIMIT).sum())


def common_set_result(questions):
    zeros = pd.DataFrame(0.0, index=questions.index.get_level_values("doc_id").unique(), columns=questions.columns)
    rng = np.random.default_rng(SEED)
    single, per_doc, setups = analyse(questions, zeros, zeros, rng)
    low, high = interval(resampled_means(per_doc[["gap"]].to_numpy(), rng)[:, 0])
    return {"documents": len(per_doc), "questions": len(questions), "best_single": single,
            "best_single_recall": setups.loc[single, "recall"], "tied_with_best": int(setups["tied_with_best"].sum()),
            "tuning_winner_recall": setups.loc[TUNING_WINNER, "recall"], "oracle": per_doc["oracle"].mean(),
            "gap": per_doc["gap"].mean(), "gap_low": low, "gap_high": high, "decision": "GO" if low > 0 else "NO-GO"}


def exclusion(run, page_sizes, final):
    questions = question_matrix(scores(run, P4_BUDGET, final), primary_settings())[0]
    excluded, pages = shape_questions(page_sizes)
    kept = questions[~questions.index.get_level_values("question_id").isin(excluded)]
    table = pd.DataFrame([{"questions_set": "all", **common_set_result(questions)},
                          {"questions_set": f"without shape > {SHAPE_LIMIT:.0%}", **common_set_result(kept)}])
    return table, {"scores_run": run, "page_sizes": project_path(page_sizes), "pages_over_limit": pages,
                   "common_set_questions_excluded": len(questions) - len(kept)}


def winner_gaps(run, final):
    """Per document: split-half oracle minus the tuning winner (one-question documents: the winner's value)."""
    questions = question_matrix(scores(run, P4_BUDGET, final), primary_settings())[0]
    rng = np.random.default_rng(SEED)
    rows = []
    for doc, doc_questions in questions.groupby(level="doc_id"):
        winner = doc_questions[TUNING_WINNER].mean()
        oracle = split_half_oracle(doc_questions, rng)[0] if len(doc_questions) > 1 else winner
        rows.append({"doc_id": doc, "questions": len(doc_questions), "tuning_winner": winner, "oracle": oracle,
                     "gap": oracle - winner})
    return pd.DataFrame(rows)


def pooled(held_out_1, run, final):
    sets = {"held-out 1": winner_gaps(held_out_1, final), "held-out 2": winner_gaps(run, final)}
    rng, total = np.random.default_rng(SEED), sum(len(frame) for frame in sets.values())
    resampled = sum(resampled_means(frame[["gap"]].to_numpy(), rng)[:, 0] * len(frame) / total for frame in sets.values())
    frame = pd.concat([frame.assign(set=name) for name, frame in sets.items()])
    low, high = interval(resampled)
    table = pd.DataFrame([{"set": "pooled (secondary)", "documents": total, "questions": int(frame["questions"].sum()),
                           "tuning_winner": frame["tuning_winner"].mean(), "oracle": frame["oracle"].mean(),
                           "gap_oracle_minus_tuning_winner": frame["gap"].mean(), "gap_low": low, "gap_high": high,
                           "decision_secondary": "GO" if low > 0 else "NO-GO"}])
    return table, {"held_out_1_scores": held_out_1, "held_out_2_scores": run,
                   "documents": {name: len(part) for name, part in sets.items()}}, frame


def corpora(docs):
    """doc id -> corpus from data/heldout2/queries.jsonl; other documents take their score source."""
    lines = QUERIES_FILE.read_text(encoding="utf-8").splitlines() if QUERIES_FILE.exists() else []
    return {query["doc_id"]: query["corpus"] for query in map(json.loads, lines) if query["doc_id"] in docs}


def size_spearman(doc_means, sizes):
    """NaN when recall is the same for every setup (Spearman undefined); counted, not hidden."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return doc_means.mean().corr(sizes[doc_means.columns], method="spearman")


def rq2(runs, final):
    """Tuning RQ2 unit (robust_no_indian.size_rows): per parser, the common set of its 13 setups per budget (no
    fits_750 filter), sizes from the 1,250 matrix; Spearman of size against recall (question means per document, then
    document means). Verdict on all documents only: every parser and budget negative; per corpus descriptive."""
    rows = []
    for run in runs:
        frames = {budget: scores(run, budget, final, fits_750=False) for budget in BUDGETS}
        for parser in sorted(frames[P4_BUDGET]["parser"].unique()):
            matrices = {budget: question_matrix(frame[frame["parser"] == parser], primary_settings())[0]
                        for budget, frame in frames.items()}
            sizes = measured_sizes(matrices[P4_BUDGET])
            for budget, questions in matrices.items():
                doc_means = questions.groupby(level="doc_id").mean()
                sources = frames[budget].drop_duplicates("doc_id").set_index("doc_id")["source"].reindex(doc_means.index)
                groups = pd.Series(corpora(set(doc_means.index))).reindex(doc_means.index).fillna(sources)
                for corpus, part in [("all", doc_means), *doc_means.groupby(groups)]:
                    picks = np.random.default_rng(SEED).integers(0, len(part), size=(RESAMPLES, len(part)))
                    resampled = pd.Series([size_spearman(part.iloc[pick], sizes) for pick in picks])
                    low, high = interval(resampled.dropna()) if resampled.notna().any() else (np.nan, np.nan)
                    rows.append({"scores_run": run, "parser": parser, "budget": budget, "corpus": corpus,
                                 "documents": len(part), "setups": part.shape[1], "spearman": size_spearman(part, sizes),
                                 "low": low, "high": high, "resamples_undefined": int(resampled.isna().sum())})
    table = pd.DataFrame(rows)
    overall = table[table["corpus"] == "all"]
    verdicts = {run: bool((part["spearman"] < 0).all()) for run, part in overall.groupby("scores_run", sort=False)}
    return table, {"scores_runs": runs, "budgets": list(BUDGETS), "unit": "per parser and budget, 13 setups",
                   "negative_at_every_parser_and_budget_all": verdicts}


# ---------- main ----------

def main():
    arg_parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    arg_parser.add_argument("step", choices=("side", "exclusion", "pooled", "rq2"))
    arg_parser.add_argument("--held-out-1", help="side: P4 run (P4-FINAL-20261106-1); pooled: P3 run (P3-FINAL-20261106-1)")
    arg_parser.add_argument("--runs", nargs="+", help="side: held-out 2 P4 runs; exclusion, pooled: the primary P3 "
                                                      "run; rq2: P3 runs, primary first")
    arg_parser.add_argument("--page-sizes", default=str(PAGE_SIZES), help="exclusion: page size table")
    arg_parser.add_argument("--final", action="store_true", help="allow held-out data (final evaluation only)")
    arg_parser.add_argument("--test", action="store_true", help="outputs to data/results/tests/, record to runs/tests/")
    arg_parser.add_argument("--machine", default="laptop")
    args = arg_parser.parse_args()
    if not args.runs or (args.step in ("side", "pooled") and not args.held_out_1):
        arg_parser.error(f"{args.step} needs --runs{' and --held-out-1' if args.step in ('side', 'pooled') else ''}")

    logger, extra = CostLogger(), None
    with logger.stage(f"h2_analyse:{args.step}"):
        if args.step == "side":
            table, stack = side(args.held_out_1, args.runs, args.final)
        elif args.step == "exclusion":
            table, stack = exclusion(args.runs[0], Path(args.page_sizes).resolve(), args.final)
        elif args.step == "pooled":
            table, stack, extra = pooled(args.held_out_1, args.runs[0], args.final)
        else:
            table, stack = rq2(args.runs, args.final)
    run_id = (new_test_run_id if args.test else new_run_id)(4, "H2")
    folder = RESULTS / ("tests" if args.test else "h2")
    folder.mkdir(parents=True, exist_ok=True)
    outputs = [folder / f"{'test_' if args.test else ''}{run_id}_{args.step}.csv"]
    if extra is not None:
        outputs.append(folder / f"{'test_' if args.test else ''}{run_id}_{args.step}_documents.csv")
    if any(path.exists() for path in outputs):
        raise FileExistsError(f"output exists: {outputs}")
    table.to_csv(outputs[0], index=False)
    if extra is not None:
        extra.to_csv(outputs[1], index=False)
    stack = {"analysis": f"h2_{args.step}", **stack, "tuning_winner": TUNING_WINNER, "resamples": RESAMPLES,
             "level": LEVEL, "seed": SEED, "final": args.final, "test": args.test}
    record = build_manifest(run_id, "v1.2", stack, [], outputs, logger.summary(), args.machine)
    if args.test:
        record_path = RUNS_DIR / "tests" / f"test_h2_analyse_{run_id}.json"
        if record_path.exists():
            raise FileExistsError(f"test record already exists: {record_path}")
        record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    else:
        record_path = write_manifest(record)
    pd.set_option("display.width", 240)
    print(f"{table.round(3).to_string(index=False)}\n\n{json.dumps({key: value for key, value in stack.items() if key not in ('analysis',)})}"
          f"\nrun {run_id} | record: {project_path(record_path)}")


if __name__ == "__main__":
    main()
