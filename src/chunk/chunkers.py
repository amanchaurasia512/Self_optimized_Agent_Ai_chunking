"""P2 chunkers: each takes a frozen document plus its settings and returns character spans, before shared post-processing."""
from src.chunk.base import token_windows
from functools import lru_cache
from src.chunk.base import token_counts, token_windows
from src.chunk.vendor.adaptive_splitters import RecursiveSplitter
from src.chunk.vendor.adaptive_sentence import SentenceSplitter
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings

from src.chunk.vendor.adaptive_semantic import SemanticChunkerWrapper
SEMANTIC_MODEL = {"name": "Qwen/Qwen3-Embedding-0.6B", "revision": "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"}

# Separators of the Adaptive Chunking paper, copied from ekimetrics/adaptive-chunking (commit ea87ce8),
# src/adaptive_chunking/paper/replicate.py (MIT, Copyright (c) 2026 Ekimetrics).
SEPARATORS = [
    r"(?<=\n)#{1}\s", r"(?<=\n)#{2}\s", r"(?<=\n)#{3}\s", r"(?<=\n)#{4}\s", r"(?<=\n)#{5}\s", r"(?<=\n)#{6}\s",
    r"(?<=\n)\s*\(?[A-Za-z0-9]{1,4}[.)]\s+",
    r"(?<=\n)\s*[-*·•●▪◦‣▸▹○◯‒–—]\s+",
    r"\n{2,}", r"\n", r"[.!?]\s+", r",\s+", r"\s+", r"",
]

def fixed_token(document, size, overlap=0):
    """P2-R02: windows of `size` bge-m3 tokens, cut at word starts."""
    return token_windows(document["text"], size, overlap)

def page(document):
    """P2-R03: one span per page, from the parser's page offsets."""
    return [(entry["start_char"], entry["end_char"]) for entry in document["pages"]]

@lru_cache(maxsize=None)
def bge_tokens(text):
    """bge-m3 count for the vendored splitter, which asks for the same piece many times while it splits and merges."""
    return token_counts([text])[0]


def locate(pieces, text):
    """Exact offsets of the splitter's chunk strings: each is a substring of the text, in order, starting after the previous one."""
    spans, previous = [], -1
    for piece in pieces:
        start = text.find(piece, previous + 1)
        if start < 0:
            raise ValueError(f"chunk {len(spans)} not found in the text after offset {previous}")
        spans.append((start, start + len(piece)))
        previous = start
    return spans


def recursive(document, size, overlap=0):
    """P2-R04: Adaptive Chunking's recursive split-then-merge (vendored, commit ea87ce8) with the paper's separators and
    settings ('our_recurs' in its replicate.py), counted in bge-m3 tokens; chunk strings mapped back to exact offsets."""
    splitter = RecursiveSplitter(separators=SEPARATORS, chunk_size=size, chunk_overlap=overlap, is_separator_regex=True,
                                 attach_separator_to="start", length_function=bge_tokens, merging="to_chunk_size",
                                 merging_order="forward")
    return locate(splitter.split_text(document["text"]), document["text"])

def sentence(document, sentences=5):
    """Adaptive Chunking's sentence baseline (vendored, commit ea87ce8): Stanza English sentences, each keeping its
    trailing separator, grouped `sentences` at a time ('sentence' in its replicate.py); mapped back to exact offsets."""
    splitter = SentenceSplitter(method="stanza", sentences_per_chunk=sentences, device="cpu")
    return locate(splitter.split_text(document["text"]), document["text"])
def langchain_default(document):
    """Paper baseline 'langch_recurs_default': LangChain's RecursiveCharacterTextSplitter with all its defaults
    (4,000 characters, 200-character overlap, separators blank line / line break / space / character)."""
    return locate(RecursiveCharacterTextSplitter().split_text(document["text"]), document["text"])


def langchain_recursive(document, size, overlap=0):
    """Paper baseline 'langch_recurs_1100' (run at our sizes): LangChain's splitter with the paper's separators,
    separators kept at the start of a chunk, counted in bge-m3 tokens."""
    splitter = RecursiveCharacterTextSplitter(separators=SEPARATORS, chunk_size=size, chunk_overlap=overlap,
                                              is_separator_regex=True, keep_separator="start", length_function=bge_tokens)
    return locate(splitter.split_text(document["text"]), document["text"])

@lru_cache(maxsize=1)
def semantic_embeddings():
    """The paper's embedder for its semantic baseline, in float32 (set explicitly, never the model's default) with standard
    attention: flash_attention_2 and bfloat16 need an Ampere GPU. Uses the GPU when one is present (Kaggle), else CPU.
    'processor_kwargs' is the paper's 'tokenizer_kwargs' under its sentence-transformers 6 name (left padding)."""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return HuggingFaceEmbeddings(model_name=SEMANTIC_MODEL["name"], encode_kwargs={"batch_size": 16},
                                 model_kwargs={"device": device, "revision": SEMANTIC_MODEL["revision"],
                                               "processor_kwargs": {"padding_side": "left"},
                                               "model_kwargs": {"dtype": torch.float32}})


def semantic(document):
    """Paper baseline 'semantic': LangChain SemanticChunker (gradient breakpoints, its defaults) in the paper's wrapper,
    with Qwen3-Embedding-0.6B; chunk strings mapped back to exact offsets."""
    splitter = SemanticChunkerWrapper(embeddings=semantic_embeddings(), breakpoint_threshold_type="gradient")
    return locate(splitter.split_text(document["text"]), document["text"])

CHUNKERS = {"fixed_token": {"function": fixed_token, "version": "1.0"},
            "page": {"function": page, "version": "1.0"},
            "recursive": {"function": recursive, "version": "1.0+adaptive-chunking-ea87ce8"},
            "sentence": {"function": sentence, "version": "1.0+adaptive-chunking-ea87ce8+stanza-1.15.0"},
            "langchain_default": {"function": langchain_default, "version": "1.0+langchain-text-splitters-1.1.3"},
            "langchain_recursive": {"function": langchain_recursive, "version": "1.0+langchain-text-splitters-1.1.3"},
            "semantic": {"function": semantic, "version": "1.0+adaptive-chunking-ea87ce8+langchain-experimental-0.4.2+qwen3-emb-0.6b-97b0c61-fp32"}}