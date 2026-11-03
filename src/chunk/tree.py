"""P2 own method 1: a document tree from the document's own headings and numbering (rules R1-R19, written before this
code). Candidates come from parser headings and label shapes; a style counts only if it proves itself in the document
(it starts at its first value and continues); levels come from the order in which styles appear and nest. Nothing
about any particular document is written into the rules."""
import re
from collections import defaultdict
from bisect import bisect_left, bisect_right
from src.chunk.base import token_counts

LABEL = re.compile(
    r"(?<![\w.])(?:"
    r"(?P<word>[A-Z](?:\.?[A-Z])+)(?:\.\s*|\s+)(?:(?P<word_roman>[IVXLCDM]+)|(?P<word_number>\d+)(?P<word_suffix>-?[A-Z])?)\b"
    r"|(?P<dotted>\d+(?:\.\d+)*)(?P<dotted_suffix>-?[A-Z])?(?P<dotted_end>[.)])(?=\s)"
    r"|\((?P<paren>\d+|[A-Za-z]|[ivxlcdm]{2,4}|[IVXLCDM]{2,4})\)(?=\s)"
    r"|(?P<letter>[A-Za-z]|[ivxlcdm]{2,4}|[IVXLCDM]{2,4})(?P<letter_end>[.)])(?=\s))")
HEADING_NUMBER = re.compile(r"(?P<number>\d+(?:\.\d+)*)\.?(?=\s+[A-Za-z])")
HEADING = ("heading", 1)
ROMAN_DIGITS = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
ROMAN_TABLE = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
               (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))
PAGE_FURNITURE = re.compile(r"\s*\d{1,4}\s*")
SENTENCE_MARK = re.compile(r"[.;:!?]")
INLINE_LEAD = re.compile(r"(?:[;:.]|[-–—](?=\s|$))\s*(?:\w+\s+)?$")
INTRO = re.compile(r"(?::|[-–—](?=\s|$))\s*$")


def roman_value(letters):
    values = [ROMAN_DIGITS[letter] for letter in letters.lower()]
    return sum(-value if index + 1 < len(values) and value < values[index + 1] else value
               for index, value in enumerate(values))


def to_roman(value):
    letters = ""
    for number, symbol in ROMAN_TABLE:
        count, value = divmod(value, number)
        letters += symbol * count
    return letters


def is_roman(letters):
    """A properly formed roman numeral (R7): XIV yes, CIVIL no."""
    return all(letter in ROMAN_DIGITS for letter in letters.lower()) and to_roman(roman_value(letters)) == letters.upper()


def with_suffix(value, suffix):
    """An inserted label after its own number (R6): 12 -> 12, 12-A -> 12.01, 12-B -> 12.02."""
    return value + (ord(suffix[-1].upper()) - 64) / 100 if suffix else value


def follows(previous, value):
    """True when value is the next label after previous: the next whole number (12 -> 13, 12-A -> 13), or an inserted
    label after its own number (12 -> 12-A -> 12-B)."""
    if value == int(value):
        return value == int(previous) + 1
    return int(value) == int(previous) and value > previous


def character_candidates(kind, characters):
    """(style, value) readings of a letter-type label: a letter, a roman numeral, or both when ambiguous (i, v, x...)."""
    case = "upper" if characters.isupper() else "lower"
    readings = [((kind, "letter", case), ord(characters.lower()) - 96)] if len(characters) == 1 else []
    return readings + ([((kind, "roman", case), roman_value(characters))] if is_roman(characters) else [])


