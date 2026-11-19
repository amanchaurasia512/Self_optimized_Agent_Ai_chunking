"""Extension analysis (spec v1.2: Extension design note, its dated additions and the clarification of 2026-11-19).
Tuning only. (a) each new setup against the tuning best single, paired document bootstrap, S10 tie, Holm over the 6;
(b) RQ1 extension: p4 on the primary choice set plus the new setups, after reproducing the original primary result;
(c) both without the Indian documents; (d) table questions (OHR-Bench, Docling), descriptive. Writes a run record."""
import argparse
import copy
import time
from itertools import combinations

import numpy as np
import pandas as pd

from scripts.p3_sanity import table_questions
from scripts.p4_analyse import analyse, in_scope, question_matrix, resampled_means, tied_with_best
from scripts.robust_no_indian import EXCLUDED_SOURCE, ORIGINAL_RUN, PRIMARY_FILE
from scripts.rq5_parser_compare import holm
from src.common.cost_logger import CostLogger
from src.common.manifest import build_manifest, new_run_id, write_manifest
from src.common.paths import RESULTS
from src.common.split import tuning_ids
from src.eval.stats import LEVEL, RESAMPLES, SEED

TUNING_RUN, EXTENSION_RUN = "P3-LOCAL-20261105-4", "P3-EXT-KN01-20261118-2"
REFERENCE = "docling/langchain_recursive_size256_overlap0_noprefix"
MAIN_BUDGET, BUDGETS = 1250, [1250, 750, 2000]
EXPECTED = {"all": (REFERENCE, 0.802, -0.001, -0.032, 0.030),  # tuning primary, P4-NOINDIAN-20261114-1
            "without Indian": ("docling/langchain_recursive_size512_overlap0_noprefix", 0.791, -0.014, -0.044, 0.014)}
TABLE_SOURCE = "OHR-Bench"
TABLE_SETUPS = ["docling/dynamic_token_noprefix", "docling/section_table_prefix",
                "docling/method1_tree_T384_noprefix", "docling/method1_tree_T512_noprefix"]
OUTPUT = RESULTS / "ext"


def load(run):
    path = RESULTS / "p3" / f"{run}.csv.gz"
    frame = pd.read_csv(path)
    frame = frame[(frame["retriever"] == "hybrid") & (frame["source"].str.lower() != "qasper")]
    sealed = sorted(set(frame["doc_id"]) - tuning_ids())
    if sealed:
        raise SystemExit(f"{run} holds documents outside the tuning split: {sealed}")
    return path, frame.assign(setup=frame["parser"] + "/" + frame["setting"])


def at_budget(frame, budget):
    """p4_analyse's filter: one budget; at 750 only setups whose largest chunk fits."""
    return frame[(frame["budget"] == budget) & ((budget != 750) | frame["fits_750"])]


def interval(values):
    return np.quantile(values, [(1 - LEVEL) / 2, (1 + LEVEL) / 2])


def versus_reference(frame, new_setups, budget):
    """(a) per new setup: (new - reference) on shared questions; interval, two-sided bootstrap p and the S10 tie from
    the same resamples."""
    frame, rng, rows = at_budget(frame, budget), np.random.default_rng(SEED), []
    for setup in new_setups:
        pair = frame[frame["setup"].isin([REFERENCE, setup])]
        if setup not in set(pair["setup"]):
            rows.append({"budget": budget, "setup": setup, "note": "does not fit 750"})
            continue
        questions = question_matrix(pair, sorted(pair["setting"].unique()))[0]
        docs = questions.groupby(level="doc_id").mean()[[REFERENCE, setup]]
        tied = bool(tied_with_best(docs, copy.deepcopy(rng)).all())
        difference = (lambda means: means[:, 1] - means[:, 0])(resampled_means(docs.to_numpy(), rng))
        low, high = interval(difference)
        rows.append({"budget": budget, "setup": setup, "documents": len(docs), "questions": len(questions),
                     "reference_recall": docs[REFERENCE].mean(), "recall": docs[setup].mean(),
                     "difference": docs[setup].mean() - docs[REFERENCE].mean(), "low": low, "high": high,
                     "p": min(1.0, 2 * min((difference <= 0).mean(), (difference >= 0).mean())), "tied": tied, "note": ""})
    table = pd.DataFrame(rows)
    if budget == MAIN_BUDGET:
        table["holm_p"] = holm(table["p"].to_numpy())
    return table


