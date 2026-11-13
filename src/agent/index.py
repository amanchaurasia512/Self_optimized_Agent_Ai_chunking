"""Agent ask mode, index and retrieval (spec/agent_v1.md, Ask mode): a per-PDF cache of the extraction, chunk.json and
bge-m3 vectors, and retrieval exactly as scripts/aq_run.contexts does it (hybrid ranking, read within the budget)."""
import json
from functools import cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import numpy as np

from scripts.p3_score import load_chunks
from src.chunk.base import TOKENIZER
from src.common.manifest import file_sha256
from src.common.paths import AGENT_CACHE
from src.eval.embed import EMBEDDER, load_cache, save_part, text_key
from src.eval.score import BM25, dense_ranking, hybrid_ranking, read_ranking

BUDGETS = (750, 1250, 2000)
BATCH_SIZE = 16  # as scripts/p3_embed.py
PROGRESS_SLICE = 64  # texts per progress step, a multiple of BATCH_SIZE
PARSER_PACKAGES = {"docling": "docling", "pdfplumber": "pdfplumber"}
FILES = ("extraction.json", "chunks.json", "index.json")


def index_folder(planned, setting, root=AGENT_CACHE):
    """<root>/<PDF SHA-256>/<parser>_<setting>; an index built from an extraction file gets its own folder."""
    name = f"{planned['parser']}_{setting}"
    if planned["from_extraction"]:
        name += f"_extraction-{file_sha256(planned['from_extraction'])[:12]}"
    return Path(root) / planned["pdf_sha"] / name


def installed_parser_version(parser):
    try:
        return version(PARSER_PACKAGES[parser])
    except PackageNotFoundError:
        return None


def index_info(parser_info, chunker):
    return {"parser": parser_info, "chunker": chunker, "tokenizer": TOKENIZER, "embedder": EMBEDDER}


def cached_index(folder, parser, chunker):
    """(extraction, chunk document, info) when the folder holds a complete index built with the current chunker,
    tokenizer, embedder and installed parser version; None otherwise (the index is then rebuilt)."""
    folder = Path(folder)
    if not all((folder / name).exists() for name in FILES):
        return None
    info = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    installed = installed_parser_version(parser)
    current = (info["chunker"] == chunker and info["tokenizer"] == TOKENIZER and info["embedder"] == EMBEDDER
               and info["parser"]["name"] == parser and installed in (None, info["parser"]["version"]))
    if not current:
        return None
    read = lambda name: json.loads((folder / name).read_text(encoding="utf-8"))
    return read("extraction.json"), read("chunks.json"), info


@cache
def encoder():
    """bge-m3 as scripts/p3_embed.py loads it: pinned revision, float32, max length 8,192; CUDA when available."""
    import torch
    from sentence_transformers import SentenceTransformer
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(EMBEDDER["name"], revision=EMBEDDER["revision"], device=device,
                                model_kwargs={"dtype": torch.float32})
    model.max_seq_length = EMBEDDER["max_length"]
    return model


def embed(texts, progress=None, slice_size=PROGRESS_SLICE):
    """Normalised float32 vectors, one row per text. With progress, texts are embedded in slices and
    progress(done, total) is called after each (spec/agent_v1.md, App v1: quality guard on the top-ranked chunks)."""
    texts = list(texts)
    encode = lambda part: encoder().encode(part, batch_size=BATCH_SIZE, normalize_embeddings=True, convert_to_numpy=True,
                                           show_progress_bar=False).astype(np.float32)
    if progress is None or len(texts) <= slice_size:
        vectors = encode(texts)
        if progress:
            progress(len(texts), len(texts))
        return vectors
    parts = []
    for start in range(0, len(texts), slice_size):
        parts.append(encode(texts[start:start + slice_size]))
        progress(min(start + slice_size, len(texts)), len(texts))
    return np.concatenate(parts)


def save_index(folder, document, chunk_doc, info, embed_texts):
    """Writes the extraction, chunk.json and vectors; index.json last, so a stopped build is never taken as complete."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.json").unlink(missing_ok=True)
    (folder / "extraction.json").write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    (folder / "chunks.json").write_text(json.dumps(chunk_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    texts = [chunk["index_text"] for chunk in load_chunks(folder / "chunks.json")]
    save_part(folder, "chunks", [text_key(text) for text in texts], embed_texts(texts))
    (folder / "index.json").write_text(json.dumps(info, indent=2), encoding="utf-8")


def chunk_vectors(folder, chunks):
    cached, vectors = load_cache(folder)
    return vectors[[cached[text_key(chunk["index_text"])] for chunk in chunks]]


def retrieve(question, question_vector, chunks, vectors, text, budget):
    """(context, tokens read, chunk indexes read in reading order), as scripts/aq_run.contexts: hybrid ranking of BM25
    and dense, read within the budget, read parts joined by blank lines."""
    if budget not in BUDGETS:
        raise ValueError(f"budget must be one of {BUDGETS}, not {budget}")
    order = hybrid_ranking(BM25([chunk["index_text"] for chunk in chunks]).ranking(question),
                           dense_ranking(question_vector, vectors))
    taken, used = read_ranking(order, chunks, text, budget)
    read = list(dict.fromkeys(next(index for index in order if chunks[index]["start"] <= start < chunks[index]["end"])
                              for position, start, end in taken))
    return "\n\n".join(text[start:end] for position, start, end in taken), used, read
