"""P1: structure profile of every catalogue PDF from Docling's layout elements.
Replaces the pdfplumber font-size profile, which missed text-styled headings and was fooled by layout tables."""
import json

import pandas as pd

from src.common.manifest import PROJECT_ROOT
from src.common.pdf_catalog import PDF_MANIFEST

DOCLING_DIR = PROJECT_ROOT / "data" / "extracted" / "docling"
OLD_COLUMNS = ["chars_per_page", "tables", "table_char_share", "body_font_size", "heading_lines", "heading_levels",
               "image_only_pages", "docling_heading_depths", "docling_chars_per_page"]
               
HEADING_LABELS = {"title", "section_header"}


def element_words(element, text):
    return len(text[element["start_char"]:element["end_char"]].split())


def label_share(elements, labels, text):
    total_words = sum(element_words(element, text) for element in elements)
    labelled = sum(element_words(element, text) for element in elements if element["label"] in labels)
    return round(labelled / total_words, 3) if total_words else 0.0


def structure_profile(doc_id):
    document = json.loads((DOCLING_DIR / f"{doc_id}.json").read_text(encoding="utf-8"))
    elements, pages, text = document["elements"], document["pages"], document["text"]
    return {"docling_headings": sum(element["label"] in HEADING_LABELS for element in elements),
            "docling_table_share": label_share(elements, {"table"}, text),
            "docling_list_share": label_share(elements, {"list_item"}, text),
            "docling_words_per_page": round(len(text.split()) / len(pages)) if pages else 0,
            "docling_empty_pages": sum(page["start_char"] == page["end_char"] for page in pages)}

def main():
    catalog = pd.read_csv(PDF_MANIFEST)
    profiles = pd.DataFrame([structure_profile(doc_id) for doc_id in catalog["doc_id"]])
    catalog = pd.concat([catalog.drop(columns=OLD_COLUMNS + list(profiles.columns), errors="ignore"), profiles], axis=1)
    catalog.to_csv(PDF_MANIFEST, index=False)
    print(catalog[["doc_id", "pages", *profiles.columns]].to_string(index=False))


if __name__ == "__main__":
    main()