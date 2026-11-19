"""P3 (spec v1.2 S5, S5b): embed every text the scorer needs with bge-m3 (pinned revision, float32, normalised),
skipping texts already in the cache. --share below 1 is a code check on that share of the texts (first, middle and
last thirds) into a separate test cache: it checks the vectors, re-embeds a few texts for identical results, and
estimates the full run's time. --embedder nomic is the robustness embedder (spec v1.2 "Robustness embedder",
2026-11-19): nomic-embed-text-v1.5, pinned revision, 768 dimensions, task prefixes before chunk texts
and questions when encoding only (the cache key stays the text, as for bge-m3), own cache folder. --test writes the
run record to runs/tests/."""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

from src.common.manifest import PROJECT_ROOT, RUNS_DIR
from src.eval.embed import CACHE_FOLDERS, EMBEDDERS, chunk_texts, load_cache, question_texts, sample_windows, save_part
from src.common.cost_logger import CostLogger
from src.common.manifest import build_manifest, new_run_id, new_test_run_id, write_manifest
from src.common.split import all_ids, tuning_ids


def load_model(embedder, device):
    """The pinned model in float32; remote code only when the embedder record asks for it (bge-m3 as before)."""
    remote = {"trust_remote_code": True} if embedder.get("trust_remote_code") else {}
    model = SentenceTransformer(embedder["name"], revision=embedder["revision"], device=device,
                                model_kwargs={"dtype": torch.float32}, **remote)
    model.max_seq_length = embedder["max_length"]
    return model


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--embedder", choices=list(EMBEDDERS), default="bge-m3")
    arg_parser.add_argument("--chunks", type=Path, default=PROJECT_ROOT / "data" / "chunks")
    arg_parser.add_argument("--gold", type=Path, default=PROJECT_ROOT / "data" / "gold")
    arg_parser.add_argument("--cache", type=Path, help="default data/embeddings/<embedder folder>")
    arg_parser.add_argument("--name", required=True, help="part name, e.g. P3-KN01-full")
    arg_parser.add_argument("--share", type=float, default=1.0)
    arg_parser.add_argument("--batch-size", type=int, default=16)
    arg_parser.add_argument("--settings", nargs="+", help="setting folder names; default: every setting")
    arg_parser.add_argument("--docs", nargs="+", help="tuning doc ids; default: every tuning document")
    arg_parser.add_argument("--test", action="store_true", help="run record to runs/tests/ (use with a test --cache)")
    arg_parser.add_argument("--machine", default="kaggle")
    arg_parser.add_argument("--run-source", default="KN01", help="run id source, e.g. KN01")
    arg_parser.add_argument("--final", action="store_true", help="include held-out documents (final evaluation only)")
    args = arg_parser.parse_args()

    embedder = EMBEDDERS[args.embedder]
    cache = args.cache or PROJECT_ROOT / "data" / "embeddings" / CACHE_FOLDERS[args.embedder]
    docs = all_ids() if args.final else tuning_ids()
    if args.docs:
        if set(args.docs) - docs:
            raise PermissionError(f"not allowed without --final (final evaluation only): {sorted(set(args.docs) - docs)}")
        docs = set(args.docs)
    chunks, questions = chunk_texts(args.chunks, docs, args.settings), question_texts(args.gold, docs)
    cached, cache_vectors = load_cache(cache, embedder)
    todo = {key: item for key, item in {**chunks, **questions}.items() if key not in cached}
    chunk_keys = [key for key, item in todo.items() if item["kind"] == "chunk"]
    question_keys = [key for key, item in todo.items() if item["kind"] == "question"]
    keys = (sample_windows(chunk_keys, args.share) + sample_windows(question_keys, args.share)
            if args.share < 1 else chunk_keys + question_keys)
    print(f"embedder {embedder['name']} | unique chunk texts {len(chunks):,} | questions {len(questions):,} | "
          f"already cached {len(cached):,} | to embed now {len(keys):,} ({sum(todo[key]['tokens'] for key in keys):,} tokens)")

    run_id = new_test_run_id(3, args.run_source) if args.test else new_run_id(3, args.run_source)
    logger = CostLogger()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = load_model(embedder, device)
    prefixes = embedder.get("prefixes", {"chunk": "", "question": ""})
    inputs = [prefixes[todo[key]["kind"]] + todo[key]["text"] for key in keys]
    model_lengths = [len(ids) for ids in model.tokenizer(inputs)["input_ids"]] if inputs else [0]
    with logger.stage("embed") as stage:
        vectors = model.encode(inputs, batch_size=args.batch_size, normalize_embeddings=True,
                               convert_to_numpy=True, show_progress_bar=True)
        stage["texts"] = len(keys)
        stage["tokens"] = sum(todo[key]["tokens"] for key in keys)

    norms = np.linalg.norm(vectors, axis=1)
    repeat = model.encode(inputs[:8], batch_size=args.batch_size, normalize_embeddings=True, convert_to_numpy=True)
    print(f"device {device} | shape {vectors.shape} | all finite {bool(np.isfinite(vectors).all())} | "
          f"norms {norms.min():.4f}-{norms.max():.4f} | repeat max difference {np.abs(repeat - vectors[:8]).max():.2e} | "
          f"longest input {max(model_lengths):,} model tokens (limit {embedder['max_length']:,})")
    save_part(cache, args.name, keys, vectors, embedder)

    seconds, all_tokens = stage["wall_seconds"], sum(item["tokens"] for item in todo.values())
    speed = stage["tokens"] / seconds
    print(f"embedded {len(keys):,} texts ({stage['tokens']:,} tokens) in {seconds:.0f} s = {speed:,.0f} tokens/s | "
          f"all {len(todo):,} texts ({all_tokens:,} tokens) would take about {all_tokens / speed / 60:.0f} min | saved to {cache}")
    stack = {"embedder": embedder, "device": device, "share": args.share, "batch_size": args.batch_size}
    if args.settings or args.docs or args.test:
        stack.update(settings=args.settings, documents=sorted(docs), test=args.test)
    outputs = [cache / f"{args.name}.npy", cache / f"{args.name}.keys.json", cache / "embedder.json"]
    manifest = build_manifest(run_id, "v1.2", stack, sorted(args.gold.glob("spans_*.jsonl")), outputs, logger.summary(),
                              args.machine)
    if args.test:
        manifest_path = RUNS_DIR / "tests" / f"test_p3_embed_{args.embedder}_{run_id}.json"
        if manifest_path.exists():
            raise FileExistsError(f"test record already exists: {manifest_path}")
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    else:
        manifest_path = write_manifest(manifest)
    print(f"run {run_id} | manifest: {manifest_path}")

if __name__ == "__main__":
    main()
