"""Held-out set 2, step 3 (spec v1.2 "Held-out set 2: step 3 embedding on Kaggle"), upload side: build the folder for
a private Kaggle dataset (H2-KD02) for notebook H2-KN02. Held_out_2 documents only; refuses without --final. Files keep
their repo paths so the notebook copies them straight into the clone:
  data/chunks/{parser}/{setting}/<doc_id>.json  the chunk files of the 26 primary setups (P4-FINAL-20261106-1)
  data/heldout2/questions.jsonl                 doc_id + question of every held_out_2 query (no gold, no boxes)
  data/embeddings/bge-m3/H2-KD02-cached.*       vectors of those texts already in the local bge-m3 cache, so the
                                                notebook embeds only new texts and the cache never holds a key twice
No PDFs, no extractions, no gold. Never overwrites; re-checks the finished folder and prints counts, size and the
estimated embedding time at the held-out-1 speed (P3-P4-KN01-20261105-1)."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.ext_kaggle_bundle import CACHE, PARSERS, copy
from scripts.heldout2_vidore_register import QUERIES_FILE
from src.common.manifest import PROJECT_ROOT, RUNS_DIR, code_version, file_sha256
from src.common.split import SPLIT_FILE, tuning_ids
from src.eval.embed import EMBEDDER, chunk_texts, save_part, text_key

DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "kaggle" / "h2-kd02"
DATASET_ID = "aman125/h2-kd02-heldout2"
PRIMARY_SETUPS = PROJECT_ROOT / "data" / "results" / "p4" / "P4-FINAL-20261106-1_primary_setups.csv"
SPEED_RUN = "P3-P4-KN01-20261105-1"
CACHED_PART = "H2-KD02-cached"
QUESTIONS = Path("data") / "heldout2" / "questions.jsonl"


def primary_settings():
    setups = pd.read_csv(PRIMARY_SETUPS).iloc[:, 0].str.split("/", expand=True)
    if len(setups) != 26 or setups.groupby(1)[0].nunique().ne(len(PARSERS)).any():
        raise SystemExit(f"{PRIMARY_SETUPS.name}: expected 26 setups, every setting on both parsers")
    return sorted(setups[1].unique())


def write_questions(bundle, docs):
    rows = [{"doc_id": query["doc_id"], "question": query["query"]}
            for query in map(json.loads, QUERIES_FILE.read_text(encoding="utf-8").splitlines())]
    if {row["doc_id"] for row in rows} != docs:
        raise SystemExit("queries.jsonl documents differ from held_out_2")
    target = bundle / QUESTIONS
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    return target, {text_key(row["question"]) for row in rows}


def write_cached_vectors(bundle, wanted):
    """Rows of the local cache for texts the notebook would embed (memory-mapped; first part wins, as in load_cache
    order); saved as one part so p3_embed skips them."""
    if json.loads((CACHE / "embedder.json").read_text(encoding="utf-8")) != EMBEDDER:
        raise ValueError(f"{CACHE} holds vectors of another embedder")
    found = {}
    for keys_path in sorted(CACHE.glob("*.keys.json")):
        rows = {key: row for row, key in enumerate(json.loads(keys_path.read_text(encoding="utf-8"))) if key in wanted}
        if rows:
            part = np.load(keys_path.with_name(keys_path.name.replace(".keys.json", ".npy")), mmap_mode="r")
            found.update({key: np.array(part[row]) for key, row in rows.items() if key not in found})
    keys = sorted(found)
    folder = bundle / "data" / "embeddings" / "bge-m3"
    save_part(folder, CACHED_PART, keys, np.stack([found[key] for key in keys]) if keys
              else np.zeros((0, EMBEDDER["dimension"]), np.float32))
    return [folder / name for name in (f"{CACHED_PART}.npy", f"{CACHED_PART}.keys.json", "embedder.json")], set(keys)


def check_bundle(bundle, docs):
    stems = {path.stem for path in (bundle / "data" / "chunks").rglob("*.json")}
    question_docs = {json.loads(line)["doc_id"] for line in (bundle / QUESTIONS).read_text(encoding="utf-8").splitlines()}
    if stems - docs or question_docs - docs:
        raise PermissionError(f"documents outside held_out_2 in the bundle: {sorted((stems | question_docs) - docs)}")


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arg_parser.add_argument("--final", action="store_true", help="allow held-out documents (final evaluation only)")
    args = arg_parser.parse_args()

    split = pd.read_csv(SPLIT_FILE)
    docs = set(split.loc[split["split"] == "held_out_2", "doc_id"])
    if docs - tuning_ids() and not args.final:
        raise PermissionError(f"held-out documents need --final (final evaluation only): {len(docs)}, e.g. {sorted(docs)[:3]}")
    if len(docs) != 53:
        raise SystemExit(f"held_out_2 has {len(docs)} documents, not 53")
    bundle = args.output.resolve()
    if bundle.exists() and any(bundle.iterdir()):
        raise FileExistsError(f"{bundle} is not empty; choose another --output (bundles are never overwritten)")

    settings = primary_settings()
    sources = [PROJECT_ROOT / "data" / "chunks" / parser / setting / f"{doc}.json"
               for parser in PARSERS for setting in settings for doc in sorted(docs)]
    missing = [str(path.relative_to(PROJECT_ROOT)) for path in sources if not path.exists()]
    if missing:
        raise FileNotFoundError(f"{len(missing)} chunk files missing, e.g. {missing[:3]}")
    files = [copy(source, bundle) for source in sources]
    question_file, question_keys = write_questions(bundle, docs)
    chunks = chunk_texts(bundle / "data" / "chunks", docs, settings)
    vector_files, cached = write_cached_vectors(bundle, set(chunks) | question_keys)
    check_bundle(bundle, docs)

    new_tokens = sum(item["tokens"] for key, item in chunks.items() if key not in cached)
    speed = json.loads((RUNS_DIR / f"{SPEED_RUN}.json").read_text())["costs"]["stages"][0]
    tokens_per_second = speed["tokens"] / speed["wall_seconds"]
    record = {"bundle": "H2-KD02", "for_notebook": "H2-KN02", "code": code_version(), "split": "held_out_2",
              "documents": sorted(docs), "parsers": PARSERS, "settings": settings, "setups": len(PARSERS) * len(settings),
              "chunk_texts": len(chunks), "questions": len(question_keys),
              "cached": {"chunks": len(set(chunks) & cached), "questions": len(question_keys & cached)},
              "files": [{"path": str(path.relative_to(bundle)), "sha256": file_sha256(path)}
                        for path in [*files, question_file, *vector_files]]}
    (bundle / "BUNDLE.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    (bundle / "dataset-metadata.json").write_text(json.dumps(
        {"title": "H2-KD02 heldout2", "id": DATASET_ID, "licenses": [{"name": "other"}]}, indent=2), encoding="utf-8")

    sizes = [path.stat().st_size for path in bundle.rglob("*") if path.is_file()]
    print(f"documents: {len(docs)} (held_out_2) | setups: {record['setups']} ({len(settings)} settings x 2 parsers) | "
          f"chunk files: {len(files)} | files: {len(sizes)} | size: {sum(sizes) / 1e6:.1f} MB\n"
          f"unique chunk texts: {len(chunks):,} | questions: {len(question_keys)} | already cached: {record['cached']}\n"
          f"to embed on Kaggle: {new_tokens:,} chunk tokens, about {new_tokens / tokens_per_second / 3600:.1f} h at the "
          f"{SPEED_RUN} speed ({tokens_per_second:,.0f} tokens/s)\nbundle: {bundle}")


if __name__ == "__main__":
    main()
