"""P3 sanity-test chunkers (spec v1.2 S14), never part of the benchmark (setting names start with "sanity_").
Floor: boundaries at random character positions. Damage: method 1 (T=512) with a cut through the middle of every table."""
import hashlib
import random

from src.chunk.base import token_counts
from src.chunk.method1 import method1_tree


def seeded(document):
    """A random generator seeded by the document id, so every run cuts the same places."""
    return random.Random(int(hashlib.sha256(document["doc_id"].encode("utf-8")).hexdigest()[:8], 16))


def sanity_random_cut(document, size):
    """Floor: boundaries at random character positions (mid-word allowed), as many chunks as size-token windows give."""
    text = document["text"]
    count = max(1, round(token_counts([text])[0] / size))
    cuts = sorted(seeded(document).sample(range(1, len(text)), count - 1))
    edges = [0, *cuts, len(text)]
    return list(zip(edges, edges[1:]))


def sanity_table_split(document, T):
    """Damage: method 1 spans plus a cut at the middle line of every table block, so no larger table stays whole."""
    text = document["text"]
    cuts = []
    for element in document.get("elements", []):
        if element["label"] == "table":
            middle = (element["start_char"] + element["end_char"]) // 2
            line = text.find("\n", middle, element["end_char"])
            cuts.append(line + 1 if line >= 0 else middle)
    spans = []
    for start, end in method1_tree(document, T):
        edges = [start, *sorted(cut for cut in cuts if start < cut < end), end]
        spans += list(zip(edges, edges[1:]))
    return spans