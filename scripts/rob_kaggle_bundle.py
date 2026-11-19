"""Robustness embedder Kaggle run (ROB-KN01), upload side: build the folder for a private Kaggle dataset (ROB-KD01)
holding tuning documents only (pdfs/split.csv via src/common/split.py; no --final). Files keep their repo paths so the
notebook copies them straight into the clone:
  data/chunks/{parser}/{setting}/      the chunk files of the 34 setups (spec v1.2 "Robustness embedder", 2026-11-19)
  data/extracted/{docling,pdfplumber}  the frozen extractions (the scorer reads the text for the gold characters)
  data/gold/spans_{parser}.jsonl       gold span records of tuning documents only (the questions are in them)
No PDFs and no vectors: nomic embeds every chunk text and question on Kaggle. Refuses any non-tuning document, re-checks
the finished folder, and prints the counts and size."""
import argparse
import json
from pathlib import Path

from scripts.ext_kaggle_bundle import PARSERS, check_bundle, copy, write_gold
from scripts.rob_analyse import robustness_settings
from src.common.manifest import PROJECT_ROOT, code_version, file_sha256
from src.common.split import tuning_ids
from src.eval.embed import question_texts

DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "kaggle" / "rob-kd01"
DATASET_ID = "aman125/rob-kd01-tuning"


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = arg_parser.parse_args()

    bundle, docs, settings = args.output.resolve(), tuning_ids(), robustness_settings()
    if bundle.exists() and any(bundle.iterdir()):
        raise FileExistsError(f"{bundle} is not empty; choose another --output (bundles are never overwritten)")
    sources = [PROJECT_ROOT / "data" / "chunks" / parser / setting / f"{doc}.json"
               for parser in PARSERS for setting in settings for doc in sorted(docs)]
    sources += [PROJECT_ROOT / "data" / "extracted" / parser / f"{doc}.json" for parser in PARSERS for doc in sorted(docs)]
    missing = [str(path.relative_to(PROJECT_ROOT)) for path in sources if not path.exists()]
    if missing:
        raise FileNotFoundError(f"{len(missing)} files missing, e.g. {missing[:3]}")
    files = [copy(source, bundle) for source in sources]
    gold = write_gold(bundle, docs)
    check_bundle(bundle, docs)
    questions = len(question_texts(bundle / "data" / "gold", docs))

    record = {"bundle": "ROB-KD01", "for_notebook": "ROB-KN01", "code": code_version(), "split": "tuning",
              "documents": sorted(docs), "parsers": PARSERS, "settings": settings, "setups": len(PARSERS) * len(settings),
              "gold": gold, "scored_questions": questions,
              "files": [{"path": str(path.relative_to(bundle)), "sha256": file_sha256(path)} for path in files]}
    (bundle / "BUNDLE.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    (bundle / "dataset-metadata.json").write_text(json.dumps(
        {"title": "ROB-KD01 tuning", "id": DATASET_ID, "licenses": [{"name": "other"}]}, indent=2), encoding="utf-8")

    sizes = [path.stat().st_size for path in bundle.rglob("*") if path.is_file()]
    print(f"documents: {len(docs)} (tuning only) | setups: {record['setups']} | files: {len(sizes)} | "
          f"size: {sum(sizes) / 1e6:.1f} MB\ngold records: {gold} | unique scored questions: {questions}\nbundle: {bundle}")


if __name__ == "__main__":
    main()