def scope_result(frame, settings, rng):
    """One p4 scope (zero cost tables, as robust_no_indian): best single, ties, split-half oracle, gap, go/no-go."""
    questions = question_matrix(frame, settings)[0]
    zeros = pd.DataFrame(0.0, index=questions.index.get_level_values("doc_id").unique(), columns=questions.columns)
    single, per_doc, setups = analyse(questions, zeros, zeros, rng)
    low, high = interval(resampled_means(per_doc[["gap"]].to_numpy(), rng)[:, 0])
    row = {"setups": questions.shape[1], "documents": len(per_doc), "questions": len(questions), "best_single": single,
           "best_recall": setups.loc[single, "recall"], "tied": int(setups["tied_with_best"].sum()),
           "oracle": per_doc["oracle"].mean(), "gap": per_doc["gap"].mean(), "gap_low": low, "gap_high": high,
           "decision": "GO" if low > 0 else "NO-GO"}
    return row, setups[["recall", "tied_with_best"]]


def rq1(old, new, primary, variant):
    """(b) full, original, primary replayed on the tuning scores with one seed-42 generator (checked against the
    original result), then primary + new setups as the next scope on the same generator."""
    rng, old, new = np.random.default_rng(SEED), at_budget(old, MAIN_BUDGET), at_budget(new, MAIN_BUDGET)
    original = set(in_scope(pd.read_csv(RESULTS / "p3" / f"{ORIGINAL_RUN}.csv.gz", usecols=["setting"])["setting"].unique()))
    full = in_scope(old["setting"].unique())
    scopes = {"full": (old, full), "original": (old, [setting for setting in full if setting in original]),
              "primary": (old, [setting for setting in full if setting in primary]),
              "primary + new": (pd.concat([old, new]), sorted({*primary, *new["setting"]}))}
    rows, setups = {}, None
    for scope, (frame, settings) in scopes.items():
        rows[scope], setups = scope_result(frame, settings, rng)
    found = rows["primary"]
    found = (found["best_single"], *(round(found[key], 3) for key in ("best_recall", "gap", "gap_low", "gap_high")))
    if found != EXPECTED[variant]:
        raise SystemExit(f"{variant}: original primary result not reproduced: {found} != {EXPECTED[variant]}")
    return pd.DataFrame.from_dict(rows, orient="index").loc[["primary", "primary + new"]], setups


