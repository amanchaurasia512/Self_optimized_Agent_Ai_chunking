"""P3 (spec v1.2 S5, S5b): the texts to embed and the vector cache. Texts = unique chunk texts (prefix + text) of every
chunk setting and the certain span-level gold questions of the chosen documents, keyed by SHA-256. The cache records
its embedder and refuses a mismatch; chunk.json never holds vectors."""
import hashlib
import json
from pathlib import Path

import numpy as np

from src.chunk.base import token_counts

EMBEDDER = {"name": "BAAI/bge-m3", "revision": "5617a9f61b028005a4858fdac845db406aefb181", "dimension": 1024,
            "max_length": 8192, "dtype": "float32", "normalized": True}


def text_key(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_texts(chunk_root, docs):
    """Unique chunk texts (prefix + text) with their token counts, in a stable order (parser, setting, document)."""
    texts = {}
    for path in sorted(Path(chunk_root).glob("*/*/*.json")):
        if path.stem in docs:
            for chunk in json.loads(path.read_text(encoding="utf-8"))["chunks"]:
                text = (chunk["prefix"] or "") + chunk["text"]
                texts.setdefault(text_key(text), {"kind": "chunk", "text": text,
                                                  "tokens": chunk["token_count"] + chunk["prefix_token_count"]})
    return texts


def question_texts(gold_root, docs):
    """Unique certain span-level gold questions of the documents (D3), with their token counts."""
    questions = {}
    for path in sorted(Path(gold_root).glob("spans_*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record["doc_id"] in docs and str(record["certain"]) == "True" and record["kind"] == "span" and record["method"] != "page":
                questions.setdefault(text_key(record["question"]), {"kind": "question", "text": record["question"]})
    counts = token_counts(item["text"] for item in questions.values())
    return {key: {**item, "tokens": count} for (key, item), count in zip(questions.items(), counts)}


def sample_windows(keys, share):
    """A share of the keys in three equal windows (the first, the middle and the last) for a code check."""
    size = max(1, round(len(keys) * share / 3))
    middle = len(keys) // 2 - size // 2
    return list(dict.fromkeys(keys[:size] + keys[middle:middle + size] + keys[-size:]))


def check_embedder(folder):
    """The cache folder's embedder must be this one; a new folder records it."""
    record = Path(folder) / "embedder.json"
    if record.exists() and json.loads(record.read_text(encoding="utf-8")) != EMBEDDER:
        raise ValueError(f"{folder} holds vectors of another embedder: {record.read_text(encoding='utf-8')}")
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps(EMBEDDER, indent=2), encoding="utf-8")


def load_cache(folder):
    """{text key: row} and the vector matrix of every part in the folder (empty when there is none)."""
    folder = Path(folder)
    if not (folder / "embedder.json").exists():
        return {}, np.zeros((0, EMBEDDER["dimension"]), dtype=np.float32)
    check_embedder(folder)
    keys, parts = [], []
    for keys_path in sorted(folder.glob("*.keys.json")):
        keys += json.loads(keys_path.read_text(encoding="utf-8"))
        parts.append(np.load(keys_path.with_name(keys_path.name.replace(".keys.json", ".npy"))))
    return {key: row for row, key in enumerate(keys)}, (np.vstack(parts) if parts else np.zeros((0, EMBEDDER["dimension"]), dtype=np.float32))


def save_part(folder, name, keys, vectors):
    check_embedder(folder)
    np.save(Path(folder) / f"{name}.npy", vectors.astype(np.float32))
    (Path(folder) / f"{name}.keys.json").write_text(json.dumps(keys), encoding="utf-8")