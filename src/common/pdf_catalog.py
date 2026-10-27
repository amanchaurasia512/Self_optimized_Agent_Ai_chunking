"""Shared helpers for the test-PDF list (pdfs/catalog.csv): ids, PDF stats, adding or replacing rows."""
import re

import pandas as pd
from pypdf import PdfReader

from src.common.manifest import PROJECT_ROOT

PDF_MANIFEST = PROJECT_ROOT / "pdfs" / "catalog.csv"


def safe_id(prefix, name):
    return f"{prefix}_" + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def pdf_stats(path):
    reader = PdfReader(path)
    return {"pages": len(reader.pages), "text_chars": sum(len(page.extract_text() or "") for page in reader.pages)}


def update_manifest(rows):
    manifest = pd.DataFrame(rows)
    if PDF_MANIFEST.exists():
        existing = pd.read_csv(PDF_MANIFEST)
        manifest = pd.concat([existing[~existing["doc_id"].isin(manifest["doc_id"])], manifest], ignore_index=True)
    PDF_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(PDF_MANIFEST, index=False)