"""P4 analysis (spec v1.2, amended): from one P3 score run, the best single setup (top by mean recall among the
setups not clearly worse than it, paired document bootstrap), the per-document oracle by split-half cross-fitting,
the gap with its interval, and Pareto fronts of recall against index tokens and against chunk count. Run on the full
grid and on the settings of an earlier run (the original grid)."""
import argparse
import json
import re
from collections import Counter

import numpy as np
import pandas as pd

from src.chunk.chunkers import CHUNKERS
from src.common.cost_logger import CostLogger
from src.common.manifest import PROJECT_ROOT, build_manifest, new_run_id, write_manifest
from src.eval.stats import LEVEL, RESAMPLES, SEED

RESULTS, CHUNKS = PROJECT_ROOT / "data" / "results", PROJECT_ROOT / "data" / "chunks"
SUPERSEDED = re.compile(r"_v\d+$")
SPLITS = 200


def in_scope(settings):
    """Benchmark settings: sanity chunkers (registry flag) and superseded versions (*_vNN) left out."""
    sanity = tuple(name for name, entry in CHUNKERS.items() if entry.get("sanity"))
    return sorted(setting for setting in settings if not setting.startswith(sanity) and not SUPERSEDED.search(setting))


def question_matrix(frame, settings):
    """Questions x setups (parser/setting) of recall, keeping only questions scored by every setup, and the left-out
    questions with how many setups lack them and on which parsers."""
    frame = frame[frame["setting"].isin(settings)]
    frame = frame.assign(setup=frame["parser"] + "/" + frame["setting"])
    table = frame.pivot_table(index=["doc_id", "question_id"], columns="setup", values="recall")
    missing = table.isna()
    left_out = pd.DataFrame([{"doc_id": doc, "question_id": question, "missing_in": int(row.sum()),
                              "parsers": " ".join(sorted({setup.split("/")[0] for setup in row.index[row]}))}
                             for (doc, question), row in missing[missing.any(axis=1)].iterrows()],
                            columns=["doc_id", "question_id", "missing_in", "parsers"])
    return table.dropna(), left_out


def index_cost(setups, docs):
    """Documents x setups of index tokens (chunk + prefix tokens) and of chunk counts."""
    tokens, counts = {}, {}
    for setup in setups:
        parser, setting = setup.split("/")
        files = {doc: json.loads((CHUNKS / parser / setting / f"{doc}.json").read_text(encoding="utf-8"))["chunks"]
                 for doc in docs}
        tokens[setup] = {doc: sum(chunk["token_count"] + chunk["prefix_token_count"] for chunk in chunks)
                         for doc, chunks in files.items()}
        counts[setup] = {doc: len(chunks) for doc, chunks in files.items()}
    return pd.DataFrame(tokens), pd.DataFrame(counts)


def resampled_means(values, rng):
    """Bootstrap means of the rows of values (rows are the resampled units), RESAMPLES x columns."""
    units = len(values)
    weights = rng.multinomial(units, np.full(units, 1 / units), size=RESAMPLES)
    return weights @ values / units


def tied_with_best(frame, rng):
    """Setups whose paired bootstrap interval of (best - setup) reaches 0 (S10); the best is tied with itself."""
    values = frame.to_numpy()
    best = int(values.mean(axis=0).argmax())
    means = resampled_means(values, rng)
    lower = np.quantile(means[:, [best]] - means, (1 - LEVEL) / 2, axis=0)
    return pd.Series(lower <= 0, index=frame.columns)


