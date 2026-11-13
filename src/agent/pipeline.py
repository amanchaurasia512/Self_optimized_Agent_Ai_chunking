"""Agent chunk mode (spec/agent_v1.md): PDF -> scan check -> parser choice -> study parser -> method1_tree T384 no prefix
-> chunk.json, plus a run record. Reuses the study's parsers, chunker, chunk builder, validator and run manifest."""
import json
from datetime import datetime
from functools import cache
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


@cache
def docling_converter():
    """The study's default Docling converter and its parser info, built once per process (its models load once)."""
    from src.parse.docling_parser import make_converter
    return make_converter()


def parse(pdf_path, parser, doc_id, reason_needs_docling="Docling is needed"):
    """A document in the study's extraction format (as the P1 extraction scripts write it)."""
    if parser == "pdfplumber":
        from src.parse.pdfplumber_parser import PARSER, parse_pdf
        text, pages = parse_pdf(pdf_path)
        return {"doc_id": doc_id, "parser": PARSER, "text": text, "pages": pages}
    try:
        from src.parse.docling_parser import parse_pdf
    except ModuleNotFoundError as error:
        raise SystemExit(f"{reason_needs_docling}: install the docling extra, pip install -e \".[docling]\" ({error})")
    converter, parser_info = docling_converter()
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


def scan(pdf_path, pdf_sha, cache_root=None):
    """(pages without text, page count); with cache_root, kept in <cache_root>/<sha>/scan.json (it depends on the PDF only)."""
    cached = Path(cache_root) / pdf_sha / "scan.json" if cache_root else None
    if cached and cached.exists():
        found = json.loads(cached.read_text(encoding="utf-8"))
        return found["pages_without_text"], found["pages"]
    empty_pages, page_count = pages_without_text(pdf_path)
    if cached:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps({"pages": page_count, "pages_without_text": empty_pages}), encoding="utf-8")
    return empty_pages, page_count


def plan(pdf_path, fast=False, from_extraction=None, logger=None, cache_root=None):
    """Scan check and parser choice, before any parsing: what to build and why."""
    pdf_sha = manifest.file_sha256(pdf_path)
    with logger.stage("scan_check"):
        empty_pages, page_count = scan(pdf_path, pdf_sha, cache_root)
    extraction = json.loads(Path(from_extraction).read_text(encoding="utf-8")) if from_extraction else None
    if extraction:
        parser, reason = extraction["parser"]["name"], f"from existing extraction {manifest.project_path(from_extraction)}"
    else:
        parser, reason = choose_parser(fast, empty_pages, page_count)
    return {"pdf": Path(pdf_path), "pdf_sha": pdf_sha, "fast": fast, "from_extraction": from_extraction,
            "extraction": extraction, "empty_pages": empty_pages, "page_count": page_count, "parser": parser, "reason": reason}


def chunker_info():
    entry = CHUNKERS[CHUNKER_NAME]
    return {"name": CHUNKER_NAME, "version": entry["version"], "settings": {**CHUNKER_SETTINGS, "heading_prefix": HEADING_PREFIX}}


def build(planned, run_id, logger):
    """Parse (or take the extraction) and chunk: (document, chunk document)."""
    with logger.stage("parse"):
        if planned["extraction"]:
            document = planned["extraction"]
            source = catalog_source(document["doc_id"], planned["pdf_sha"]) or {"sha256": planned["pdf_sha"], "file": planned["pdf"].name}
        else:
            document = parse(planned["pdf"], planned["parser"], planned["pdf"].stem, planned["reason"])
            source = {"sha256": planned["pdf_sha"], "file": planned["pdf"].name}
    entry = CHUNKERS[CHUNKER_NAME]
    with logger.stage("chunk"):
        spans = entry["function"](document, **CHUNKER_SETTINGS)
        chunk_doc = chunk_document(document, spans, chunker_info(), run_id, source, HEADING_PREFIX, entry["nodes"](document),
                                   int(entry["prefix_share"] * CHUNKER_SETTINGS["T"]))
        chunk_doc["quality"]["layer1"] = layer1_report(chunk_doc, document["text"], load_validator())
    return document, chunk_doc


def plan_stack(planned, document):
    """The run-record fields every agent mode shares."""
    return {"parser_mode": "fast" if planned["fast"] else "thorough", "parser": document["parser"],
            "parser_reason": planned["reason"],
            "from_extraction": manifest.project_path(planned["from_extraction"]) if planned["from_extraction"] else None,
            "pages": planned["page_count"], "pages_without_text": len(planned["empty_pages"]),
            "pages_without_text_list": planned["empty_pages"], "chunker": chunker_info(), "tokenizer": TOKENIZER}


def plan_inputs(planned):
    return [planned["pdf"]] + ([Path(planned["from_extraction"])] if planned["from_extraction"] else [])


def chunk_pdf(pdf_path, output_path, fast=False, from_extraction=None, machine="laptop"):
    """Chunk one PDF; writes the chunk.json and the run record, returns (chunk document, run record path)."""
    output_path, logger = Path(output_path), CostLogger()
    planned = plan(pdf_path, fast, from_extraction, logger)
    run_id = agent_run_id()
    document, chunk_doc = build(planned, run_id, logger)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(chunk_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    stack = {"agent_mode": "chunk", **plan_stack(planned, document), "chunks": len(chunk_doc["chunks"]),
             "layer1_passed": chunk_doc["quality"]["layer1"].get("passed")}
    record = manifest.build_manifest(run_id, SPEC, stack, plan_inputs(planned), [output_path], logger.summary(), machine)
    return chunk_doc, manifest.write_manifest(record)
