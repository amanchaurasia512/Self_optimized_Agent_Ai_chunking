"""P1-R03: freeze pdfplumber extraction for every PDF in the catalogue. Existing outputs are never overwritten."""
import json

import pandas as pd

from src.common.cost_logger import CostLogger
from src.common.manifest import PROJECT_ROOT, build_manifest, new_run_id, write_manifest
from src.common.pdf_catalog import PDF_MANIFEST
from src.parse.pdfplumber_parser import PARSER, parse_pdf

OUTPUT_DIR = PROJECT_ROOT / "data" / "extracted" / "pdfplumber"
SPEC_VERSION = "v1"


def main():
    catalog = pd.read_csv(PDF_MANIFEST)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger = CostLogger()
    inputs, outputs, skipped = [], [], []
    for record in catalog.itertuples(index=False):
        output_path = OUTPUT_DIR / f"{record.doc_id}.json"
        if output_path.exists():
            skipped.append(record.doc_id)
            continue
        pdf_path = PROJECT_ROOT / record.file
        with logger.stage(f"parse:{record.doc_id}") as stage:
            text, pages = parse_pdf(pdf_path)
            output_path.write_text(json.dumps({"doc_id": record.doc_id, "parser": PARSER, "text": text, "pages": pages},
                                              ensure_ascii=False, indent=2), encoding="utf-8")
            stage["chars"] = len(text)
            stage["empty_pages"] = sum(page["start_char"] == page["end_char"] for page in pages)
        inputs.append(pdf_path)
        outputs.append(output_path)

    if outputs:
        manifest = build_manifest(new_run_id(1, "LOCAL"), SPEC_VERSION, {"parser": PARSER}, inputs, outputs,
                                  logger.summary(), "laptop")
        print("manifest:", write_manifest(manifest))
        print(pd.DataFrame(logger.stages)[["stage", "wall_seconds", "peak_ram_mb", "chars", "empty_pages"]].to_string(index=False))
    print("skipped (already frozen):", skipped)


if __name__ == "__main__":
    main()