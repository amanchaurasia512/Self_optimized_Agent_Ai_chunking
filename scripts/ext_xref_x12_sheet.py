"""Method 1 v2, X12 precision check (spec v1.2). Tuning documents only; no --final; no LLM call; the chunker is not changed.
Stage 'sheet': draw up to --n attached cross-references at random (seed in the run record) from one method1_xref chunk
file and write a sheet for the hand check. Stage 'label' (modelled on scripts/golden_check.py): terminal labelling,
c = correct, w = wrong target in this document, o = other document (another law), s = unsure, m = more context,
q = quit, an optional note after each label; saved after every label, resumable from the first empty row. Stage
'report': counts per label and the correct rate (correct / labelled, unsure in the denominator) with a Wilson 95%
interval, saved next to the sheet as ..._X12_report_<run>.txt."""
import argparse
import json
import random
from pathlib import Path

import pandas as pd

from scripts.golden_check import wilson
from src.chunk.xref import CHUNKS, PREFIX_SHARE, cross_references
from src.common.manifest import PROJECT_ROOT, RUNS_DIR, build_manifest, file_sha256, new_run_id, new_test_run_id
from src.common.split import tuning_ids

EXTRACTED = PROJECT_ROOT / "data" / "extracted"
JUDGEMENT, NOTE = "judgement (correct / wrong / other document)", "note"
KEYS = {"c": "correct", "w": "wrong", "o": "other document", "s": "unsure"}
CONTEXT, MORE, TARGET, WIDTH = 300, 1000, 200, 80


def attached_references(document, chunks, T, chunk_path):
    """The attached references of a chunk file, recomputed; stops if they no longer give the file's prefixes."""
    prefixes, report, details = cross_references(document, [(chunk["start_char"], chunk["end_char"]) for chunk in chunks],
                                                 int(PREFIX_SHARE * T))
    if prefixes != [chunk["prefix"] for chunk in chunks]:
        raise ValueError(f"the references recomputed now differ from the prefixes in {chunk_path}")
    return [item for item in details if item["status"] == "attached"]


def make_sheet(args):
    if args.doc not in tuning_ids():
        raise PermissionError(f"tuning documents only: {args.doc}")
    if not args.run_source:
        raise ValueError("--stage sheet needs --run-source")
    extracted_path = EXTRACTED / args.parser / f"{args.doc}.json"
    chunk_path = (CHUNKS / "tests" if args.test else CHUNKS) / args.parser / f"method1_xref_T{args.T}_noprefix" / f"{args.doc}.json"
    document = json.loads(extracted_path.read_text(encoding="utf-8"))
    chunks = json.loads(chunk_path.read_text(encoding="utf-8"))["chunks"]
    attached = attached_references(document, chunks, args.T, chunk_path)
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


def load_sheet(sheet_path):
    sheet = pd.read_csv(sheet_path, dtype=str, keep_default_na=False)
    return sheet if NOTE in sheet else sheet.assign(**{NOTE: ""})


def sheet_record(sheet_path):
    """The sheet's run record (runs/tests/ or runs/, same name without '_sheet'); its inputs must be unchanged."""
    name = sheet_path.stem.replace("_sheet_", "_") + ".json"
    path = next((folder / name for folder in (RUNS_DIR / "tests", RUNS_DIR) if (folder / name).exists()), None)
    if path is None:
        raise FileNotFoundError(f"no run record {name} in runs/tests/ or runs/")
    record = json.loads(path.read_text(encoding="utf-8"))
    changed = [item["path"] for item in record["inputs"] if file_sha256(PROJECT_ROOT / item["path"]) != item["sha256"]]
    if changed:
        raise ValueError(f"inputs changed since the sheet was drawn: {changed}")
    return record


def located(sheet, record):
    """Per sheet row: (reference start, target node) from the recomputed attached references of the recorded chunk file."""
    extracted_path, chunk_path = (PROJECT_ROOT / item["path"] for item in record["inputs"])
    document = json.loads(extracted_path.read_text(encoding="utf-8"))
    chunks = json.loads(chunk_path.read_text(encoding="utf-8"))["chunks"]
    attached = attached_references(document, chunks, record["stack"]["T"], chunk_path)
    by_row = {(f"c{item['chunk']:05d}", item["reference"], item["target"]["node_id"]): item for item in attached}
    return document["text"], [by_row[(row.chunk, row.reference, row.target_node)] for row in sheet.itertuples()]


