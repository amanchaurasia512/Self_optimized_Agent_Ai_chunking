"""P1-R03: freeze Docling extraction for every PDF under --input (searched recursively). Existing outputs are skipped."""
import argparse
import json
from pathlib import Path

import pandas as pd

from src.common.cost_logger import CostLogger
from src.common.manifest import build_manifest, new_run_id, write_manifest
from src.parse.docling_parser import make_converter, parse_pdf

SPEC_VERSION = "v1"


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--input", type=Path, required=True)
    arg_parser.add_argument("--output", type=Path, required=True)
    arg_parser.add_argument("--machine", default="kaggle")
    arg_parser.add_argument("--run-source", default="KN02", help="notebook id used in the run id, e.g. KN04")
    arg_parser.add_argument("--force-full-page-ocr", action="store_true")
    arg_parser.add_argument("--ocr-lang", nargs="+")
    arg_parser.add_argument("--only", nargs="+", help="doc ids to run; default: all PDFs under --input")
    args = arg_parser.parse_args()

    converter, parser_info = make_converter(args.force_full_page_ocr, args.ocr_lang)
    args.output.mkdir(parents=True, exist_ok=True)
    logger = CostLogger()
    inputs, outputs = [], []
    pdf_paths = [path for path in sorted(args.input.rglob("*.pdf")) if not args.only or path.stem in args.only]
    for pdf_path in pdf_paths:
        output_path = args.output / f"{pdf_path.stem}.json"
        if output_path.exists():
            continue
        with logger.stage(f"parse:{pdf_path.stem}") as stage:
            text, pages, elements = parse_pdf(pdf_path, converter)
            output_path.write_text(json.dumps({"doc_id": pdf_path.stem, "parser": parser_info, "text": text,
                                               "pages": pages, "elements": elements}, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
            stage["chars"] = len(text)
            stage["empty_pages"] = sum(page["start_char"] == page["end_char"] for page in pages)
            stage["elements"] = len(elements)
        inputs.append(pdf_path)
        outputs.append(output_path)

    if outputs:
        manifest = build_manifest(new_run_id(1, args.run_source), SPEC_VERSION, {"parser": parser_info}, inputs, outputs,
                                  logger.summary(), args.machine)
        print("manifest:", write_manifest(manifest))
        print(pd.DataFrame(logger.stages)[["stage", "wall_seconds", "chars", "empty_pages", "elements"]].to_string(index=False))

if __name__ == "__main__":
    main()