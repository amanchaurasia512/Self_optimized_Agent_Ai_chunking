"""Held-out set 2 gold, frozen drop rule (spec v1.2 "Held-out set 2: gold rule amendment", 2026-11-23): applies
P1 judge() with the frozen threshold (configs/gold_drop_rule.json) to the stored placements of
P1-H2-GOLD-20261123-1. No new threshold, no re-placement. A page is placed if it has placements and judge() keeps
every piece; pages with no stored placement (no words in box, parser page empty) are not placed. Primary: a query
keeps gold only if all its score-2 pages are placed; sensitivity: at least one.
Each output row is the stored row plus: drop_rule_keep (judge() of the piece), page_keep, keep_primary,
keep_sensitivity, drop_reason (under the drop rule) and certain_only (the stored certain flag). "certain" is set to
keep_primary, so the P3 filter certain == True selects the primary gold.
Sealed split: refuses without --final, before reading any gold file. Never overwrites.
- inputs:  data/heldout2/queries.jsonl, data/heldout2/box_evidence.jsonl, data/gold/h2_spans_<parser>.jsonl
- outputs: data/gold/h2_spans_droprule_<parser>.jsonl, runs/P1-H2-DROPRULE-<date>-<n>.json
Run from the repo root: python -m scripts.h2_gold_droprule --final"""
import argparse
import json
from collections import Counter, defaultdict

import pandas as pd

from src.common.cost_logger import CostLogger
from src.common.manifest import PROJECT_ROOT, build_manifest, new_run_id, write_manifest
from src.common.split import tuning_ids
from src.gold.matching import DROP_RULE_FILE
from scripts.h2_gold_boxes import EVIDENCE_FILE, EXTRACTION_RUNS
from scripts.heldout2_vidore_register import QUERIES_FILE
from scripts.p1_gold_match import GOLD_DIR, judge

SPEC_VERSION = "v1.2"
GOLD_RUN = "P1-H2-GOLD-20261123-1"


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def question_id(query):
    return f"vidore_{query['corpus']}::{query['query_id']}"


def page_reason(rows, evidence):
    """None when the page is placed under the drop rule, else why not."""
    if not rows:
        return "no words in box" if not evidence.strip() else "parser page empty"
    if any(row["start"] is None for row in rows):
        return "not placed"
    return None if all(row["drop_rule_keep"] for row in rows) else "fuzzy below threshold"


def apply_rule(parser, queries, evidence, threshold):
    pages = defaultdict(list)
    for row in read_jsonl(GOLD_DIR / f"h2_spans_{parser}.jsonl"):
        span = (row["start"], row["end"]) if row["start"] is not None else None
        pages[(row["question_id"], row["evidence_index"])].append(
            {**row, "certain_only": row["certain"], "drop_rule_keep": judge(row, span, None, None, threshold)["keep"]})
    output, summary = [], []
    for query in queries:
        key = question_id(query)
        reasons = [page_reason(pages[(key, index)], evidence[(key, index)]) for index in range(len(query["pages"]))]
        keep_all, keep_any = all(reason is None for reason in reasons), any(reason is None for reason in reasons)
        summary.append({"parser": parser, "corpus": query["corpus"], "question_id": key, "keep_primary": keep_all,
                        "keep_sensitivity": keep_any, "reasons": [reason for reason in reasons if reason]})
        output += [{**row, "page_keep": reason is None, "keep_primary": keep_all, "keep_sensitivity": keep_any,
                    "drop_reason": reason, "certain": keep_all}
                   for index, reason in enumerate(reasons) for row in pages[(key, index)]]
    return output, summary


def report(summary):
    """Counts only: no question, evidence or document text is printed."""
    table = pd.DataFrame(summary)
    grouped = table.groupby(["parser", "corpus"]).agg(questions_in=("question_id", "size"),
                                                      gold_primary=("keep_primary", "sum"),
                                                      gold_sensitivity=("keep_sensitivity", "sum"))
    grouped["dropped_primary"] = grouped["questions_in"] - grouped["gold_primary"]
    grouped["drop_rate_primary"] = (grouped["dropped_primary"] / grouped["questions_in"]).round(3)
    grouped["dropped_sensitivity"] = grouped["questions_in"] - grouped["gold_sensitivity"]
    grouped["drop_rate_sensitivity"] = (grouped["dropped_sensitivity"] / grouped["questions_in"]).round(3)
    print(grouped.to_string())
    reasons = Counter((row["parser"], row["corpus"], reason) for row in summary for reason in row["reasons"])
    print("failing pages by reason (all questions):")
    print("\n".join(f"  {parser} {corpus}: {reason} {count}" for (parser, corpus, reason), count in sorted(reasons.items())))
    wide = table.pivot_table(index=["corpus", "question_id"], columns="parser", values=["keep_primary", "keep_sensitivity"])
    for column in ("keep_primary", "keep_sensitivity"):
        both = wide[column].all(axis=1) if wide[column].shape[1] > 1 else wide[column].iloc[:, 0].astype(bool)
        print(f"questions with gold in every parser ({column}):", both.groupby(level="corpus").sum().to_dict(),
              "| total", int(both.sum()))


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--parsers", nargs="+", default=list(EXTRACTION_RUNS), choices=list(EXTRACTION_RUNS))
    arg_parser.add_argument("--final", action="store_true", help="allow held-out documents (final evaluation only)")
    args = arg_parser.parse_args()

    queries = read_jsonl(QUERIES_FILE)
    sealed = sorted({query["doc_id"] for query in queries} - tuning_ids())
    if sealed and not args.final:
        raise PermissionError(f"held-out documents need --final (final evaluation only): {len(sealed)}, e.g. {sealed[:3]}")
    outputs = [GOLD_DIR / f"h2_spans_droprule_{parser}.jsonl" for parser in args.parsers]
    existing = [str(path) for path in outputs if path.exists()]
    if existing:
        raise FileExistsError(f"outputs exist, never overwritten: {existing}")
    inputs = [QUERIES_FILE, EVIDENCE_FILE, *(GOLD_DIR / f"h2_spans_{parser}.jsonl" for parser in args.parsers)]
    if not (PROJECT_ROOT / "runs" / f"{GOLD_RUN}.json").exists() or not all(path.exists() for path in inputs):
        raise SystemExit(f"stored placements of {GOLD_RUN} missing")

    rule = json.loads(DROP_RULE_FILE.read_text())
    evidence = {(row["question_id"], row["evidence_index"]): row["evidence"] for row in read_jsonl(EVIDENCE_FILE)}
    logger, summary = CostLogger(), []
    for parser, path in zip(args.parsers, outputs):
        with logger.stage(f"drop_rule:{parser}"):
            rows, parser_summary = apply_rule(parser, queries, evidence, rule["threshold"])
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        summary += parser_summary

    stack = {"gold_rule": "P1 judge() with the frozen drop rule", "threshold": rule["threshold"],
             "placements_from": GOLD_RUN}
    manifest = build_manifest(new_run_id(1, "H2-DROPRULE"), SPEC_VERSION, stack, inputs, outputs, logger.summary(),
                              "laptop", config_path=DROP_RULE_FILE)
    print("manifest:", write_manifest(manifest))
    report(summary)


if __name__ == "__main__":
    main()
