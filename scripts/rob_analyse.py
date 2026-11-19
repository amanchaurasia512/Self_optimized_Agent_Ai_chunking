"""Robustness embedder analysis (spec v1.2 "Robustness embedder: nomic-embed-text-v1.5, design before any code",
2026-11-19): do RQ1, RQ2 and RQ3 hold with nomic as the dense embedder? Tuning documents only, main questions (QASPER
excluded), with and without the Indian documents; each analysis is repeated with the same code on bge-m3.
  RQ1: p4_analyse (best single, ties, split-half oracle, gap, go/no-go) on the 26 primary setups, Recall@1,250,
       hybrid and dense-only; one seed-42 generator per analysis, the same for both embedders.
  RQ2: the pooled size curve of robust_no_indian (Spearman of measured size against recall per parser and budget)
       on the 34 embedded setups; bge-m3 recomputed from P3-LOCAL-20261105-4 on the same 34.
  RQ3: p3_budget_sweep scoring and tests on the four size-swept families at 256 and 1,024 (hybrid with the nomic
       cache): (256 - 1,024) in Recall@1,250, Recall@5 and Lift@5, paired document bootstrap, Holm over the 24;
       bge-m3 from the stored sweep rows (budget_sweep_tuning.csv) through the same compare().
"Holds" (fixed in the note): RQ1 NO-GO; RQ2 every size-recall Spearman negative; RQ3 every tested difference has the
bge-m3 sign (Recall@1,250 > 0, Recall@5 < 0, Lift@5 > 0). There is no --final option: held-out documents are refused."""
import argparse
import json
import time
from datetime import datetime

import numpy as np
import pandas as pd

from scripts.p3_budget_sweep import FAMILIES, LARGE, PARSERS, SMALL, TEST_DOCS, TESTED, compare, setting_name
from scripts.p3_budget_sweep import score as sweep_score
from scripts.p3_score import GOLD, OUTPUT, gold_questions
from scripts.p4_analyse import analyse, question_matrix, resampled_means
from scripts.robust_no_indian import EXCLUDED_SOURCE, PRIMARY_FILE, size_rows
from src.common.cost_logger import CostLogger
from src.common.manifest import PROJECT_ROOT, RUNS_DIR, build_manifest, new_run_id, new_test_run_id, write_manifest
from src.common.split import tuning_ids
from src.eval.embed import CACHE_FOLDERS, EMBEDDERS
from src.eval.stats import LEVEL, RESAMPLES, SEED

BGE_RUN = "P3-LOCAL-20261105-4"
BGE_SWEEP_ROWS, BGE_SWEEP_TESTS = OUTPUT / "budget_sweep_tuning.csv", OUTPUT / "budget_sweep_tuning_tests.csv"
EXPECTED_SIGN = {("budget", 1250, "recall"): 1, ("k", 5, "recall"): -1, ("k", 5, "lift"): 1}
SWEEP_SETTINGS = [setting_name(family, size) for family in FAMILIES for size in (SMALL, LARGE)]
RESULTS = PROJECT_ROOT / "data" / "results"


def primary_settings():
    """The 13 setting names of the 26 primary setups (P4-FINAL-20261106-1_primary_setups.csv, names only)."""
    return sorted({setup.split("/", 1)[1] for setup in pd.read_csv(PRIMARY_FILE, usecols=[0]).iloc[:, 0]})


def robustness_settings():
    """The 17 settings per parser (34 setups): the primary settings and the size-swept families at 1,024."""
    settings = sorted(set(primary_settings()) | {setting_name(family, LARGE) for family in FAMILIES})
    if len(settings) != 17 or not set(SWEEP_SETTINGS) <= set(settings):
        raise ValueError(f"expected 17 settings holding the 8 swept ones: {settings}")
    return settings


def main_scores(path, settings, docs=None):
    """Score rows for the settings (and documents), main questions only; every setup present, tuning documents only."""
    frame, run = pd.read_csv(path), path.name.removesuffix(".csv.gz")
    frame = frame[frame["setting"].isin(settings) & (frame["source"].str.lower() != "qasper")
                  & (frame["doc_id"].isin(docs) if docs is not None else True)]
    if set(frame["doc_id"]) - tuning_ids():
        raise PermissionError(f"{run} holds non-tuning documents: {sorted(set(frame['doc_id']) - tuning_ids())}")
    absent = {parser: sorted(set(settings) - set(frame.loc[frame["parser"] == parser, "setting"])) for parser in PARSERS}
    if any(absent.values()):
        raise ValueError(f"{run} lacks setups: {absent}")
    return frame