def candidates(match):
    """(style, value) readings of a label (R5); a word label with a malformed roman numeral has none."""
    if match.re is HEADING_NUMBER:
        parts = match["number"].split(".")
        return [(("heading", len(parts)), int(parts[-1]))]
    if match["word"]:
        style = ("word", match["word"].replace(".", ""))
        if match["word_number"]:
            return [(style, with_suffix(int(match["word_number"]), match["word_suffix"]))]
        return [(style, roman_value(match["word_roman"]))] if is_roman(match["word_roman"]) else []
    if match["dotted"]:
        parts = match["dotted"].split(".")
        return [(("dotted", len(parts), match["dotted_end"]), with_suffix(int(parts[-1]), match["dotted_suffix"]))]
    if match["paren"]:
        label = match["paren"]
        return [(("paren", "digit"), int(label))] if label.isdigit() else character_candidates("paren", label)
    return character_candidates(f"letter{match['letter_end']}", match["letter"])


def placement(stack, seen, style, value):
    """(stack index, how): 'continue' an open sequence (R10), 'start' a new or restarted one (R11, R12), 'resume' a
    closed sequence at the level it first had (R13), 'gap' the same with numbers skipped (R14), 'fallback' to an open
    sequence of the same style, or 'new' for a style never seen not starting at its first value (R15)."""
    same = [index for index, entry in enumerate(stack) if entry["style"] == style]
    continuing = [index for index in same if follows(stack[index]["value"], value)]
    if continuing:
        return continuing[-1], "continue"
    if same and same[0] == 0 and value == 1:
        return 0, "start"
    earlier = seen.get(style)
    if value != 1 and not same and earlier and earlier["index"] <= len(stack):
        return earlier["index"], "resume" if follows(earlier["value"], value) else "gap"
    if value == 1 or not same:
        return len(stack), "start" if value == 1 else "new"
    return same[-1], "fallback"


def header_placement(stack, seen):
    """(stack index, value) for a heading without a number (R17): beside the open top numbered headings (taking no number
    of its own), at the level they first had, or one level below the deepest open node when none has been seen."""
    same = [index for index, entry in enumerate(stack) if entry["style"] == HEADING]
    if same:
        return same[0], stack[same[0]]["value"]
    earlier = seen.get(HEADING)
    if earlier and earlier["index"] <= len(stack):
        return earlier["index"], earlier["value"]
    return len(stack), 0


def choose(stack, seen, readings, following):
    """Pick a reading (R8): an ambiguous label (i, v, x...) is settled by the next label continuing it; otherwise prefer
    continuing an open sequence, then resuming a closed one, then starting one."""
    placed = [(reading, placement(stack, seen, *reading)) for reading in readings]
    confirmed = [item for item in placed if any(style == item[0][0] and follows(item[0][1], value) for style, value in following)]
    if len(placed) > 1 and confirmed:
        return confirmed[0]
    return next((item for how in ("continue", "resume", "start") for item in placed if item[1][1] == how), placed[0])


def leading_chain(text, position, end):
    """Labels at a position, possibly chained ('4. (1)')."""
    matches = []
    while (match := LABEL.match(text, position, end)) is not None:
        matches.append(match)
        position = match.end()
        while position < end and text[position].isspace():
            position += 1
    return matches


def is_title(prefix):
    """Text before a margin section number: a heading with at most one sentence mark, at its very end."""
    prefix = prefix.strip()
    return bool(prefix) and not SENTENCE_MARK.search(prefix[:-1])


def inline_lead(before, match):
    """Text before a label inside a block (R4): a sentence mark and at most one word ('; or (ii)'), or, for a section
    number, a capitalised heading after the last sentence mark ('...conformity. Appropriate Government to prepare 26.')."""
    if INLINE_LEAD.search(before):
        return True
    heading = re.split(r"[.;:!?]", before)[-1].strip()
    return bool(match["dotted"]) and SENTENCE_MARK.search(before) is not None and heading[:1].isupper()


def labelled(chain, kind, title, first, end, opens=False):
    """Items for a chain of labels: the first gets the kind (and whether an introducing ':' or dash precedes it), each
    later one depends on the one before it."""
    return [{"kind": kind if offset == 0 else "chain", "match": match, "readings": candidates(match),
             "title": title if offset == 0 else None, "requires": first + offset - 1, "end": end,
             "opens": opens and offset == 0} for offset, match in enumerate(chain)]