def window(text, item, size):
    start, end = item["start"], item["start"] + len(item["reference"])
    margin = max(0, (size - (end - start)) // 2)
    return f"{text[max(0, start - margin):start]}>>>{text[start:end]}<<<{text[end:end + margin]}"


def screen(number, total, row, item, text):
    target = item["target"]
    equals = "=" * WIDTH
    return (f"\n{f'---- {number}/{total} · {row.chunk} · {row.reference!r} '.ljust(WIDTH, '-')}\n"
            f"{equals}\nCONTEXT ({CONTEXT} characters):\n{window(text, item, CONTEXT)}\n{equals}\n"
            f"ATTACHED: {row.attached}\n"
            f"TARGET {target['node_id']} title: {target['title']}\n"
            f"TARGET text: {text[target['start_char']:target['start_char'] + TARGET]}\n{equals}")


def label(sheet_path, ask=input):
    """Label from the first empty row on; save after every label; m shows more context; q quits."""
    sheet = load_sheet(sheet_path)
    text, items = located(sheet, sheet_record(sheet_path))
    pending = [index for index in range(len(sheet)) if not sheet.at[index, JUDGEMENT]]
    print(f"{len(pending)} of {len(sheet)} rows to label | c = correct, w = wrong target in this document, "
          f"o = other document, s = unsure, m = {MORE:,} more characters of context, q = quit")
    for index in pending:
        row = next(sheet.iloc[[index]].itertuples())
        print(screen(index + 1, len(sheet), row, items[index], text))
        key = ""
        while key not in KEYS and key != "q":
            key = ask("[c] correct [w] wrong [o] other document [s] unsure [m] more context [q] quit: ").strip().lower()
            if key == "m":
                print(f"{'=' * WIDTH}\nLONGER CONTEXT ({CONTEXT + MORE:,} characters):\n"
                      f"{window(text, items[index], CONTEXT + MORE)}\n{'=' * WIDTH}")
        if key == "q":
            break
        sheet.at[index, JUDGEMENT], sheet.at[index, NOTE] = KEYS[key], ask("note (Enter for none): ").strip()
        sheet.to_csv(sheet_path, index=False)
    print(f"\nlabelled {int((sheet[JUDGEMENT] != '').sum())} of {len(sheet)} | saved {sheet_path}")


def report(sheet_path):
    """Counts per label; correct rate = correct / labelled (unsure counted in the denominator) with Wilson 95%."""
    sheet = load_sheet(sheet_path)
    labelled = sheet[sheet[JUDGEMENT] != ""]
    counts = {name: int((labelled[JUDGEMENT] == name).sum()) for name in KEYS.values()}
    total, correct = len(labelled), counts["correct"]
    low, high = wilson(correct, total)
    lines = [f"X12 precision check, {sheet_path.name}",
             f"labelled {total} of {len(sheet)}",
             *(f"  {name:15s} {count}" for name, count in counts.items()),
             f"correct rate = correct / labelled = {correct}/{total} = {correct / total:.3f}, Wilson 95% [{low:.3f}, {high:.3f}]"
             if total else "correct rate: nothing labelled yet",
             f"unsure (in the denominator above): {counts['unsure']} of {total}",
             *([f"notes:\n{labelled[labelled[NOTE] != ''][['chunk', 'reference', JUDGEMENT, NOTE]].to_string(index=False)}"]
               if (labelled[NOTE] != "").any() else [])]
    report_path = sheet_path.with_name(sheet_path.stem.replace("_sheet_", "_report_") + ".txt")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines) + f"\nsaved {report_path}")


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--stage", default="sheet", choices=["sheet", "label", "report"])
    arg_parser.add_argument("--sheet", type=Path, help="the sheet to label or report (stages label, report)")
    arg_parser.add_argument("--doc", default="indian_d4_rti_act")
    arg_parser.add_argument("--parser", default="docling")
    arg_parser.add_argument("--T", type=int, default=512)
    arg_parser.add_argument("--n", type=int, default=30)
    arg_parser.add_argument("--seed", type=int, default=20261118)
    arg_parser.add_argument("--run-source", help="stage sheet: e.g. LOCAL; TEST with --test")
    arg_parser.add_argument("--test", action="store_true", help="stage sheet: read data/chunks/tests/, write to runs/tests/")
    args = arg_parser.parse_args()
    if args.stage == "sheet":
        make_sheet(args)
    elif not args.sheet:
        arg_parser.error(f"--stage {args.stage} needs --sheet")
    elif args.stage == "label":
        label(args.sheet)
    else:
        report(args.sheet)


if __name__ == "__main__":
    main()
