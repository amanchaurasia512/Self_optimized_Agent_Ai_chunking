"""Extension Kaggle run (EXT-KN01), upload side: build the folder for a private Kaggle dataset (EXT-KD01) holding tuning
documents only (pdfs/split.csv via src/common/split.py; no --final). Files keep their repo paths so the notebook copies
them straight into the clone:
  data/raw/...                       the tuning PDFs (paths and SHA-256 from pdfs/catalog.csv, checked)
  data/extracted/{docling,pdfplumber} the frozen extractions
  data/gold/spans_{parser}.jsonl     gold span records of tuning documents only
  data/embeddings/bge-m3/            the cached vectors of the scorer's tuning questions only (src/eval/embed.py rule),
                                     so P3-EXT scores against the same question vectors as P3; no chunk vectors
Refuses any non-tuning document, re-checks the finished folder, and prints the document count and size."""
import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from src.common.manifest import PROJECT_ROOT, code_version, file_sha256
from src.common.pdf_catalog import PDF_MANIFEST
from src.common.split import tuning_ids
from src.eval.embed import EMBEDDER, question_texts, save_part

PARSERS = ["docling", "pdfplumber"]
CACHE = PROJECT_ROOT / "data" / "embeddings" / "bge-m3"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "kaggle" / "ext-kd01"
DATASET_ID = "aman125/ext-kd01-tuning"
QUESTION_PART = "EXT-KD01-questions"


def copy(source, bundle):
    target = bundle / source.relative_to(PROJECT_ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return target


def write_gold(bundle, docs):
    """Gold span records of tuning documents only, line for line as in data/gold."""
    counts = {}
    for parser in PARSERS:
        lines = (PROJECT_ROOT / "data" / "gold" / f"spans_{parser}.jsonl").read_text(encoding="utf-8").splitlines()
        kept = [line for line in lines if json.loads(line)["doc_id"] in docs]
        target = bundle / "data" / "gold" / f"spans_{parser}.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("".join(f"{line}\n" for line in kept), encoding="utf-8")
        counts[parser] = {"records": len(kept), "of": len(lines)}
    return counts


def write_question_vectors(bundle, docs):
    """Rows of the local cache for the scorer's tuning questions (memory-mapped, nothing else is read into memory)."""
    wanted = list(question_texts(bundle / "data" / "gold", docs))
    wanted_set, found = set(wanted), {}
    for keys_path in sorted(CACHE.glob("*.keys.json")):
        rows = {key: row for row, key in enumerate(json.loads(keys_path.read_text(encoding="utf-8"))) if key in wanted_set}
        if rows:
            part = np.load(keys_path.with_name(keys_path.name.replace(".keys.json", ".npy")), mmap_mode="r")
            found.update({key: np.array(part[row]) for key, row in rows.items() if key not in found})
    keys = [key for key in wanted if key in found]
    if json.loads((CACHE / "embedder.json").read_text(encoding="utf-8")) != EMBEDDER:
        raise ValueError(f"{CACHE} holds vectors of another embedder")
    save_part(bundle / "data" / "embeddings" / "bge-m3", QUESTION_PART, keys,
              np.stack([found[key] for key in keys]) if keys else np.zeros((0, EMBEDDER["dimension"]), np.float32))
    return {"questions": len(wanted), "cached": len(keys), "embedded_on_kaggle": len(wanted) - len(keys)}


def check_bundle(bundle, docs):
    """Every document file in the folder is a tuning document; every gold record belongs to one."""
    document_files = [path for path in (bundle / "data").rglob("*") if path.suffix in {".pdf", ".json"}
                      and "embeddings" not in path.parts]
    strangers = sorted({path.stem for path in document_files} - docs)
    gold_docs = {json.loads(line)["doc_id"] for path in (bundle / "data" / "gold").glob("*.jsonl")
                 for line in path.read_text(encoding="utf-8").splitlines()}
    if strangers or gold_docs - docs:
        raise PermissionError(f"non-tuning documents in the bundle: {strangers + sorted(gold_docs - docs)}")


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = arg_parser.parse_args()

    bundle, docs = args.output.resolve(), tuning_ids()
    if bundle.exists() and any(bundle.iterdir()):
        raise FileExistsError(f"{bundle} is not empty; choose another --output (bundles are never overwritten)")
    catalog = pd.read_csv(PDF_MANIFEST).set_index("doc_id")
    missing = sorted(docs - set(catalog.index))
    if missing:
        raise KeyError(f"tuning documents missing from {PDF_MANIFEST.name}: {missing}")

    files = []
    for doc_id in sorted(docs):
        pdf = PROJECT_ROOT / catalog.loc[doc_id, "file"]
        if Path(pdf).stem != doc_id or file_sha256(pdf) != catalog.loc[doc_id, "sha256"]:
            raise ValueError(f"{pdf}: name or SHA-256 differs from {PDF_MANIFEST.name}")
        sources = [pdf, *(PROJECT_ROOT / "data" / "extracted" / parser / f"{doc_id}.json" for parser in PARSERS)]
        files += [copy(source, bundle) for source in sources]
    gold = write_gold(bundle, docs)
    vectors = write_question_vectors(bundle, docs)
    check_bundle(bundle, docs)

    record = {"bundle": "EXT-KD01", "for_notebook": "EXT-KN01", "code": code_version(), "split": "tuning",
              "documents": sorted(docs), "gold": gold, "question_vectors": vectors,
              "files": [{"path": str(path.relative_to(bundle)), "sha256": file_sha256(path)} for path in files]}
    (bundle / "BUNDLE.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    (bundle / "dataset-metadata.json").write_text(json.dumps(
        {"title": "EXT-KD01 tuning", "id": DATASET_ID, "licenses": [{"name": "other"}]}, indent=2), encoding="utf-8")

    sizes = [path.stat().st_size for path in bundle.rglob("*") if path.is_file()]
    pdfs = sum(path.stat().st_size for path in bundle.rglob("*.pdf"))
    print(f"documents: {len(docs)} (tuning only) | files: {len(sizes)} | size: {sum(sizes) / 1e6:.1f} MB "
          f"(PDFs {pdfs / 1e6:.1f} MB)\ngold records: {gold}\nquestion vectors: {vectors}\nbundle: {bundle}")


if __name__ == "__main__":
    main()
