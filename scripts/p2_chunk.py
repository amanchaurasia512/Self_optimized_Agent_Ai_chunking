"""P2: run one chunker setting over frozen extractions; writes chunk.json (with Layer 1), logs cost per document, writes a manifest."""
import argparse
import json
from pathlib import Path

import pandas as pd

from src.chunk.base import TOKENIZER, chunk_document
from src.chunk.chunkers import CHUNKERS
from src.common.cost_logger import CostLogger
from src.common.manifest import PROJECT_ROOT, build_manifest, new_run_id, write_manifest
from src.common.pdf_catalog import PDF_MANIFEST
from src.common.validate import layer1_report, load_validator

EXTRACTED, CHUNKS = PROJECT_ROOT / "data" / "extracted", PROJECT_ROOT / "data" / "chunks"
INDIAN = ["indian_d1", "indian_d2_ccs_conduct_rules", "indian_d3_fundamental_rules", "indian_d4_rti_act"]


def parse_settings(pairs):
    return {key: int(value) if value.isdigit() else value for key, value in (pair.split("=", 1) for pair in pairs)}


def setting_name(chunker, settings, heading_prefix):
    return "_".join([chunker, *(f"{key}{value}" for key, value in settings.items()), "prefix" if heading_prefix else "noprefix"])


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--chunker", required=True, choices=list(CHUNKERS))
    arg_parser.add_argument("--set", nargs="*", default=[], help="chunker settings as key=value, e.g. size=512 overlap=0")
    arg_parser.add_argument("--heading-prefix", action="store_true")
    arg_parser.add_argument("--parsers", nargs="+", default=["docling", "pdfplumber"])
    arg_parser.add_argument("--docs", nargs="+", default=INDIAN)
    args = arg_parser.parse_args()

    settings = parse_settings(args.set)
    chunker = {"name": args.chunker, "version": CHUNKERS[args.chunker]["version"],
               "settings": {**settings, "heading_prefix": args.heading_prefix}}
    name = setting_name(args.chunker, settings, args.heading_prefix)
    catalog = pd.read_csv(PDF_MANIFEST).set_index("doc_id")
    run_id, logger, validator = new_run_id(2, "LOCAL"), CostLogger(), load_validator()
    rows, inputs, outputs = [], [], []
    for parser in args.parsers:
        for doc_id in args.docs:
            extracted_path = EXTRACTED / parser / f"{doc_id}.json"
            document = json.loads(extracted_path.read_text(encoding="utf-8"))
            source = {"sha256": catalog.loc[doc_id, "sha256"], "file": Path(catalog.loc[doc_id, "file"]).name}
            with logger.stage(f"chunk:{parser}:{doc_id}") as stage:
                spans = CHUNKERS[args.chunker]["function"](document, **settings)
                chunk_doc = chunk_document(document, spans, chunker, run_id, source, args.heading_prefix)
                stage["chunks"] = len(chunk_doc["chunks"])
                stage["index_tokens"] = sum(chunk["token_count"] + chunk["prefix_token_count"] for chunk in chunk_doc["chunks"])
            layer1 = layer1_report(chunk_doc, document["text"], validator)
            chunk_doc["quality"]["layer1"] = layer1
            output_path = CHUNKS / parser / name / f"{doc_id}.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(chunk_doc, ensure_ascii=False, indent=2), encoding="utf-8")
            inputs.append(extracted_path)
            outputs.append(output_path)
            tokens = pd.Series([chunk["token_count"] for chunk in chunk_doc["chunks"]])
            rows.append({"parser": parser, "doc_id": doc_id, "chunks": len(tokens), "index_tokens": stage["index_tokens"],
                         "min": tokens.min(), "median": int(tokens.median()), "max": tokens.max(),
                         "C3": sum("C3" in chunk["errors"] for chunk in chunk_doc["chunks"]),
                         "passed": layer1.get("passed"), "offset_match": layer1.get("offset_match_rate"),
                         "coverage": round(layer1.get("text_coverage", 0), 4), "seconds": stage["wall_seconds"]})

    stack = {"chunker": chunker, "tokenizer": TOKENIZER, "parsers": args.parsers}
    manifest_path = write_manifest(build_manifest(run_id, "v1", stack, inputs, outputs, logger.summary(), "laptop"))
    pd.set_option("display.width", 200)
    print(f"{name} | run {run_id}\n{pd.DataFrame(rows).to_string(index=False)}\nmanifest: {manifest_path}")


if __name__ == "__main__":
    main()