"""Compare one page across parsers: pdfplumber and Docling from the frozen extractions, OCRia-1 (LlamaParse agentic) live.
Only that page is sent to LlamaParse (10 credits); its output is cached, so re-running never spends credits twice."""
import argparse
import json

import pandas as pd
from pypdf import PdfReader, PdfWriter

from src.common.manifest import PROJECT_ROOT
from src.common.pdf_catalog import PDF_MANIFEST
from src.parse.llamaparse_parser import CREDITS_PER_PAGE, make_client, parse_pdf, parser_info

EXTRACTED = PROJECT_ROOT / "data" / "extracted"
PAGE_DIR = PROJECT_ROOT / "data" / "raw" / "page_test"
OCRIA_TIER = "agentic"


def frozen_page(parser, doc_id, page_number):
    document = json.loads((EXTRACTED / parser / f"{doc_id}.json").read_text(encoding="utf-8"))
    page = next(page for page in document["pages"] if page["page"] == page_number)
    return document["text"][page["start_char"]:page["end_char"]]


def ocria_page(doc_id, page_number):
    cache = EXTRACTED / "page_test" / f"llamaparse_{OCRIA_TIER}" / f"{doc_id}_p{page_number}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))["text"]
    catalog = pd.read_csv(PDF_MANIFEST).set_index("doc_id")
    page_pdf = PAGE_DIR / f"{doc_id}_p{page_number}.pdf"
    PAGE_DIR.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    writer.add_page(PdfReader(PROJECT_ROOT / catalog.loc[doc_id, "file"]).pages[page_number - 1])
    writer.write(page_pdf)
    text, pages = parse_pdf(page_pdf, make_client(), OCRIA_TIER)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"doc_id": doc_id, "page": page_number, "parser": parser_info(OCRIA_TIER), "text": text,
                                 "credits": len(pages) * CREDITS_PER_PAGE[OCRIA_TIER]}, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    return text


def describe(name, text):
    words = text.split()
    average = sum(len(word) for word in words) / max(len(words), 1)
    longest = sorted(words, key=len, reverse=True)[:5]
    print(f"\n{'=' * 25} {name} {'=' * 25}\n{text}")
    print(f"--- {name}: {len(text)} characters, {len(words)} words, average word length {average:.1f}; longest: {longest}")


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--doc-id", required=True)
    arg_parser.add_argument("--page", type=int, required=True, help="page number, starting at 1")
    arg_parser.add_argument("--parsers", nargs="+", default=["pdfplumber", "docling", "ocria"])
    args = arg_parser.parse_args()

    readers = {"pdfplumber": lambda: frozen_page("pdfplumber", args.doc_id, args.page),
               "docling": lambda: frozen_page("docling", args.doc_id, args.page),
               "ocria": lambda: ocria_page(args.doc_id, args.page)}
    for name in args.parsers:
        describe(name, readers[name]())


if __name__ == "__main__":
    main()