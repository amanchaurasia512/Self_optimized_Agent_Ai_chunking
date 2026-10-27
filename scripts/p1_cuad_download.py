"""P1-R01: download the selected CUAD PDFs and record them in pdfs/manifest.csv."""
import re
import shutil
from pathlib import Path

import pandas as pd
from huggingface_hub import hf_hub_download, list_repo_files
from pypdf import PdfReader

from src.common.manifest import PROJECT_ROOT, file_sha256, project_path

REPO_ID = "theatticusproject/cuad"
CUAD_DIR = PROJECT_ROOT / "data" / "external" / "cuad"
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "cuad"
PDF_MANIFEST = PROJECT_ROOT / "pdfs" / "manifest.csv"
LICENCE = "CC BY 4.0"


def doc_id_for(title):
    return "cuad_" + re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")


def pdf_paths_by_title():
    matches = {}
    for name in list_repo_files(REPO_ID, repo_type="dataset"):
        if name.lower().endswith(".pdf"):
            matches.setdefault(Path(name).stem, []).append(name)
    return matches


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


def main():
    selected = pd.read_csv(CUAD_DIR / "selected_contracts.csv")
    paths = pdf_paths_by_title()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for record in selected.itertuples(index=False):
        candidates = paths.get(record.contract, [])
        if len(candidates) != 1:
            print(f"SKIPPED {record.contract}: {len(candidates)} matching PDFs {candidates}")
            continue
        downloaded = hf_hub_download(REPO_ID, candidates[0], repo_type="dataset", local_dir=CUAD_DIR)
        doc_id = doc_id_for(record.contract)
        target = RAW_DIR / f"{doc_id}.pdf"
        shutil.copyfile(downloaded, target)
        rows.append({"doc_id": doc_id, "source_dataset": "CUAD v1", "source_title": record.contract,
                     "source_path": candidates[0], "licence": LICENCE, "file": project_path(target),
                     "sha256": file_sha256(target), "length_group": record.length_group, "words": record.words,
                     **pdf_stats(target)})
    update_manifest(rows)
    print(pd.DataFrame(rows)[["length_group", "doc_id", "words", "pages", "text_chars"]].to_string(index=False))


if __name__ == "__main__":
    main()