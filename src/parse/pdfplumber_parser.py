"""pdfplumber parser: per-page text joined into one frozen document text, with each page's character offsets.
Named variants (RQ5a) pass extra extract_text options; the default passes none."""
from importlib.metadata import version
from itertools import accumulate

import pdfplumber

PAGE_SEPARATOR = "\n\n"
PARSER = {"name": "pdfplumber", "version": version("pdfplumber")}
VARIANTS = {"default": {}, "layout": {"layout": True}, "tolerance_wide": {"x_tolerance": 5}}


def parse_pdf(pdf_path, variant="default"):
    with pdfplumber.open(pdf_path) as pdf:
        page_texts = [page.extract_text(**VARIANTS[variant]) or "" for page in pdf.pages]
    starts = [0, *accumulate(len(text) + len(PAGE_SEPARATOR) for text in page_texts[:-1])]
    pages = [{"page": number, "start_char": start, "end_char": start + len(text)}
             for number, (start, text) in enumerate(zip(starts, page_texts), start=1)]
    return PAGE_SEPARATOR.join(page_texts), pages