def allowed(kind, style, how, opens):
    """Inline labels must continue an open sequence, or start one right after ':' or a dash (R16); margin labels must fit
    a sequence; a label fitting no sequence is not a label (R15), nor is a letter or roman label skipping values (R14)."""
    if kind == "inline":
        return how == "continue" or (opens and how == "start")
    if how == "new" or (how in ("gap", "fallback") and style[1] in ("letter", "roman")):
        return False
    return kind != "margin" or how in ("continue", "start", "resume")


def proven_styles(items):
    """Styles that prove themselves (R9) among block-start and heading candidates: some label starts at its first value
    and some label directly continues the one before it in that style."""
    values = defaultdict(list)
    for item in items:
        if item["kind"] in ("lead", "margin", "chain", "heading"):
            for style, value in item["readings"]:
                values[style].append(value)
    return {style for style, found in values.items()
            if 1 in found and any(follows(previous, value) for previous, value in zip(found, found[1:]))}


def occurrences(document):
    """Every candidate in document order (R1-R4): 'lead' (block start), 'heading' (number on a parser heading),
    'margin' (section or chapter number after a heading), 'inline' (inside a block), 'chain' (labels right after any of
    these), and 'header' (a parser heading without a number). Table blocks give no labels (R20)."""
    text, items, skipped = document["text"], [], 0
    for element in document.get("elements", []):
        start, end = element["start_char"], element["end_char"]
        block = text[start:end]
        if PAGE_FURNITURE.fullmatch(block):
            skipped += 1
            continue
        if element["label"] == "table":
            continue
        first = start + len(block) - len(block.lstrip())
        header = element["label"] == "section_header"
        chain, kind, title = leading_chain(text, first, end), "lead", None
        if not chain and header and (number := HEADING_NUMBER.match(text, first, end)):
            chain, kind = [number], "heading"
        if not chain:
            margin = next((match for match in LABEL.finditer(text, start, end)
                           if (match["dotted"] or match["word"]) and is_title(text[start:match.start()])), None)
            if margin:
                chain, kind, title = leading_chain(text, margin.start(), end), "margin", text[start:margin.start()].strip()
        if not chain and header:
            items.append({"kind": "header", "readings": [], "text": block.strip(), "start": first, "end": end})
        items += labelled(chain, kind, title, len(items), end)
        position = chain[-1].end() if chain else start
        for match in LABEL.finditer(text, position, end):
            before = text[start:match.start()]
            if match.start() >= position and not match["word"] and inline_lead(before, match):
                inline_chain = leading_chain(text, match.start(), end)
                items += labelled(inline_chain, "inline", None, len(items), end, bool(INTRO.search(before)))
                position = inline_chain[-1].end()
    return items, skipped


