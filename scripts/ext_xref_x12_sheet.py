"""Method 1 v2, X12 precision check (spec v1.2): draw up to --n attached cross-references at random (seed in the run
record) from one method1_xref chunk file and write a sheet for the hand check: correct target / wrong target /
reference to another document. Tuning documents only; no --final."""
import argparse
import json
import random

import pandas as pd

from src.chunk.xref import CHUNKS, PREFIX_SHARE, cross_references
from src.common.manifest import PROJECT_ROOT, RUNS_DIR, build_manifest, new_run_id, new_test_run_id
from src.common.split import tuning_ids

EXTRACTED = PROJECT_ROOT / "data" / "extracted"
JUDGEMENT = "judgement (correct / wrong / other document)"


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--doc", default="indian_d4_rti_act")
    arg_parser.add_argument("--parser", default="docling")
    arg_parser.add_argument("--T", type=int, default=512)
    arg_parser.add_argument("--n", type=int, default=30)
    arg_parser.add_argument("--seed", type=int, default=20261118)
    arg_parser.add_argument("--run-source", required=True, help="e.g. LOCAL; TEST with --test")
    arg_parser.add_argument("--test", action="store_true", help="read data/chunks/tests/, write sheet and record to runs/tests/")
    args = arg_parser.parse_args()

    if args.doc not in tuning_ids():
        raise PermissionError(f"tuning documents only: {args.doc}")
    extracted_path = EXTRACTED / args.parser / f"{args.doc}.json"
    chunk_path = (CHUNKS / "tests" if args.test else CHUNKS) / args.parser / f"method1_xref_T{args.T}_noprefix" / f"{args.doc}.json"
    document = json.loads(extracted_path.read_text(encoding="utf-8"))
    chunks = json.loads(chunk_path.read_text(encoding="utf-8"))["chunks"]
    prefixes, report, details = cross_references(document, [(chunk["start_char"], chunk["end_char"]) for chunk in chunks],
                                                 int(PREFIX_SHARE * args.T))
    if prefixes != [chunk["prefix"] for chunk in chunks]:
        raise ValueError(f"the references recomputed now differ from the prefixes in {chunk_path}")
    attached = [item for item in details if item["status"] == "attached"]
    sample = random.Random(args.seed).sample(attached, min(args.n, len(attached)))
    text = document["text"]
    sheet = pd.DataFrame([{"chunk": f"c{item['chunk']:05d}", "reference": item["reference"],
                           "reference_context": text[max(0, item["start"] - 120):item["start"] + len(item["reference"]) + 60],
                           "target_node": item["target"]["node_id"], "attached": item["added"],
                           "target_text_start": text[item["target"]["start_char"]:item["target"]["start_char"] + 160],
                           JUDGEMENT: ""} for item in sample])
    run_id = new_test_run_id(2, args.run_source) if args.test else new_run_id(2, args.run_source)
    folder = RUNS_DIR / "tests" if args.test else PROJECT_ROOT / "data" / "results" / "ext_xref"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{'test_' if args.test else ''}method1_xref_{args.doc}_{args.parser}_T{args.T}_X12"
    sheet_path, manifest_path = folder / f"{name}_sheet_{run_id}.csv", RUNS_DIR / ("tests" if args.test else "") / f"{name}_{run_id}.json"
    if manifest_path.exists() or sheet_path.exists():
        raise FileExistsError(f"already exists: {manifest_path} or {sheet_path}")
    sheet.to_csv(sheet_path, index=False)
    stack = {"check": "X12", "doc": args.doc, "parser": args.parser, "T": args.T, "n": args.n, "seed": args.seed,
             "attached_total": len(attached), "drawn": len(sample)}
    manifest_path.write_text(json.dumps(build_manifest(run_id, "v1.2", stack, [extracted_path, chunk_path], [sheet_path],
                                                       {}, "laptop"), indent=2), encoding="utf-8")
    print(f"{len(sample)} of {len(attached)} attached references, seed {args.seed}\nsheet: {sheet_path}\nmanifest: {manifest_path}")


if __name__ == "__main__":
    main()
