"""Agent chunk mode (spec/agent_v1.md): PDF -> scan check -> parser choice -> study parser -> method1_tree T384 no prefix
-> chunk.json, plus a run record. Reuses the study's parsers, chunker, chunk builder, validator and run manifest."""
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import pdfplumber

from src.chunk.base import TOKENIZER, chunk_document
from src.chunk.chunkers import CHUNKERS
from src.common import manifest
from src.common.cost_logger import CostLogger
from src.common.pdf_catalog import PDF_MANIFEST
from src.common.validate import layer1_report, load_validator

CHUNKER_NAME, CHUNKER_SETTINGS, HEADING_PREFIX = "method1_tree", {"T": 384}, False
SPEC = "agent_v1"


def agent_run_id(source="LOCAL"):
    """A-{source}-{date}-{n}, numbered like manifest.new_run_id: highest existing n + 1."""
    prefix = f"A-{source}-{datetime.now():%Y%m%d}"
    numbers = [int(path.stem.rsplit("-", 1)[1]) for path in manifest.RUNS_DIR.glob(f"{prefix}-*.json")]
    return f"{prefix}-{max(numbers, default=0) + 1}"


def pages_without_text(pdf_path):
    """Page numbers (from 1) on which pdfplumber finds no characters, i.e. pages without a text layer."""
    with pdfplumber.open(pdf_path) as pdf:
        return [number for number, page in enumerate(pdf.pages, start=1) if not page.chars], len(pdf.pages)


def choose_parser(fast, empty_pages, page_count):
    if not fast:
        return "docling", "thorough mode: Docling for every document"
    if empty_pages:
        return "docling", f"fast mode, but {len(empty_pages)} of {page_count} pages have no text layer: Docling for the whole document"
    return "pdfplumber", "fast mode, every page has a text layer"


def parse(pdf_path, parser, doc_id, reason_needs_docling="Docling is needed"):
    """A document in the study's extraction format (as the P1 extraction scripts write it)."""
    if parser == "pdfplumber":
        from src.parse.pdfplumber_parser import PARSER, parse_pdf
        text, pages = parse_pdf(pdf_path)
        return {"doc_id": doc_id, "parser": PARSER, "text": text, "pages": pages}
    try:
        from src.parse.docling_parser import make_converter, parse_pdf
    except ModuleNotFoundError as error:
        raise SystemExit(f"{reason_needs_docling}: install the docling extra, pip install -e \".[docling]\" ({error})")
    converter, parser_info = make_converter()
    text, pages, elements = parse_pdf(pdf_path, converter)
    return {"doc_id": doc_id, "parser": parser_info, "text": text, "pages": pages, "elements": elements}


def catalog_source(doc_id, pdf_sha):
    """The study's source fields for a catalogued document (as scripts/p2_chunk.py takes them); None if not catalogued."""
    catalog = pd.read_csv(PDF_MANIFEST).set_index("doc_id")
    if doc_id not in catalog.index:
        return None
    row = catalog.loc[doc_id]
    if row["sha256"] != pdf_sha:
        raise ValueError(f"{doc_id}: the PDF given does not match the catalogued file (SHA-256 differs)")
    return {"sha256": row["sha256"], "file": Path(row["file"]).name}


def chunk_pdf(pdf_path, output_path, fast=False, from_extraction=None, machine="laptop"):
    """Chunk one PDF; writes the chunk.json and the run record, returns (chunk document, run record path)."""
    pdf_path, output_path = Path(pdf_path), Path(output_path)
    logger, pdf_sha = CostLogger(), manifest.file_sha256(pdf_path)
    with logger.stage("scan_check"):
        empty_pages, page_count = pages_without_text(pdf_path)
    with logger.stage("parse"):
        if from_extraction:
            document = json.loads(Path(from_extraction).read_text(encoding="utf-8"))
            parser, reason = document["parser"]["name"], f"from existing extraction {manifest.project_path(from_extraction)}"
            source = catalog_source(document["doc_id"], pdf_sha) or {"sha256": pdf_sha, "file": pdf_path.name}
        else:
            parser, reason = choose_parser(fast, empty_pages, page_count)
            document = parse(pdf_path, parser, pdf_path.stem, reason)
            source = {"sha256": pdf_sha, "file": pdf_path.name}
    entry = CHUNKERS[CHUNKER_NAME]
    chunker = {"name": CHUNKER_NAME, "version": entry["version"],
               "settings": {**CHUNKER_SETTINGS, "heading_prefix": HEADING_PREFIX}}
    run_id = agent_run_id()
    with logger.stage("chunk"):
        spans = entry["function"](document, **CHUNKER_SETTINGS)
        chunk_doc = chunk_document(document, spans, chunker, run_id, source, HEADING_PREFIX, entry["nodes"](document),
                                   int(entry["prefix_share"] * CHUNKER_SETTINGS["T"]))
        chunk_doc["quality"]["layer1"] = layer1_report(chunk_doc, document["text"], load_validator())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(chunk_doc, ensure_ascii=False, indent=2), encoding="utf-8")

    stack = {"agent_mode": "chunk", "parser_mode": "fast" if fast else "thorough", "parser": document["parser"],
             "parser_reason": reason, "from_extraction": manifest.project_path(from_extraction) if from_extraction else None,
             "pages": page_count, "pages_without_text": len(empty_pages), "pages_without_text_list": empty_pages,
             "chunker": chunker, "tokenizer": TOKENIZER, "chunks": len(chunk_doc["chunks"]),
             "layer1_passed": chunk_doc["quality"]["layer1"].get("passed")}
    inputs = [pdf_path] + ([Path(from_extraction)] if from_extraction else [])
    record = manifest.build_manifest(run_id, SPEC, stack, inputs, [output_path], logger.summary(), machine)
    return chunk_doc, manifest.write_manifest(record)