def rq1(frame, settings):
    """p4_analyse on the primary setups (Recall@1,250), one seed-42 generator: zero cost tables, since cost does not
    enter ties, best single, oracle or gap."""
    rng = np.random.default_rng(SEED)
    questions, left_out = question_matrix(frame[frame["budget"] == 1250], settings)
    zeros = pd.DataFrame(0.0, index=questions.index.get_level_values("doc_id").unique(), columns=questions.columns)
    single, per_doc, setups = analyse(questions, zeros, zeros, rng)
    low, high = np.quantile(resampled_means(per_doc[["gap"]].to_numpy(), rng)[:, 0], [(1 - LEVEL) / 2, (1 + LEVEL) / 2])
    return {"setups": questions.shape[1], "documents": len(per_doc), "questions": len(questions),
            "questions_left_out": len(left_out), "best_single": single, "best_recall": setups.loc[single, "recall"],
            "tied": int(setups["tied_with_best"].sum()), "oracle": per_doc["oracle"].mean(), "gap": per_doc["gap"].mean(),
            "gap_low": low, "gap_high": high, "go": bool(low > 0)}


def without_indian(frame):
    return frame[frame["source"] != EXCLUDED_SOURCE]


def tested(tests):
    """The 24 tested comparisons with the sign the note expects and whether the difference has it."""
    keys = list(zip(tests["measure"], tests["cut"], tests["value"]))
    tests = tests.assign(expected_sign=[EXPECTED_SIGN.get(key, 0) for key in keys])[tests["tested"]]
    return tests.assign(sign_holds=np.sign(tests["difference"]) == tests["expected_sign"])


def sweep_docs(test):
    """Every tuning document, or for --test the first TEST_DOCS documents with main questions on both parsers."""
    tuning = tuning_ids()
    if not test:
        return tuning
    shared = set.intersection(*({question["doc_id"] for question in gold_questions(parser, tuning)[0].values()
                                 if question["source"].lower() != "qasper"} for parser in PARSERS))
    return set(sorted(shared)[:TEST_DOCS])


