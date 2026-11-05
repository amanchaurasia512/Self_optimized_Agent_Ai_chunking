
"""P3 scorer v1 (spec v1.2, S1-S15 and D1-D4): ranking, budgeted reading and metrics for one question over one
document's chunks. BM25 on lower-cased words (D2), dense = cosine on cached bge-m3 vectors, hybrid = reciprocal rank
fusion. The ranking is read until the token budget: prefix counted, text already read counted once, the last chunk cut
at the budget (D1). Gold characters are counted without whitespace, so spacing never changes a score."""
import math
import re
from bisect import insort
from collections import Counter

import numpy as np

from src.chunk.base import token_counts, tokenizer

SCORER = {"version": "scorer_v1",
          "bm25": {"k1": 1.5, "b": 0.75, "idf": "log((N - n + 0.5) / (n + 0.5) + 1)", "words": "lower-cased [\\w Devanagari]+"},
          "hybrid": {"method": "reciprocal rank fusion", "k": 60},
          "characters": "gold characters counted without whitespace"}
WORD = re.compile(r"[\w\u0900-\u097F]+")


class BM25:
    """Okapi BM25 over one document's chunk texts, built once and queried per question."""

    def __init__(self, texts):
        self.counts = [Counter(WORD.findall(text.lower())) for text in texts]
        self.lengths = np.array([sum(counts.values()) for counts in self.counts], dtype=float)
        self.average = max(self.lengths.mean(), 1.0) if len(texts) else 1.0
        self.holders = Counter(term for counts in self.counts for term in counts)

    def ranking(self, question):
        k1, b = SCORER["bm25"]["k1"], SCORER["bm25"]["b"]
        scores = np.zeros(len(self.counts))
        for term in set(WORD.findall(question.lower())) & set(self.holders):
            frequency = np.array([counts[term] for counts in self.counts], dtype=float)
            idf = math.log((len(self.counts) - self.holders[term] + 0.5) / (self.holders[term] + 0.5) + 1)
            scores += idf * frequency * (k1 + 1) / (frequency + k1 * (1 - b + b * self.lengths / self.average))
        return np.argsort(-scores, kind="stable")


def dense_ranking(question_vector, chunk_vectors):
    return np.argsort(-(chunk_vectors @ question_vector), kind="stable")


def hybrid_ranking(*rankings):
    """Reciprocal rank fusion of rankings (rank 1 = best)."""
    scores = np.zeros(len(rankings[0]))
    for ranking in rankings:
        scores[ranking] += 1 / (SCORER["hybrid"]["k"] + np.arange(1, len(ranking) + 1))
    return np.argsort(-scores, kind="stable")


class Gold:
    """A question's gold pieces (overlaps merged) over the document text, counted in non-whitespace characters."""

    def __init__(self, pieces, nonspace):
        merged = []
        for start, end in sorted(pieces):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        self.pieces, self.nonspace = merged, nonspace
        self.total = sum(self.chars(start, end) for start, end in merged)

    def chars(self, start, end):
        return int(self.nonspace[end] - self.nonspace[start]) if end > start else 0

    def inside(self, start, end):
        """Gold characters inside a span of the text."""
        return sum(self.chars(max(start, left), min(end, right)) for left, right in self.pieces)

    def whole_in(self, chunks):
        """Evidence coverage (the ceiling): every piece lies whole inside one chunk."""
        return all(any(chunk["start"] <= start and end <= chunk["end"] for chunk in chunks) for start, end in self.pieces)


def unread(span, read):
    """Parts of a span not inside the spans already read (sorted, disjoint)."""
    parts, start = [], span[0]
    for left, right in read:
        if right <= start or left >= span[1]:
            continue
        if left > start:
            parts.append((start, left))
        start = max(start, right)
    return parts + ([(start, span[1])] if start < span[1] else [])


def read_ranking(order, chunks, text, budget):
    """[(position, start, end)] read from the ranking within the budget, and the tokens used (S6, D1): each chunk's
    prefix counted, text already read skipped (overlap counted once), the last part cut at the budget."""
    read, taken, used, position = [], [], 0, 0
    for index in order:
        if used >= budget:
            break
        chunk = chunks[index]
        parts = unread((chunk["start"], chunk["end"]), read)
        if not parts:
            continue
        position += 1
        used += chunk["prefix_tokens"]
        for start, end in parts:
            if used >= budget:
                break
            tokens = chunk["tokens"] if (start, end) == (chunk["start"], chunk["end"]) else token_counts([text[start:end]])[0]
            if used + tokens > budget:
                end = start + tokenizer().encode(text[start:end], add_special_tokens=False).offsets[budget - used - 1][1]
                tokens = budget - used
            taken.append((position, start, end))
            insort(read, (start, end))
            used += tokens
    return taken, min(used, budget)


def measure(order, chunks, text, gold, budget, chunk_gold):
    """Budget metrics (S8): Recall@B, Hit@B, Full@B, nDCG@B, Geom@B and the tokens read."""
    taken, used = read_ranking(order, chunks, text, budget)
    by_position = Counter()
    for position, start, end in taken:
        by_position[position] += gold.inside(start, end)
    covered = sum(by_position.values())
    dcg = sum(value / gold.total / math.log2(position + 1) for position, value in by_position.items())
    ideal = sorted(chunk_gold, reverse=True)[:max(by_position, default=0)]
    idcg = sum(value / gold.total / math.log2(rank + 2) for rank, value in enumerate(ideal))
    recall, ndcg = covered / gold.total, (dcg / idcg if idcg else 0.0)
    return {"recall": recall, "hit": covered > 0, "full": covered == gold.total, "ndcg": ndcg,
            "geom": math.sqrt(ndcg * recall), "tokens_read": used}


def rank_metrics(order, chunks, chunk_gold, text):
    """Budget-free metrics of a ranking: MRR, Hit@5, Hit@10 and the tokens read up to the first chunk with gold."""
    first = next((rank for rank, index in enumerate(order, start=1) if chunk_gold[index] > 0), None)
    tokens = read_ranking(order[:first], chunks, text, math.inf)[1] if first else None
    return {"mrr": 1 / first if first else 0.0, "hit5": bool(first and first <= 5), "hit10": bool(first and first <= 10),
            "tokens_to_first_hit": tokens}