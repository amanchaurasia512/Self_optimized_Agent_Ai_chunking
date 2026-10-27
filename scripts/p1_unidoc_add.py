"""P1-R01: add the UniDoc-Bench PDFs extracted on Kaggle (P1-KN01) to the PDF catalogue."""
import shutil

import pandas as pd

from src.common.manifest import PROJECT_ROOT, file_sha256, project_path
from src.common.pdf_catalog import pdf_stats, update_manifest

UNIDOC_DIR = PROJECT_ROOT / "data" / "external" / "unidoc"
SELECTED_DIR = UNIDOC_DIR / "selected" / "unidoc_selected"
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "unidoc"
LICENCE = "CC BY-NC 4.0 (UniDoc-Bench; questions generated with GPT-4.1)"


def main():
    questions = pd.read_csv(UNIDOC_DIR / "usable_questions.csv", dtype={"doc_id": str})
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for pdf_path in sorted(SELECTED_DIR.glob("unidoc_*.pdf")):
        domain, source_id = pdf_path.stem.removeprefix("unidoc_").rsplit("_", 1)
        target = RAW_DIR / pdf_path.name
        shutil.copyfile(pdf_path, target)
        doc_questions = questions[(questions["domain"] == domain) & (questions["doc_id"] == source_id)]
        rows.append({"doc_id": pdf_path.stem, "source_dataset": "UniDoc-Bench", "source_title": source_id,
                     "source_path": f"Salesforce/UniDoc-Bench {domain}_pdfs.tar.gz -> {domain}/{source_id}.pdf (Kaggle P1-KN01)",
                     "licence": LICENCE, "file": project_path(target), "sha256": file_sha256(target),
                     "usable_questions": len(doc_questions), **pdf_stats(target)})
    update_manifest(rows)
    table = pd.DataFrame(rows)
    table["sha256_start"] = table["sha256"].str[:16]
    print(table[["doc_id", "pages", "text_chars", "usable_questions", "sha256_start"]].to_string(index=False))


if __name__ == "__main__":
    main()