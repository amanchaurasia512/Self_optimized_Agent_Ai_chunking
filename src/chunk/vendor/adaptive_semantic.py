# Vendored from ekimetrics/adaptive-chunking, commit ea87ce8, src/adaptive_chunking/paper/splitters.py, lines 22-58
# MIT License, Copyright (c) 2026 Ekimetrics; full text in src/chunk/vendor/LICENSE_adaptive_chunking
import re
from typing import List, Tuple

from langchain_experimental.text_splitter import SemanticChunker


class SemanticChunkerWrapper(SemanticChunker):
    def __init__(self, *args, lookback_min: int = 32, **kwargs):
        """
        A subclass of SemanticChunker that keeps the base semantic breakpoints but remaps each chunk back to the original text using a whitespace-tolerant match, then makes chunks contiguous.
        """
        super().__init__(*args, **kwargs)
        self._lookback_min = lookback_min

    @staticmethod
    def _relaxed_pattern(s: str) -> re.Pattern:
        s = re.sub(r"\s+", " ", s.strip())
        parts = [re.escape(p) for p in s.split(" ")] if s else []
        return re.compile(r"\s+".join(parts), re.DOTALL | re.MULTILINE)

    def _map_chunks(self, chunks: List[str], text: str) -> List[Tuple[int,int]]:
        spans, cur = [], 0
        for ch in chunks:
            if not ch.strip():
                spans.append((cur, cur)); continue
            pat = self._relaxed_pattern(ch)
            m = pat.search(text, cur) or pat.search(text, max(0, cur - max(self._lookback_min, len(ch)//4)))
            if not m:
                raise ValueError("Could not remap a chunk back to the source text.")
            s, e = m.span(); spans.append((s, e)); cur = e
        return spans

    def split_text(self, text: str) -> List[str]:
        mutated = super().split_text(text)
        if not mutated:
            return []
        spans = self._map_chunks(mutated, text)
        boundaries = [0] + [s for s, _ in spans[1:]] + [len(text)]
        for i in range(1, len(boundaries)):
            if boundaries[i] < boundaries[i-1]:
                boundaries[i] = boundaries[i-1]
        return [text[boundaries[i]:boundaries[i+1]] for i in range(len(mutated))]