def build_tree(document):
    """Nodes in document order (node_id, parent_id, level, label, style, how, title, start_char, end_char = subtree end)
    (R18), and counts for checking."""
    text = document["text"]
    items, skipped = occurrences(document)
    proven = proven_styles(items)
    for item in items:
        item["readings"] = [reading for reading in item["readings"] if reading[0] in proven]
    nodes = [{"node_id": "n0000", "parent_id": None, "level": 0, "label": "", "style": None, "how": None,
              "title": "document", "start_char": 0, "end_char": len(text)}]
    stack, seen, accepted, last_heading_end = [], {}, set(), None
    stats = {"page_numbers_skipped": skipped, "styles_proven": len(proven), "margin_titles": 0, "inline_labels": 0,
             "headings": 0, "headings_merged": 0, "resumed": 0, "sequence_breaks": 0}
    for index, item in enumerate(items):
        if item["kind"] == "header":
            if last_heading_end is not None and not text[last_heading_end:item["start"]].strip():
                nodes[-1]["title"] = f"{nodes[-1]['title']} · {item['text']}"[:160]
                last_heading_end = item["end"]
                stats["headings_merged"] += 1
                continue
            if nodes[-1]["level"] and not nodes[-1]["title"]:
                nodes[-1]["title"] = item["text"][:80]
                continue
            (position, value), style, how = header_placement(stack, seen), HEADING, "heading"
            label, title, start = "", item["text"][:80], item["start"]
        else:
            kind = "inline" if item["kind"] == "chain" and item["requires"] not in accepted else item["kind"]
            if not item["readings"]:
                continue
            following = next((later["readings"] for later in items[index + 1:] if later["readings"]), [])
            (style, value), (position, how) = choose(stack, seen, item["readings"], following)
            if not allowed(kind, style, how, item["opens"]):
                continue
            accepted.add(index)
            stats["margin_titles"] += kind == "margin"
            stats["inline_labels"] += kind == "inline"
            match = item["match"]
            label, start = match.group(0), match.start()
            title = item["title"] or text[match.end():item["end"]].strip(" \n.-–—:")[:80]
        stats["headings"] += how == "heading"
        stats["resumed"] += how == "resume"
        stats["sequence_breaks"] += how in ("fallback", "gap")
        stack[position:] = [{"style": style, "value": value, "node": len(nodes)}]
        seen[style] = {"index": seen.get(style, {}).get("index", position), "value": value}
        nodes.append({"node_id": f"n{len(nodes):04d}", "level": position + 1, "label": label, "style": style, "how": how,
                      "parent_id": nodes[stack[position - 1]["node"]]["node_id"] if position else "n0000",
                      "title": title, "start_char": start, "end_char": None})
        last_heading_end = item["end"] if how == "heading" else None
    for index, node in enumerate(nodes[1:], start=1):
        node["end_char"] = next((later["start_char"] for later in nodes[index + 1:] if later["level"] <= node["level"]), len(text))
    return nodes, stats

def subtree_tokens(nodes, text):
    return token_counts([text[node["start_char"]:node["end_char"]] for node in nodes])

def pack(text, start, end, cuts, budget):
    """Whole blocks packed in order up to the budget (R22): pieces of [start, end) cut only at block starts; a single
    block larger than the budget stays one (too big) piece."""
    edges = [start, *cuts, end]
    sizes = token_counts([text[left:right] for left, right in zip(edges, edges[1:])])
    pieces, piece_start, used = [], start, 0
    for left, size in zip(edges, sizes):
        if used and used + size > budget:
            pieces.append((piece_start, left))
            piece_start, used = left, 0
        used += size
    return pieces + [(piece_start, end)]

def fit_report(nodes, document, budget):
    """What the tree offers at a token budget (R19, R22): every node that does not fit is opened into its own text and
    its children; every region is then packed from whole blocks. conf_lbl = share of tokens in fitting pieces using
    labels only; confidence = the same with blocks as the bottom level; largest = the biggest piece left."""
    text = document["text"]
    starts = sorted({element["start_char"] for element in document.get("elements", [])})
    children = defaultdict(list)
    for node in nodes[1:]:
        children[node["parent_id"]].append(node)
    sizes = dict(zip((node["node_id"] for node in nodes), subtree_tokens(nodes, text)))
    regions, pending = [], [nodes[0]]
    while pending:
        node = pending.pop()
        below = children[node["node_id"]]
        if sizes[node["node_id"]] <= budget or not below:
            regions.append((node["start_char"], node["end_char"]))
        else:
            regions.append((node["start_char"], below[0]["start_char"]))
            pending.extend(below)
    pieces = [piece for start, end in regions
              for piece in pack(text, start, end, starts[bisect_right(starts, start):bisect_left(starts, end)], budget)]

    def share(spans):
        counts = token_counts([text[start:end] for start, end in spans if text[start:end].strip()])
        return counts, round(sum(count for count in counts if count <= budget) / (sum(counts) or 1), 3)

    counts, confidence = share(pieces)
    return {"pieces": len(counts), "confidence": confidence, "conf_lbl": share(regions)[1], "largest": max(counts, default=0)}