"""Tuning B: add the OHR-Bench PDFs extracted on Kaggle (P1-KN03) to the catalogue, verifying each file's hash
against the Kaggle log and recording the licence of the PDF's original source."""
import re
import shutil

import pandas as pd

from src.common.manifest import PROJECT_ROOT, file_sha256, project_path
from src.common.pdf_catalog import pdf_stats, safe_id, update_manifest

OHR_DIR = PROJECT_ROOT / "data" / "external" / "ohr_bench"
KAGGLE_DIR = PROJECT_ROOT / "data" / "external" / "kaggle_out" / "P1-KN03"
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "ohr"
QUESTIONS_LICENCE = "questions: CC BY 4.0 (OHR-Bench)"


def source_licence(doc_name):
    domain, name = doc_name.split("/", 1)
    if domain == "law":
        return f"{QUESTIONS_LICENCE}; PDF: CUAD contract (CC BY 4.0)"
    if name.startswith("DUDE_"):
        return f"{QUESTIONS_LICENCE}; PDF: DUDE document (per-document licence, DUDE licenses_metadata)"
    if re.fullmatch(r"\d{4}\.\d{4,5}v\d+", name):
        return f"{QUESTIONS_LICENCE}; PDF: arXiv (per-paper licence)"
    return f"{QUESTIONS_LICENCE}; PDF: original publisher (as distributed by OHR-Bench)"


def logged_hashes():
    log_text = next(KAGGLE_DIR.glob("*.log")).read_text(encoding="utf-8")
    return dict(re.findall(r"  (.+?): [\d,]+ bytes \| sha256 ([0-9a-f]{16})", log_text))


def main():
    selected = pd.read_csv(OHR_DIR / "selected_documents.csv")
    hashes = logged_hashes()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for record in selected.itertuples(index=False):
        source = KAGGLE_DIR / "ohr_selected" / (record.doc_name.replace("/", "__") + ".pdf")
        doc_id = safe_id("ohr", record.doc_name)
        target = RAW_DIR / f"{doc_id}.pdf"
        shutil.copyfile(source, target)
        sha256 = file_sha256(target)
        rows.append({"doc_id": doc_id, "source_dataset": "OHR-Bench v2", "source_title": record.doc_name,
                     "source_path": f"opendatalab/OHR-Bench pdfs.zip -> {record.doc_name}.pdf (Kaggle P1-KN03)",
                     "licence": source_licence(record.doc_name), "file": project_path(target), "sha256": sha256,
                     "set": "B", "ohr_domain": record.domain, "usable_questions": record.usable_questions,
                     "hash_matches_kaggle": hashes.get(record.doc_name) == sha256[:16], **pdf_stats(target)})
    update_manifest(rows)
    table = pd.DataFrame(rows)
    print(table[["doc_id", "ohr_domain", "pages", "text_chars", "usable_questions", "hash_matches_kaggle"]].to_string(index=False))
    print("\nall hashes match:", table["hash_matches_kaggle"].all())


if __name__ == "__main__":
    main()