def split_half_oracle(doc_questions, rng):
    """Oracle without selection luck: choose the best setup on a random half of the document's questions, measure it
    on the other half; the mean over SPLITS random splits, and the setup chosen most often."""
    values, units = doc_questions.to_numpy(), len(doc_questions)
    orders = rng.permuted(np.tile(np.arange(units), (SPLITS, 1)), axis=1)
    scores, chosen = [], Counter()
    for order in orders:
        choose, measure = order[:units // 2], order[units // 2:]
        pick = int(values[choose].mean(axis=0).argmax())
        scores.append(values[measure, pick].mean())
        chosen[doc_questions.columns[pick]] += 1
    return float(np.mean(scores)), chosen.most_common(1)[0][0]


def pareto(quality, cost):
    """Setups that no other setup beats on both quality (higher) and cost (lower)."""
    return pd.Series({setup: not ((quality >= quality[setup]) & (cost <= cost[setup])
                                  & ((quality > quality[setup]) | (cost < cost[setup]))).any() for setup in quality.index})


def analyse(questions, tokens, counts, rng):
    docs = questions.groupby(level="doc_id").mean()
    tokens, counts = tokens.loc[docs.index, docs.columns], counts.loc[docs.index, docs.columns]
    tied = tied_with_best(docs, rng)
    single = docs.mean().idxmax()
    rows = []
    for doc, doc_questions in questions.groupby(level="doc_id"):
        oracle, chosen = (split_half_oracle(doc_questions, rng) if len(doc_questions) > 1
                          else (docs.loc[doc, single], single))
        rows.append({"doc_id": doc, "questions": len(doc_questions), "best_single": docs.loc[doc, single],
                     "oracle": oracle, "most_chosen": chosen, "raw_max": docs.loc[doc].max()})
    per_doc = pd.DataFrame(rows).set_index("doc_id")
    per_doc["gap"], per_doc["raw_gap"] = per_doc["oracle"] - per_doc["best_single"], per_doc["raw_max"] - per_doc["best_single"]
    setups = pd.DataFrame({"recall": docs.mean(), "index_tokens": tokens.mean(), "chunks": counts.mean(), "tied_with_best": tied})
    setups["pareto_tokens"] = pareto(setups["recall"], setups["index_tokens"])
    setups["pareto_chunks"] = pareto(setups["recall"], setups["chunks"])
    return single, per_doc, setups.sort_values("recall", ascending=False)


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--run", required=True, help="P3 score run id, e.g. P3-LOCAL-20261105-4")
    arg_parser.add_argument("--original-run", required=True, help="earlier P3 run whose settings form the original grid")
    arg_parser.add_argument("--retriever", default="hybrid")
    arg_parser.add_argument("--budget", type=int, default=1250)
    arg_parser.add_argument("--machine", default="laptop")
    arg_parser.add_argument("--run-source", default="LOCAL")
    arg_parser.add_argument("--settings", nargs="*", help="setting names of the pre-registered primary choice set")
    args = arg_parser.parse_args()

    scores = RESULTS / "p3" / f"{args.run}.csv.gz"
    frame = pd.read_csv(scores)
    frame = frame[(frame["retriever"] == args.retriever) & (frame["budget"] == args.budget)
                  & (frame["source"].str.lower() != "qasper") & ((args.budget != 750) | frame["fits_750"])]
    original = set(in_scope(pd.read_csv(RESULTS / "p3" / f"{args.original_run}.csv.gz", usecols=["setting"])["setting"].unique()))
    full = in_scope(frame["setting"].unique())
    scopes = {"full": full, "original": [setting for setting in full if setting in original]}
    if args.settings:
        unknown = sorted(set(args.settings) - set(full))
        if unknown:
            raise ValueError(f"primary settings not in this run: {unknown}")
        scopes["primary"] = [setting for setting in full if setting in set(args.settings)]
    run_id, logger, rng, outputs, summary = new_run_id(4, args.run_source), CostLogger(), np.random.default_rng(SEED), [], {}
    output = RESULTS / "p4"
    output.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 240)
    pd.set_option("display.max_colwidth", 60)
    pd.set_option("display.max_rows", 200)
    for scope, settings in scopes.items():
        with logger.stage(f"analyse:{scope}"):
            questions, left_out = question_matrix(frame, settings)
            docs = questions.index.get_level_values("doc_id").unique()
            tokens, counts = index_cost(questions.columns, docs)
            single, per_doc, setups = analyse(questions, tokens, counts, rng)
            low, high = np.quantile(resampled_means(per_doc[["gap"]].to_numpy(), rng)[:, 0], [(1 - LEVEL) / 2, (1 + LEVEL) / 2])
        for name, table in (("documents", per_doc), ("setups", setups), ("left_out", left_out)):
            path = output / f"{run_id}_{scope}_{name}.csv"
            table.to_csv(path)
            outputs.append(path)
        dropped_docs = sorted(set(left_out["doc_id"]) - set(docs))
        summary[scope] = {"setups": questions.shape[1], "documents": len(per_doc), "questions": len(questions),
                          "questions_left_out": len(left_out), "documents_left_out": dropped_docs,
                          "best_single": single, "best_single_recall": setups.loc[single, "recall"],
                          "tied_with_best": int(setups["tied_with_best"].sum()), "oracle": per_doc["oracle"].mean(),
                          "raw_max_oracle": per_doc["raw_max"].mean(), "gap": per_doc["gap"].mean(),
                          "gap_interval": [low, high], "raw_gap": per_doc["raw_gap"].mean()}
        print(f"\n=== {scope}: {questions.shape[1]} setups | {len(per_doc)} documents | {len(questions)} questions\n"
              f"left out: {len(left_out)} questions, lacking on parser(s) {left_out['parsers'].value_counts().to_dict()} | "
              f"documents left out entirely: {dropped_docs or 'none'}\n"
              f"best single (top by mean): {single} {setups.loc[single, 'recall']:.3f} | "
              f"statistically tied with it: {int(setups['tied_with_best'].sum())} of {len(setups)}\n"
              f"oracle (split-half, {SPLITS} splits): {per_doc['oracle'].mean():.3f} | raw max: {per_doc['raw_max'].mean():.3f}\n"
              f"gap: {per_doc['gap'].mean():.3f} [{low:.3f}, {high:.3f}] | raw gap: {per_doc['raw_gap'].mean():.3f}\n\n"
              f"{per_doc.round(3).to_string()}\n\nPareto front, recall vs chunk count:\n"
              f"{setups[setups['pareto_chunks']].round(3).to_string()}\n\nPareto front, recall vs index tokens:\n"
              f"{setups[setups['pareto_tokens']].round(3).to_string()}")

    stack = {"analysis": "p4_v2", "scores_run": args.run, "original_run": args.original_run, "retriever": args.retriever,
             "budget": args.budget, "metric": "recall", "resamples": RESAMPLES, "level": LEVEL, "seed": SEED,
             "splits": SPLITS, "cost": "index tokens (chunk + prefix) and chunk count per document; LLM tokens not included",
             "summary": summary}
    manifest_path = write_manifest(build_manifest(run_id, "v1.2", stack, [scores], outputs, logger.summary(), args.machine))
    print(f"\nrun {run_id} | manifest: {manifest_path}")


if __name__ == "__main__":
    main()