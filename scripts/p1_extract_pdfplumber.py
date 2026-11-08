"""P1-R03: freeze pdfplumber extraction for every PDF in the catalogue. Existing outputs are never overwritten."""
import argparse
import json

import pandas as pd

from src.common.cost_logger import CostLogger
from src.common.manifest import PROJECT_ROOT, build_manifest, new_run_id, write_manifest
from src.common.pdf_catalog import PDF_MANIFEST
from src.parse.pdfplumber_parser import PARSER, parse_pdf, variant, VARIANTS


OUTPUT_DIR = PROJECT_ROOT / "data" / "extracted" / "pdfplumber"
SPEC_VERSION = "v1"


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--variant", default="default", choices=list(VARIANTS), help="RQ5a parser variant")
    arg_parser.add_argument("--only", nargs="+", help="doc ids to run; default: every PDF in the catalogue")
    args = arg_parser.parse_args()

    output_dir = OUTPUT_DIR if args.variant == "default" else OUTPUT_DIR.with_name(f"pdfplumber_{args.variant}")
    parser_info = PARSER if args.variant == "default" else {**PARSER, "variant": args.variant, "settings": VARIANTS[args.variant]}
    catalog = pd.read_csv(PDF_MANIFEST)
    output_dir.mkdir(parents=True, exist_ok=True)
    logger = CostLogger()
    inputs, outputs, skipped = [], [], []
    for record in catalog.itertuples(index=False):
        if args.only and record.doc_id not in args.only:
            continue
        output_path = output_dir / f"{record.doc_id}.json"
        if output_path.exists():
            skipped.append(record.doc_id)
            continue
        pdf_path = PROJECT_ROOT / record.file
        with logger.stage(f"parse:{record.doc_id}") as stage:
            text, pages = parse_pdf(pdf_path, args.variant)
            output_path.write_text(json.dumps({"doc_id": record.doc_id, "parser": parser_info, "text": text, "pages": pages},
                                              ensure_ascii=False, indent=2), encoding="utf-8")
            stage["chars"] = len(text)
            stage["empty_pages"] = sum(page["start_char"] == page["end_char"] for page in pages)
        inputs.append(pdf_path)
        outputs.append(output_path)

    if outputs:
        manifest = build_manifest(new_run_id(1, "LOCAL"), SPEC_VERSION, {"parser": parser_info}, inputs, outputs,
                                  logger.summary(), "laptop")
        print("manifest:", write_manifest(manifest))
        print(pd.DataFrame(logger.stages)[["stage", "wall_seconds", "peak_ram_mb", "chars", "empty_pages"]].to_string(index=False))
    print("skipped (already frozen):", skipped)

if __name__ == "__main__":
    main()