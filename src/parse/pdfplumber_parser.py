"""pdfplumber parser: per-page text joined into one frozen document text, with each page's character offsets."""
from importlib.metadata import version
from itertools import accumulate

import pdfplumber

PAGE_SEPARATOR = "\n\n"
PARSER = {"name": "pdfplumber", "version": version("pdfplumber")}


def parse_pdf(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        page_texts = [page.extract_text() or "" for page in pdf.pages]
    starts = [0, *accumulate(len(text) + len(PAGE_SEPARATOR) for text in page_texts[:-1])]
    pages = [{"page": number, "start_char": start, "end_char": start + len(text)}
             for number, (start, text) in enumerate(zip(starts, page_texts), start=1)]
    return PAGE_SEPARATOR.join(page_texts), pages