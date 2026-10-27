"""P1: measure the structure of every PDF in pdfs/catalog.csv with pdfplumber and write it back to the manifest.
Headings are lines set larger than the document's own most common (body) font size."""
from collections import Counter

import pandas as pd
import pdfplumber

from src.common.manifest import PROJECT_ROOT

PDF_MANIFEST = PROJECT_ROOT / "pdfs" / "catalog.csv"


def inside(char, bbox):
    left, top, right, bottom = bbox
    return left <= char["x0"] and char["x1"] <= right and top <= char["top"] and char["bottom"] <= bottom


def page_profile(page):
    tables = page.find_tables()
    lines = [line for line in page.extract_text_lines(return_chars=True) if line["chars"]]
    return {"chars": len(page.chars), "tables": len(tables),
            "table_chars": sum(any(inside(char, table.bbox) for table in tables) for char in page.chars),
            "image_only": not page.chars and bool(page.images),
            "line_sizes": [round(sum(char["size"] for char in line["chars"]) / len(line["chars"]), 1) for line in lines]}


def document_profile(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        pages = [page_profile(page) for page in pdf.pages]
    total_chars = sum(page["chars"] for page in pages)
    sizes = [size for page in pages for size in page["line_sizes"]]
    body_size = Counter(sizes).most_common(1)[0][0] if sizes else 0.0
    return {"chars_per_page": round(total_chars / len(pages)),
            "tables": sum(page["tables"] for page in pages),
            "table_char_share": round(sum(page["table_chars"] for page in pages) / total_chars, 3) if total_chars else 0.0,
            "body_font_size": body_size,
            "heading_lines": sum(size > body_size for size in sizes),
            "heading_levels": len({size for size in sizes if size > body_size}),
            "image_only_pages": sum(page["image_only"] for page in pages)}


def main():
    manifest = pd.read_csv(PDF_MANIFEST)
    profiles = pd.DataFrame([document_profile(PROJECT_ROOT / file) for file in manifest["file"]])
    manifest = pd.concat([manifest.drop(columns=profiles.columns, errors="ignore"), profiles], axis=1)
    manifest.to_csv(PDF_MANIFEST, index=False)
    print(manifest[["doc_id", "pages", *profiles.columns]].to_string(index=False))


if __name__ == "__main__":
    main()