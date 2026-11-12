"""Size curve by source (spec v1.2, reporting): recall against measured chunk size within each source, to check
whether the pooled result holds per document type. Hybrid retriever, main questions (QASPER excluded), questions
scored by every setting of a parser, document means then source means. Runs holding held-out documents need --final."""
import argparse

import pandas as pd

from scripts.p4_analyse import in_scope, index_cost, question_matrix
from src.common.cost_logger import CostLogger
from src.common.manifest import PROJECT_ROOT, build_manifest, new_run_id, write_manifest

RESULTS = PROJECT_ROOT / "data" / "results" / "p3"
SEALED = "held_out"
EXCLUDED = {"QASPER"}
COLUMNS = ["parser", "setting", "doc_id", "question_id", "source", "retriever", "budget", "recall"]


def measured_sizes(questions):
    """Setups -> mean over documents of index tokens per chunk."""
    docs = sorted(questions.index.get_level_values(0).unique())
    tokens, counts = index_cost(questions.columns, docs)
    return (tokens / counts).mean()


def source_means(questions, sources):
    """Sources x setups of recall: question means per document, then document means per source."""
    docs = questions.groupby(level=0).mean()
    return docs.groupby(sources.reindex(docs.index)).mean(), sources.reindex(docs.index).value_counts()


def parser_curves(frame, parser):
    subset = frame[frame["parser"] == parser]
    sources = subset.drop_duplicates("doc_id").set_index("doc_id")["source"]
    matrices = {budget: question_matrix(subset[subset["budget"] == budget], in_scope(subset["setting"].unique()))[0]
                for budget in sorted(subset["budget"].unique())}
    sizes = measured_sizes(next(iter(matrices.values())))
    rows, summary = [], []
    for budget, questions in matrices.items():
        means, documents = source_means(questions, sources)
        for source, recalls in means.iterrows():
            best = recalls.idxmax()
            summary.append({"parser": parser, "budget": budget, "source": source, "documents": documents[source],
                            "best_setting": best.split("/", 1)[1], "best_size": round(sizes[best]),
                            "best_recall": round(recalls[best], 3),
                            "spearman_size_recall": round(recalls.corr(sizes[recalls.index], method="spearman"), 2)})
            rows += [{"parser": parser, "budget": budget, "source": source, "setting": setup.split("/", 1)[1],
                      "chunk_size": round(sizes[setup], 1), "recall": recall} for setup, recall in recalls.items()]
    return rows, summary


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--run", default="P3-LOCAL-20261105-4", help="P3 run whose scores are read")
    arg_parser.add_argument("--final", action="store_true", help="allow a run holding held-out documents")
    arg_parser.add_argument("--machine", default="laptop")
    args = arg_parser.parse_args()

    split_file, scores = PROJECT_ROOT / "pdfs" / "split.csv", RESULTS / f"{args.run}.csv.gz"
    splits = pd.read_csv(split_file).set_index("doc_id")["split"]
    frame = pd.read_csv(scores, usecols=COLUMNS)
    frame = frame[(frame["retriever"] == "hybrid") & ~frame["source"].isin(EXCLUDED)]
    if frame["doc_id"].map(splits).fillna("").str.startswith(SEALED).any() and not args.final:
        raise SystemExit(f"{args.run} holds held-out documents: rerun with --final")

    logger = CostLogger()
    with logger.stage("size_by_source"):
        results = [parser_curves(frame, parser) for parser in sorted(frame["parser"].unique())]
    rows = pd.DataFrame([row for parser_rows, parser_summary in results for row in parser_rows])
    summary = pd.DataFrame([row for parser_rows, parser_summary in results for row in parser_summary])
    outputs = [RESULTS / f"size_by_source_{args.run}.csv", RESULTS / f"size_by_source_summary_{args.run}.csv"]
    rows.to_csv(outputs[0], index=False)
    summary.to_csv(outputs[1], index=False)
    run_id = new_run_id(3, "SIZESRC")
    stack = {"analysis": "size_by_source", "scores_run": args.run, "retriever": "hybrid",
             "excluded_sources": sorted(EXCLUDED), "final": args.final}
    manifest_path = write_manifest(build_manifest(run_id, "v1.2", stack, [split_file, scores], outputs,
                                                  logger.summary(), args.machine))
    print(summary.sort_values(["parser", "budget", "source"]).to_string(index=False))
    print(f"\nrun {run_id} | manifest: {manifest_path}")


if __name__ == "__main__":
    main()