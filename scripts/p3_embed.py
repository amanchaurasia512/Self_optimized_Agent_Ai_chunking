"""P3 (spec v1.2 S5, S5b): embed every text the scorer needs with bge-m3 (pinned revision, float32, normalised),
skipping texts already in the cache. --share below 1 is a code check on that share of the texts (first, middle and
last thirds) into a separate test cache: it checks the vectors, re-embeds a few texts for identical results, and
estimates the full run's time."""
import argparse
import time
from pathlib import Path

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

from src.common.manifest import PROJECT_ROOT
from src.common.split import tuning_ids
from src.eval.embed import EMBEDDER, chunk_texts, load_cache, question_texts, sample_windows, save_part
from src.common.cost_logger import CostLogger
from src.common.manifest import build_manifest, new_run_id, write_manifest

def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--chunks", type=Path, default=PROJECT_ROOT / "data" / "chunks")
    arg_parser.add_argument("--gold", type=Path, default=PROJECT_ROOT / "data" / "gold")
    arg_parser.add_argument("--cache", type=Path, default=PROJECT_ROOT / "data" / "embeddings" / "bge-m3")
    arg_parser.add_argument("--name", required=True, help="part name, e.g. P3-KN01-full")
    arg_parser.add_argument("--share", type=float, default=1.0)
    arg_parser.add_argument("--batch-size", type=int, default=16)
    arg_parser.add_argument("--machine", default="kaggle")
    arg_parser.add_argument("--run-source", default="KN01", help="run id source, e.g. KN01")
    args = arg_parser.parse_args()

    docs = tuning_ids()
    chunks, questions = chunk_texts(args.chunks, docs), question_texts(args.gold, docs)
    cached, cache_vectors = load_cache(args.cache)
    todo = {key: item for key, item in {**chunks, **questions}.items() if key not in cached}
    chunk_keys = [key for key, item in todo.items() if item["kind"] == "chunk"]
    question_keys = [key for key, item in todo.items() if item["kind"] == "question"]
    keys = (sample_windows(chunk_keys, args.share) + sample_windows(question_keys, args.share)
            if args.share < 1 else chunk_keys + question_keys)
    print(f"unique chunk texts {len(chunks):,} | questions {len(questions):,} | already cached {len(cached):,} | "
          f"to embed now {len(keys):,} ({sum(todo[key]['tokens'] for key in keys):,} tokens)")

    run_id, logger = new_run_id(3, args.run_source), CostLogger()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(EMBEDDER["name"], revision=EMBEDDER["revision"], device=device,
                                model_kwargs={"dtype": torch.float32})
    model.max_seq_length = EMBEDDER["max_length"]
    with logger.stage("embed") as stage:
        vectors = model.encode([todo[key]["text"] for key in keys], batch_size=args.batch_size, normalize_embeddings=True,
                               convert_to_numpy=True, show_progress_bar=True)
        stage["texts"] = len(keys)
        stage["tokens"] = sum(todo[key]["tokens"] for key in keys)

    norms = np.linalg.norm(vectors, axis=1)
    repeat = model.encode([todo[key]["text"] for key in keys[:8]], batch_size=args.batch_size, normalize_embeddings=True,
                          convert_to_numpy=True)
    print(f"device {device} | shape {vectors.shape} | all finite {bool(np.isfinite(vectors).all())} | "
          f"norms {norms.min():.4f}-{norms.max():.4f} | repeat max difference {np.abs(repeat - vectors[:8]).max():.2e}")
    save_part(args.cache, args.name, keys, vectors)

    seconds, all_tokens = stage["wall_seconds"], sum(item["tokens"] for item in todo.values())
    speed = stage["tokens"] / seconds
    print(f"embedded {len(keys):,} texts ({stage['tokens']:,} tokens) in {seconds:.0f} s = {speed:,.0f} tokens/s | "
          f"all {len(todo):,} texts ({all_tokens:,} tokens) would take about {all_tokens / speed / 60:.0f} min | saved to {args.cache}")
    stack = {"embedder": EMBEDDER, "device": device, "share": args.share, "batch_size": args.batch_size}
    outputs = [args.cache / f"{args.name}.npy", args.cache / f"{args.name}.keys.json", args.cache / "embedder.json"]
    inputs = sorted(args.gold.glob("spans_*.jsonl"))
    manifest_path = write_manifest(build_manifest(run_id, "v1.2", stack, inputs, outputs, logger.summary(), args.machine))
    print(f"run {run_id} | manifest: {manifest_path}")

if __name__ == "__main__":
    main()