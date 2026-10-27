"""P0-R06: dummy end-to-end run. One PDF -> frozen text -> one chunk per page -> chunk.json + Layer 1 + manifest.
The page chunker here only tests the pipeline; it is not one of the six research chunkers."""
import argparse
import json
from datetime import datetime, timezone
from importlib.metadata import version
from itertools import accumulate
from pathlib import Path

import pdfplumber
from tokenizers import Tokenizer

from src.common.cost_logger import CostLogger
from src.common.manifest import PROJECT_ROOT, build_manifest, file_sha256, new_run_id, write_manifest
from src.common.validate import layer1_report, load_validator

SPEC_VERSION = "v1"
TOKENIZER = {"name": "BAAI/bge-m3", "revision": "5617a9f61b028005a4858fdac845db406aefb181"}
MIN_TOKENS, MAX_TOKENS = 100, 1024  # spec v1 chunk size limits
PAGE_SEPARATOR = "\n\n"
CHUNKER = {"name": "page_placeholder", "version": "0.1", "settings": {"unit": "page"}}


def parse_pdf(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        page_texts = [page.extract_text() or "" for page in pdf.pages]
    starts = [0, *accumulate(len(text) + len(PAGE_SEPARATOR) for text in page_texts[:-1])]
    pages = [{"page": number, "start_char": start, "end_char": start + len(text)}
             for number, (start, text) in enumerate(zip(starts, page_texts), start=1)]
    return PAGE_SEPARATOR.join(page_texts), pages


def chunk_by_page(text, pages, tokenizer):
    filled = [page for page in pages if text[page["start_char"]:page["end_char"]].strip()]
    texts = [text[page["start_char"]:page["end_char"]] for page in filled]
    counts = [len(encoding.ids) for encoding in tokenizer.encode_batch(texts, add_special_tokens=False)]
    ids = [f"c{index:04d}" for index in range(len(filled))]
    return [{
        "chunk_id": ids[index], "text": texts[index],
        "start_char": page["start_char"], "end_char": page["end_char"],
        "pages": [page["page"]], "section_path": [],
        "token_count": counts[index], "prefix": None, "prefix_token_count": 0,
        "prev_id": ids[index - 1] if index else None,
        "next_id": ids[index + 1] if index + 1 < len(ids) else None,
        "parent_node_id": None, "content_type": "prose",
        "errors": [] if MIN_TOKENS <= counts[index] <= MAX_TOKENS else ["C3"],
    } for index, page in enumerate(filled)]


def write_json(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("pdf", type=Path)
    pdf_path = arg_parser.parse_args().pdf
    doc_id = pdf_path.stem
    parser_info = {"name": "pdfplumber", "version": version("pdfplumber")}
    extracted_path = PROJECT_ROOT / "data" / "extracted" / "pdfplumber" / f"{doc_id}.json"
    chunk_path = PROJECT_ROOT / "data" / "chunks" / "pdfplumber" / CHUNKER["name"] / f"{doc_id}.json"
    run_id = new_run_id(0, "LOCAL")
    logger = CostLogger()

    with logger.stage("parse"):
        text, pages = parse_pdf(pdf_path)
        write_json(extracted_path, {"doc_id": doc_id, "parser": parser_info, "text": text, "pages": pages})

    with logger.stage("chunk"):
        frozen_text = json.loads(extracted_path.read_text(encoding="utf-8"))["text"]
        tokenizer = Tokenizer.from_pretrained(TOKENIZER["name"], revision=TOKENIZER["revision"])
        chunks = chunk_by_page(frozen_text, pages, tokenizer)

    chunk_doc = {
        "schema_version": "1.0",
        "document": {"doc_id": doc_id, "file_hash": file_sha256(pdf_path), "source_file": pdf_path.name,
                     "page_count": len(pages), "parser": parser_info},
        "run": {"run_id": run_id, "chunker": CHUNKER, "spec_version": SPEC_VERSION, "tokenizer": TOKENIZER,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
        "nodes": [], "chunks": chunks, "quality": {"layer1": {}, "layer2": {}}, "edges": [],
    }

    with logger.stage("validate"):
        chunk_doc["quality"]["layer1"] = layer1_report(chunk_doc, frozen_text, load_validator())
    write_json(chunk_path, chunk_doc)

    stack = {"parser": parser_info, "tokenizer": TOKENIZER, "chunker": CHUNKER}
    manifest_path = write_manifest(build_manifest(run_id, SPEC_VERSION, stack, [pdf_path], [extracted_path, chunk_path],
                                                  logger.summary(), "laptop"))
    print(json.dumps({"run_id": run_id, "pages": len(pages), "chunks": len(chunks),
                      "token_counts": [chunk["token_count"] for chunk in chunks],
                      "layer1": chunk_doc["quality"]["layer1"], "manifest": str(manifest_path)}, indent=2))


if __name__ == "__main__":
    main()