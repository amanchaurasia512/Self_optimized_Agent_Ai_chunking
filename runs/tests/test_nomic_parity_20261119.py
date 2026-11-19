"""Parity check before ROB-KN01 (2026-11-19): do nomic-embed-text-v1.5 vectors from transformers' built-in nomic_bert
class (study .venv, transformers 5.22.1, trust_remote_code off) equal those from Nomic's remote code (throwaway
~/venv-nomic-parity, transformers 4.x + einops, trust_remote_code on)? Same pinned revision, float32, normalised, CPU,
batch size 16. Also checks that the edited p3_embed code reproduces the stored bge-m3 cache vectors.
Tuning documents only; reads the study's chunks, gold and bge-m3 cache, writes nothing in the study's data.

Steps (WORK = a scratch folder outside the repo):
  .venv/bin/python -m runs.tests.test_nomic_parity_20261119 select  WORK   # 25 chunk texts + 25 questions, seed 42
  ~/venv-nomic-parity/bin/python -I runs/tests/test_nomic_parity_20261119.py remote WORK   # no repo imports
  .venv/bin/python -m runs.tests.test_nomic_parity_20261119 native  WORK
  .venv/bin/python -m runs.tests.test_nomic_parity_20261119 compare WORK
  .venv/bin/python -m runs.tests.test_nomic_parity_20261119 bge-m3  WORK   # 20 cached texts re-embedded
"""
import json
import sys
from pathlib import Path

SEED, CHUNKS, QUESTIONS, RANK_QUESTIONS, RANK_CHUNKS, BGE_TEXTS, BATCH = 42, 25, 25, 5, 20, 20, 16
NAME, REVISION = "nomic-ai/nomic-embed-text-v1.5", "e9b6763023c676ca8431644204f50c2b100d9aab"


def encode(model, texts):
    return model.encode(texts, batch_size=BATCH, normalize_embeddings=True, convert_to_numpy=True)


def cosine_report(first, second):
    """Cosine in float64 (a float32 vector's dot with itself rounds just below 1), bit-identical rows, max abs difference."""
    import numpy as np
    first, second = first.astype(np.float64), second.astype(np.float64)
    cosines = (first * second).sum(axis=1) / np.linalg.norm(first, axis=1) / np.linalg.norm(second, axis=1)
    return (f"bit-identical vectors {int((first == second).all(axis=1).sum())} of {len(first)} | cosine (float64) "
            f"min {cosines.min():.10f} mean {cosines.mean():.10f} | max abs difference {np.abs(first - second).max():.3e}")


def select(work):
    import numpy as np
    from scripts.rob_analyse import robustness_settings
    from src.common.manifest import PROJECT_ROOT
    from src.common.split import tuning_ids
    from src.eval.embed import NOMIC, chunk_texts, question_texts
    assert NOMIC["revision"] == REVISION
    rng, docs = np.random.default_rng(SEED), tuning_ids()
    chunks = chunk_texts(PROJECT_ROOT / "data" / "chunks", docs, robustness_settings())
    questions = question_texts(PROJECT_ROOT / "data" / "gold", docs)
    pick = lambda pool, size: [pool[key]["text"] for key in rng.choice(sorted(pool), size, replace=False)]
    prefixes = NOMIC["prefixes"]
    texts = ([prefixes["chunk"] + text for text in pick(chunks, CHUNKS)]
             + [prefixes["question"] + text for text in pick(questions, QUESTIONS)])
    (work / "texts.json").write_text(json.dumps(texts, ensure_ascii=False), encoding="utf-8")
    print(f"selected {CHUNKS} chunk texts (of {len(chunks):,}, 34 setups) and {QUESTIONS} questions (of {len(questions):,}), "
          f"seed {SEED}, from {len(docs)} tuning documents")


def remote(work):
    import numpy as np
    import torch
    import transformers
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(NAME, revision=REVISION, device="cpu", trust_remote_code=True,
                                model_kwargs={"torch_dtype": torch.float32})
    model.max_seq_length = 8192
    texts = json.loads((work / "texts.json").read_text(encoding="utf-8"))
    np.save(work / "remote.npy", encode(model, texts))
    print(f"remote: transformers {transformers.__version__} | class {type(model[0].auto_model).__module__}."
          f"{type(model[0].auto_model).__name__} | dtype {next(model.parameters()).dtype} | {len(texts)} texts")


def native(work):
    import numpy as np
    import transformers
    from scripts.p3_embed import load_model
    from src.eval.embed import NOMIC
    model = load_model(NOMIC, "cpu")
    texts = json.loads((work / "texts.json").read_text(encoding="utf-8"))
    np.save(work / "native.npy", encode(model, texts))
    lengths = [len(ids) for ids in model.tokenizer(texts)["input_ids"]]
    print(f"native: transformers {transformers.__version__} | class {type(model[0].auto_model).__module__}."
          f"{type(model[0].auto_model).__name__} | dtype {next(model.parameters()).dtype} | {len(texts)} texts, "
          f"{min(lengths)}-{max(lengths)} model tokens")


def compare(work):
    import numpy as np
    remote_vectors, native_vectors = np.load(work / "remote.npy"), np.load(work / "native.npy")
    print(f"paired: {cosine_report(remote_vectors, native_vectors)} | shape {native_vectors.shape}")
    order = lambda vectors, question: np.argsort(-(vectors[:RANK_CHUNKS] @ vectors[CHUNKS + question]), kind="stable")
    same = [bool((order(remote_vectors, question) == order(native_vectors, question)).all()) for question in range(RANK_QUESTIONS)]
    print(f"rankings of {RANK_CHUNKS} chunk texts identical for {sum(same)} of {RANK_QUESTIONS} questions: {same}")


def bge_m3(work):
    import numpy as np
    from scripts.p3_embed import load_model
    from src.common.manifest import PROJECT_ROOT
    from src.common.split import tuning_ids
    from src.eval.embed import EMBEDDER, chunk_texts, load_cache, question_texts
    docs = tuning_ids()
    cached, vectors = load_cache(PROJECT_ROOT / "data" / "embeddings" / "bge-m3")
    texts = {**chunk_texts(PROJECT_ROOT / "data" / "chunks", docs), **question_texts(PROJECT_ROOT / "data" / "gold", docs)}
    keys = list(np.random.default_rng(SEED).choice(sorted(set(texts) & set(cached)), BGE_TEXTS, replace=False))
    fresh = encode(load_model(EMBEDDER, "cpu"), [texts[key]["text"] for key in keys])
    stored = vectors[[cached[key] for key in keys]]
    print(f"bge-m3: {BGE_TEXTS} cached texts re-embedded with the edited p3_embed code (CPU; cache made on Kaggle GPU) | "
          f"{cosine_report(fresh, stored)}")


if __name__ == "__main__":
    step, work = sys.argv[1], Path(sys.argv[2])
    work.mkdir(parents=True, exist_ok=True)
    {"select": select, "remote": remote, "native": native, "compare": compare, "bge-m3": bge_m3}[step](work)
