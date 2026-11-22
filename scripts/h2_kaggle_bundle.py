"""Held-out 2 Docling run (H2-KN01), upload side: build the folder for a private Kaggle dataset (H2-KD01) holding the
53 held_out_2 PDFs only (spec v1.2 "Held-out set 2: extraction"). Each PDF is saved as <doc_id>.pdf at the top level, so Docling's
output file is named by the doc id; names and SHA-256 come from pdfs/catalog.csv and are checked. Refuses without
--final, refuses any document outside held_out_2, never overwrites a bundle, and re-checks the finished folder.
Run from the repo root: python -m scripts.h2_kaggle_bundle --final"""
import argparse
import json
import shutil
from pathlib import Path

import pandas as pd

from src.common.manifest import PROJECT_ROOT, code_version, file_sha256
from src.common.pdf_catalog import PDF_MANIFEST
from src.common.split import SPLIT_FILE

SPLIT, EXPECTED_DOCUMENTS = "held_out_2", 53
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "kaggle" / "h2-kd01"
DATASET_ID = "aman125/h2-kd01-heldout2"


def held_out_2_ids():
    split = pd.read_csv(SPLIT_FILE)
    return set(split.loc[split["split"] == SPLIT, "doc_id"])


def check_bundle(bundle, docs, files):
    """The folder holds exactly one PDF per held_out_2 document, with the catalogue's SHA-256, and nothing else."""
    found = {path for path in bundle.rglob("*") if path.is_file()} - {bundle / "BUNDLE.json", bundle / "dataset-metadata.json"}
    strangers = sorted(str(path.relative_to(bundle)) for path in found
                       if path.parent != bundle or path.suffix != ".pdf" or path.stem not in docs)
    wrong = sorted(entry["path"] for entry in files if file_sha256(bundle / entry["path"]) != entry["sha256"])
    if strangers or wrong or {path.stem for path in found} != docs:
        raise PermissionError(f"bundle check failed: strangers {strangers}, wrong SHA-256 {wrong}")


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arg_parser.add_argument("--final", action="store_true", help="allow held-out documents (final evaluation only)")
    args = arg_parser.parse_args()
    if not args.final:
        raise PermissionError(f"{SPLIT} is sealed: the bundle needs --final (final evaluation only)")

    bundle, docs = args.output.resolve(), held_out_2_ids()
    if len(docs) != EXPECTED_DOCUMENTS:
        raise ValueError(f"{SPLIT} has {len(docs)} documents in {SPLIT_FILE.name}, expected {EXPECTED_DOCUMENTS}")
    if bundle.exists() and any(bundle.iterdir()):
        raise FileExistsError(f"{bundle} is not empty; choose another --output (bundles are never overwritten)")
    catalog = pd.read_csv(PDF_MANIFEST).set_index("doc_id")
    missing = sorted(docs - set(catalog.index))
    if missing:
        raise KeyError(f"{SPLIT} documents missing from {PDF_MANIFEST.name}: {missing}")

    bundle.mkdir(parents=True, exist_ok=True)
    files = []
    for doc_id in sorted(docs):
        source, sha256 = PROJECT_ROOT / catalog.loc[doc_id, "file"], catalog.loc[doc_id, "sha256"]
        if file_sha256(source) != sha256:
            raise ValueError(f"{source}: SHA-256 differs from {PDF_MANIFEST.name}")
        target = bundle / f"{doc_id}.pdf"
        shutil.copyfile(source, target)
        files.append({"doc_id": doc_id, "path": str(target.relative_to(bundle)), "sha256": sha256,
                      "pages": int(catalog.loc[doc_id, "pages"])})
    check_bundle(bundle, docs, files)

    record = {"bundle": "H2-KD01", "for_notebook": "H2-KN01", "code": code_version(), "split": SPLIT,
              "documents": sorted(docs), "pages": sum(entry["pages"] for entry in files), "files": files}
    (bundle / "BUNDLE.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    (bundle / "dataset-metadata.json").write_text(json.dumps(
        {"title": "H2-KD01 held-out 2", "id": DATASET_ID, "licenses": [{"name": "other"}]}, indent=2), encoding="utf-8")

    size = sum(path.stat().st_size for path in bundle.rglob("*.pdf"))
    print(f"documents: {len(docs)} ({SPLIT} only) | pages: {record['pages']} | PDFs: {size / 1e6:.1f} MB\nbundle: {bundle}\n"
          f"upload (private): kaggle datasets create -p {bundle}")


if __name__ == "__main__":
    main()
