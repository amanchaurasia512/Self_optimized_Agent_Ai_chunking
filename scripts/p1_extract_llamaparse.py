"""P1-R03 (backup parser): LlamaParse on selected catalogue PDFs. Existing outputs are never overwritten."""
import argparse
import json

import pandas as pd

from src.common.cost_logger import CostLogger
from src.common.manifest import PROJECT_ROOT, build_manifest, new_run_id, write_manifest
from src.common.pdf_catalog import PDF_MANIFEST
from src.parse.llamaparse_parser import CREDITS_PER_PAGE, make_client, parse_pdf, parser_info

SPEC_VERSION = "v1"


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--only", nargs="+", required=True, help="doc ids to parse (credits are paid per page)")
    arg_parser.add_argument("--tier", default="cost_effective", choices=list(CREDITS_PER_PAGE))
    arg_parser.add_argument("--ocr-lang", nargs="+")
    args = arg_parser.parse_args()

    output_dir = PROJECT_ROOT / "data" / "extracted" / f"llamaparse_{args.tier}"
    output_dir.mkdir(parents=True, exist_ok=True)
    catalog = pd.read_csv(PDF_MANIFEST)
    client, info = make_client(), parser_info(args.tier, args.ocr_lang)
    logger = CostLogger()
    inputs, outputs = [], []
    for record in catalog[catalog["doc_id"].isin(args.only)].itertuples(index=False):
        output_path = output_dir / f"{record.doc_id}.json"
        if output_path.exists():
            continue
        pdf_path = PROJECT_ROOT / record.file
        with logger.stage(f"parse:{record.doc_id}") as stage:
            text, pages = parse_pdf(pdf_path, client, args.tier, args.ocr_lang)
            output_path.write_text(json.dumps({"doc_id": record.doc_id, "parser": info, "text": text, "pages": pages},
                                              ensure_ascii=False, indent=2), encoding="utf-8")
            logger.add_credits(len(pages) * CREDITS_PER_PAGE[args.tier])
            stage["chars"] = len(text)
            stage["empty_pages"] = sum(page["start_char"] == page["end_char"] for page in pages)
        inputs.append(pdf_path)
        outputs.append(output_path)

    if outputs:
        manifest = build_manifest(new_run_id(1, "LOCAL"), SPEC_VERSION, {"parser": info}, inputs, outputs,
                                  logger.summary(), "laptop")
        print("manifest:", write_manifest(manifest))
        print(pd.DataFrame(logger.stages)[["stage", "wall_seconds", "chars", "empty_pages", "paid_credits"]].to_string(index=False))


if __name__ == "__main__":
    main()