def table_question_result(old, new):
    """(d) Docling OHR-Bench table questions (p3_sanity rule), four setups on shared questions, descriptive."""
    frame = at_budget(pd.concat([old, new]), MAIN_BUDGET)
    frame = frame[(frame["parser"] == "docling") & (frame["source"] == TABLE_SOURCE)]
    chosen = table_questions(set(frame["doc_id"]))
    frame = frame[frame["question_id"].isin(chosen) & frame["setup"].isin(TABLE_SETUPS)]
    questions = question_matrix(frame, sorted(frame["setting"].unique()))[0][TABLE_SETUPS]
    docs = questions.groupby(level="doc_id").mean()
    means = pd.DataFrame(resampled_means(docs.to_numpy(), np.random.default_rng(SEED)), columns=TABLE_SETUPS)
    setups = pd.DataFrame([{"setup": setup, "documents": len(docs), "questions": len(questions),
                            "recall": docs[setup].mean(), **dict(zip(["low", "high"], interval(means[setup])))}
                           for setup in TABLE_SETUPS])
    pairs = pd.DataFrame([{"first": first, "second": second, "difference": docs[first].mean() - docs[second].mean(),
                           **dict(zip(["low", "high"], interval(means[first] - means[second])))}
                          for first, second in combinations(TABLE_SETUPS, 2)])
    return setups, pairs, len(chosen)


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--machine", default="laptop")
    args = arg_parser.parse_args()
    started, logger = time.perf_counter(), CostLogger()

    (old_path, old), (new_path, new) = load(TUNING_RUN), load(EXTENSION_RUN)
    if set(old["setup"]) & set(new["setup"]):
        raise SystemExit(f"setups in both score runs: {sorted(set(old['setup']) & set(new['setup']))}")
    primary = sorted({setup.split("/")[1] for setup in pd.read_csv(PRIMARY_FILE, index_col=0).index})
    new_setups = sorted(new["setup"].unique())
    variants = {"all": (old, new), "without Indian": (old[old["source"] != EXCLUDED_SOURCE], new[new["source"] != EXCLUDED_SOURCE])}

    comparisons, rq1_rows, rq1_setups = {}, {}, {}
    for variant, (old_part, new_part) in variants.items():
        with logger.stage(f"versus_reference:{variant}"):
            comparisons[variant] = pd.concat([versus_reference(pd.concat([old_part, new_part]), new_setups, budget)
                                              for budget in BUDGETS], ignore_index=True)
        with logger.stage(f"rq1:{variant}"):
            rq1_rows[variant], rq1_setups[variant] = rq1(old_part, new_part, primary, variant)
    with logger.stage("table_questions"):
        table_setups, table_pairs, table_count = table_question_result(old, new)

    tables = {"versus_reference": pd.concat([table.assign(variant=variant) for variant, table in comparisons.items()],
                                            ignore_index=True),
              "rq1": pd.concat(rq1_rows, names=["variant", "scope"]),
              "rq1_setups": pd.concat(rq1_setups, names=["variant", "setup"]),
              "table_questions": table_setups, "table_pairs": table_pairs}
    run_id = new_run_id(4, "EXT")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    outputs = [OUTPUT / f"{run_id}_{name}.csv" for name in tables]
    for path, table in zip(outputs, tables.values()):
        table.to_csv(path, index=not isinstance(table.index, pd.RangeIndex))
    seconds = time.perf_counter() - started
    stack = {"analysis": "ext_analyse", "scores_runs": [TUNING_RUN, EXTENSION_RUN], "original_run": ORIGINAL_RUN,
             "retriever": "hybrid", "budgets": BUDGETS, "main_budget": MAIN_BUDGET, "reference": REFERENCE,
             "new_setups": new_setups, "primary_settings_from": PRIMARY_FILE.name, "excluded_source": EXCLUDED_SOURCE,
             "table_rule": "p3_sanity.table_questions, source OHR-Bench", "table_questions_found": table_count,
             "table_setups": TABLE_SETUPS, "expected_primary": EXPECTED, "seed": SEED, "resamples": RESAMPLES,
             "level": LEVEL, "wall_seconds": round(seconds, 1),
             "summary": {f"{variant} / {scope}": {key: (value.item() if hasattr(value, "item") else value)
                                                 for key, value in row.items()}
                         for (variant, scope), row in tables["rq1"].iterrows()}}
    manifest_path = write_manifest(build_manifest(run_id, "v1.2", stack, [old_path, new_path, PRIMARY_FILE], outputs,
                                                  logger.summary(), args.machine))

    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 60)
    shown = tables["versus_reference"].drop(columns="p")
    print(f"(a)+(c) new setups vs {REFERENCE} (hybrid; Holm over the 6 at 1,250 per variant)\n"
          f"{shown.round(3).to_string(index=False)}\n\n(b)+(c) RQ1 extension (hybrid, Recall@1,250; primary reproduced)\n"
          f"{tables['rq1'].to_string()}\n\nprimary + new: setups\n{tables['rq1_setups'].round(3).to_string()}\n\n"
          f"(d) table questions ({TABLE_SOURCE}, Docling; rule found {table_count}), Recall@1,250, descriptive\n"
          f"{table_setups.round(3).to_string(index=False)}\n\n{table_pairs.round(3).to_string(index=False)}\n\n"
          f"run {run_id} | manifest: {manifest_path} | {seconds:.1f} s")


if __name__ == "__main__":
    main()