def verdicts(rq1_table, rq2_table, rq3_table, embedder):
    """One row per conclusion and variant for the embedder under test, the bge-m3 verdict next to it."""
    rows = []
    for variant in rq1_table["variant"].unique():
        for name in ("bge-m3", embedder):
            one = lambda table: table[(table["variant"] == variant) & (table["embedder"] == name)]
            for retriever, row in one(rq1_table).set_index("retriever").iterrows():
                rows.append({"conclusion": f"RQ1 NO-GO ({retriever})", "variant": variant, "embedder": name,
                             "holds": not row["go"], "detail": f"gap {row['gap']:.3f} [{row['gap_low']:.3f}, {row['gap_high']:.3f}]"})
            spearman = one(rq2_table)["spearman"]
            rows.append({"conclusion": "RQ2 size-recall Spearman < 0 at every budget", "variant": variant, "embedder": name,
                         "holds": bool((spearman < 0).all()), "detail": f"{int((spearman < 0).sum())} of {len(spearman)} negative"})
            signs = one(rq3_table)["sign_holds"]
            rows.append({"conclusion": "RQ3 signs (R@1,250 > 0, R@5 < 0, Lift@5 > 0)", "variant": variant, "embedder": name,
                         "holds": bool(signs.all()), "detail": f"{int(signs.sum())} of {len(signs)} signs as expected"})
    return pd.DataFrame(rows)


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--run", required=True, help="P3 score run with the robustness embedder, e.g. P3-ROB-KN01-...")
    arg_parser.add_argument("--embedder", choices=[name for name in EMBEDDERS if name != "bge-m3"], default="nomic")
    arg_parser.add_argument("--cache", help="default data/embeddings/<embedder folder>")
    arg_parser.add_argument("--test", action="store_true",
                            help=f"--run is a test score run (data/results/tests/); RQ3 on {TEST_DOCS} tuning documents; "
                                 "writes only test_ files under runs/tests/ and data/results/tests/")
    arg_parser.add_argument("--machine", default="laptop")
    args = arg_parser.parse_args()

    embedder, settings, primary = EMBEDDERS[args.embedder], robustness_settings(), primary_settings()
    cache = args.cache or PROJECT_ROOT / "data" / "embeddings" / CACHE_FOLDERS[args.embedder]
    run_id = new_test_run_id(4, "ROB") if args.test else new_run_id(4, "ROB")
    folder = RESULTS / "tests" if args.test else RESULTS / "rob"
    prefix = f"test_rob_{run_id}" if args.test else run_id
    paths = {name: folder / f"{prefix}_{name}.csv" for name in ("rq1", "rq2", "rq3", "rq3_rows", "verdicts")}
    existing = [path for path in paths.values() if path.exists()]
    if existing:
        raise FileExistsError(f"outputs already exist, never overwritten: {existing}")

    start, logger = time.perf_counter(), CostLogger()
    scores_path = (RESULTS / "tests" / f"test_p3_score_{args.run}.csv.gz" if args.test else OUTPUT / f"{args.run}.csv.gz")
    robust = main_scores(scores_path, settings)
    scores = {"bge-m3": main_scores(OUTPUT / f"{BGE_RUN}.csv.gz", settings, set(robust["doc_id"])), args.embedder: robust}
    docs = sweep_docs(args.test)
    with logger.stage("rq3_sweep"):
        sweep = {args.embedder: sweep_score(PARSERS, SWEEP_SETTINGS, docs, cache, embedder)[0]}
    with logger.stage("analyse"):
        stored = pd.read_csv(BGE_SWEEP_ROWS)
        sweep["bge-m3"] = stored[stored["setting"].isin(SWEEP_SETTINGS) & stored["doc_id"].isin(docs)]
        reference = pd.read_csv(BGE_SWEEP_TESTS)
        reproduced = None if args.test else bool(np.allclose(
            compare(sweep["bge-m3"])[["difference", "low", "high"]], reference[["difference", "low", "high"]], rtol=0, atol=1e-12))
        rq1_rows, rq2_rows, rq3_rows = [], [], []
        for name in scores:
            for variant, keep in (("all tuning", lambda frame: frame), ("without Indian", without_indian)):
                frame = keep(scores[name])
                rq1_rows += [{"embedder": name, "variant": variant, "retriever": retriever,
                              **rq1(frame[frame["retriever"] == retriever], primary)} for retriever in ("hybrid", "dense")]
                rq2_rows.append(size_rows(frame[frame["retriever"] == "hybrid"])[0].assign(embedder=name, variant=variant))
                rq3_rows.append(tested(compare(keep(sweep[name]))).assign(embedder=name, variant=variant))
        rq1_table, rq2_table, rq3_table = pd.DataFrame(rq1_rows), pd.concat(rq2_rows), pd.concat(rq3_rows)
        verdict = verdicts(rq1_table, rq2_table, rq3_table, args.embedder)
    folder.mkdir(parents=True, exist_ok=True)
    for name, table in (("rq1", rq1_table), ("rq2", rq2_table), ("rq3", rq3_table), ("rq3_rows", sweep[args.embedder]),
                        ("verdicts", verdict)):
        table.to_csv(paths[name], index=False)
    seconds = time.perf_counter() - start

    excluded = sorted(scores[args.embedder].loc[scores[args.embedder]["source"] == EXCLUDED_SOURCE, "doc_id"].unique())
    stack = {"analysis": "robustness_embedder", "spec_note": "Robustness embedder: nomic-embed-text-v1.5 (2026-11-19)",
             "embedder": embedder, "scores_run": args.run, "bge_m3_scores_run": BGE_RUN,
             "bge_m3_sweep_rows": BGE_SWEEP_ROWS.name, "bge_m3_sweep_reproduced": reproduced,
             "settings": settings, "primary_settings": primary, "sweep_settings": SWEEP_SETTINGS,
             "sweep_documents": sorted(docs), "excluded_source": EXCLUDED_SOURCE, "excluded_documents": excluded,
             "seed": SEED, "resamples": RESAMPLES, "level": LEVEL, "test": args.test,
             "verdicts": verdict[verdict["embedder"] == args.embedder].to_dict("records")}
    inputs = [OUTPUT / f"{BGE_RUN}.csv.gz", scores_path, BGE_SWEEP_ROWS, BGE_SWEEP_TESTS, PRIMARY_FILE,
              *sorted(GOLD.glob("spans_*.jsonl"))]
    manifest = build_manifest(run_id, "v1.2", stack, inputs, list(paths.values()), logger.summary(), args.machine)
    if args.test:
        manifest_path = RUNS_DIR / "tests" / f"test_rob_analyse_{run_id}.json"
        if manifest_path.exists():
            raise FileExistsError(f"test record already exists: {manifest_path}")
        manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    else:
        manifest_path = write_manifest(json.loads(json.dumps(manifest, default=str)))

    pd.set_option("display.width", 250, "display.max_rows", 200, "display.max_columns", 30)
    columns = ["parser", "family", "measure", "cut", "value", "documents", "difference", "low", "high", "holm_p", "sign_holds"]
    print(f"RQ1 (primary, Recall@1,250)\n{rq1_table.round(3).to_string(index=False)}\n\n"
          f"RQ2 (pooled size curve, 34 setups)\n{rq2_table.round(3).to_string(index=False)}\n\n"
          f"RQ3 (256 - 1,024, the 24 tested comparisons)\n"
          f"{rq3_table.set_index(['embedder', 'variant'])[columns].round(3).to_string()}\n\n"
          f"verdicts\n{verdict.to_string(index=False)}\n\n"
          f"bge-m3 sweep tests reproduced from the stored rows: {reproduced} | without Indian leaves out {excluded}\n"
          f"{seconds:.0f} s | saved {folder}/{prefix}_*\nrecord: {manifest_path}")


if __name__ == "__main__":
    main()
