"""Extension item 2 (spec v1.2, "dynamic_token: definition before any code", D1-D9; added after the main study, our own
definition): from the current start, cut where the chunk is 128 to 512 bge-m3 tokens, at the strongest break in that
window (page break or blank line > table edge or Docling block end > sentence end > line end), the latest of that kind.
Tables (Docling) and blocks with no sentence end are never cut while they fit 1,024 tokens (D4); a larger one is cut
between rows (tables) or at line ends, else by tokens (D5). No break and no such unit: cut at 512 tokens (D6)."""
import re
from bisect import bisect_left, bisect_right

from src.chunk.base import MAX_TOKENS, SPLIT_TOKENS, token_counts, token_windows, tokenizer
from src.chunk.method1 import SENTENCE_END, with_blocks

LOW, HIGH = 128, 512
PAGE_OR_BLANK, BLOCK, SENTENCE, LINE = 1, 2, 3, 4


def units_of(document, text):
    """D4/D5 units: Docling tables and blocks with no sentence end inside, as (start, end, tokens, is_table)."""
    whole = [element for element in document["elements"]
             if element["label"] == "table" or not SENTENCE_END.search(text, element["start_char"], element["end_char"])]
    counts = token_counts(text[element["start_char"]:element["end_char"]] for element in whole)
    return [(element["start_char"], element["end_char"], count, element["label"] == "table")
            for element, count in zip(whole, counts)]


def break_kinds(document, text, docling, units):
    """D3: {position: strongest kind} of every allowed break. Breaks inside a unit that fits MAX_TOKENS are left out
    (D4); inside a larger table only row ends stay (D5)."""
    kinds = {}

    def add(position, kind):
        if 0 < position < len(text):
            kinds[position] = min(kind, kinds.get(position, kind))

    for page in document["pages"][:-1]:
        add(page["end_char"], PAGE_OR_BLANK)
    for match in re.finditer(r"\n[ \t]*\n", text):
        add(match.start(), PAGE_OR_BLANK)
    for element in document["elements"]:
        if docling:
            add(element["end_char"], BLOCK)
        if element["label"] == "table":
            add(element["start_char"], BLOCK)
        else:
            for match in SENTENCE_END.finditer(text, element["start_char"], element["end_char"]):
                add(match.start(), SENTENCE)
    for match in re.finditer(r"\n", text):
        add(match.start(), LINE)
    for start, end, count, is_table in units:
        for position in [position for position in kinds if start < position < end]:
            if count <= MAX_TOKENS or (is_table and kinds[position] != LINE):
                del kinds[position]
    return kinds


def dynamic_token_cuts(document):
    """[(start, end, reason)]: reason 'window' (D2/D3), 'D4' (grown to hold a unit), 'D5' (cut inside a unit over
    MAX_TOKENS), 'D6' (cut at HIGH tokens) or 'last' (D7)."""
    document = with_blocks(document)
    text, docling = document["text"], document["parser"]["name"] == "docling"
    units = units_of(document, text)
    kinds = break_kinds(document, text, docling, units)
    positions = sorted(kinds)
    offsets = tokenizer().encode(text, add_special_tokens=False).offsets
    token_starts, token_ends = [start for start, end in offsets], [end for start, end in offsets]

    def count(start, end):
        return max(0, bisect_right(token_ends, end) - bisect_left(token_starts, start))

    def latest_break(start, low, high):
        found = []
        for position in positions[bisect_right(positions, start):]:
            size = count(start, position)
            if size > high:
                break
            if size >= low:
                found.append(position)
        return found

    def by_tokens(start, size):
        return token_windows(text[start:], size, base=start)[0][1]

    cuts, current = [], 0
    while count(current, len(text)) > HIGH:
        window = latest_break(current, LOW, HIGH)
        if window:
            strongest = min(kinds[position] for position in window)
            cut, reason = max(position for position in window if kinds[position] == strongest), "window"
        else:
            point = token_ends[min(bisect_left(token_starts, current) + HIGH, len(token_ends)) - 1]
            unit = next((unit for unit in units if unit[0] < point < unit[1]), None)
            if unit and unit[2] <= MAX_TOKENS:
                cut, reason = (unit[1] if count(current, unit[1]) <= MAX_TOKENS else unit[0]), "D4"
            elif unit:
                rows = latest_break(current, HIGH + 1, MAX_TOKENS)
                cut, reason = (rows[-1] if rows else by_tokens(current, SPLIT_TOKENS)), "D5"
            else:
                cut, reason = by_tokens(current, HIGH), "D6"
            if cut <= current:
                cut, reason = by_tokens(current, HIGH), "D6"
        cuts.append((current, cut, reason))
        current = cut
    return cuts + [(current, len(text), "last")]


def dynamic_token(document):
    """Spans for the shared base (D7: no overlap, no prefix; post-processing unchanged)."""
    return [(start, end) for start, end, reason in dynamic_token_cuts(document)]
