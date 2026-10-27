"""LlamaParse (OCRia-1) parser via the LlamaCloud API, into the same frozen format as pdfplumber (text + page offsets).
Credits are estimated from the documented per-page tier price."""
import os
from importlib.metadata import version
from itertools import accumulate
from pathlib import Path

from llama_cloud import LlamaCloud

PAGE_SEPARATOR = "\n\n"
KEY_FILE = Path.home() / ".config" / "llamacloud" / "api_key"
CREDITS_PER_PAGE = {"fast": 1, "cost_effective": 3, "agentic": 10, "agentic_plus": 45}


def make_client():
    api_key = os.environ.get("LLAMA_CLOUD_API_KEY") or KEY_FILE.read_text(encoding="utf-8").strip()
    return LlamaCloud(api_key=api_key)


def parser_info(tier, ocr_lang=None):
    return {"name": "llamaparse", "sdk_version": version("llama-cloud"), "tier": tier, "parse_version": "latest",
            "ocr_lang": ocr_lang or []}


def parse_pdf(pdf_path, client, tier, ocr_lang=None):
    uploaded = client.files.create(file=str(pdf_path), purpose="parse")
    options = {"processing_options": {"ocr_parameters": {"languages": ocr_lang}}} if ocr_lang else {}
    result = client.parsing.parse(file_id=uploaded.id, tier=tier, version="latest", expand=["markdown"], **options)
    page_texts = [getattr(page, "markdown", "") or "" for page in result.markdown.pages]
    starts = [0, *accumulate(len(text) + len(PAGE_SEPARATOR) for text in page_texts[:-1])]
    pages = [{"page": number, "start_char": start, "end_char": start + len(text)}
             for number, (start, text) in enumerate(zip(starts, page_texts), start=1)]
    return PAGE_SEPARATOR.join(page_texts), pages