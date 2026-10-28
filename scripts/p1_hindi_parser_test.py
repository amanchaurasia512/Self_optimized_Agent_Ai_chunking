"""Hindi parser test: run pdfplumber and LlamaParse tiers on single test pages and score Devanagari quality.
Outputs that already exist are reused, so re-running never spends credits twice."""
import argparse
import json
from pathlib import Path

import pandas as pd

from scripts.p1_hindi_check import devanagari_quality
from src.common.cost_logger import CostLogger
from src.common.manifest import PROJECT_ROOT, build_manifest, new_run_id, write_manifest
from src.parse import pdfplumber_parser
from src.parse.llamaparse_parser import CREDITS_PER_PAGE, make_client, parser_info
from src.parse.llamaparse_parser import parse_pdf as llamaparse_pdf

OUTPUT_DIR = PROJECT_ROOT / "data" / "extracted" / "hindi_test"
OCR_LANG = ["hi", "en"]
DEFAULT_PARSERS = ["pdfplumber", "llamaparse_fast", "llamaparse_cost_effective", "llamaparse_agentic"]


def run_parser(name, pdf_path, client):
    if name == "pdfplumber":
        text, pages = pdfplumber_parser.parse_pdf(pdf_path)
        return text, pages, pdfplumber_parser.PARSER
    tier = name.removeprefix("llamaparse_")
    text, pages = llamaparse_pdf(pdf_path, client, tier, OCR_LANG)
    return text, pages, parser_info(tier, OCR_LANG)


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--pdfs", type=Path, nargs="+", required=True)
    arg_parser.add_argument("--parsers", nargs="+", default=DEFAULT_PARSERS)
    args = arg_parser.parse_args()

    client = make_client() if any(name.startswith("llamaparse") for name in args.parsers) else None
    logger = CostLogger()
    rows, inputs, outputs = [], [], []
    for pdf_path in args.pdfs:
        for name in args.parsers:
            output_path = OUTPUT_DIR / name / f"{pdf_path.stem}.json"
            if output_path.exists():
                text = json.loads(output_path.read_text(encoding="utf-8"))["text"]
            else:
                with logger.stage(f"{name}:{pdf_path.stem}"):
                    text, pages, info = run_parser(name, pdf_path, client)
                    if name.startswith("llamaparse"):
                        logger.add_credits(len(pages) * CREDITS_PER_PAGE[info["tier"]])
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_text(json.dumps({"doc_id": pdf_path.stem, "parser": info, "text": text, "pages": pages},
                                                      ensure_ascii=False, indent=2), encoding="utf-8")
                inputs.append(pdf_path)
                outputs.append(output_path)
            quality = devanagari_quality(text)
            rows.append({"page": pdf_path.stem, "parser": name, "chars": len(text),
                         **{key: value for key, value in quality.items() if key != "examples"}})

    if outputs:
        manifest = build_manifest(new_run_id(1, "LOCAL"), "v1", {"test": "hindi parser comparison", "ocr_lang": OCR_LANG},
                                  inputs, outputs, logger.summary(), "laptop")
        print("manifest:", write_manifest(manifest))
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()