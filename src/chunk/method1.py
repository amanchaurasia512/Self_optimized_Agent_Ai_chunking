"""P2 own method 1 (spec v1.2, A1-A11): cut a document along its structure tree (tree.py v4) at a token budget T.
A node that fits is one piece; one that does not is opened into its own text and children; fitting pieces under the
same parent are packed in order; regions without children are packed from whole blocks; a block larger than T is cut
between table rows or sentences, and a part still too large by tokens."""
import re
from bisect import bisect_left, bisect_right
from collections import defaultdict
import re
from src.chunk.base import MIN_TOKENS,token_counts, token_windows
from src.chunk.tree import build_tree, subtree_tokens

SENTENCE_END = re.compile(r"(?<=[.!?;।])\s+")


def pack(units, sizes, budget):
    """Consecutive units joined in order while their total fits the budget (A5, A6)."""
    pieces, current, used = [], None, 0
    for unit, size in zip(units, sizes):
        if current and used + size <= budget:
            current, used = (current[0], unit[1]), used + size
        else:
            if current:
                pieces.append(current)
            current, used = unit, size
    return pieces + ([current] if current else [])

def with_blocks(document):
    """A13: a document without parser blocks gets its non-empty lines as blocks (label 'text')."""
    if document.get("elements"):
        return document
    lines = [match.span() for match in re.finditer(r"[^\n]+", document["text"]) if match.group().strip()]
    return {**document, "elements": [{"start_char": start, "end_char": end, "label": "text"} for start, end in lines]}

def split_block(start, end, text, is_table, budget):
    """A7: a block larger than the budget, cut between table rows or sentences; a part still too large by tokens."""
    block = text[start:end]
    marks = [match.end() for match in (re.finditer(r"\n", block) if is_table else SENTENCE_END.finditer(block))]
    edges = [0, *marks, len(block)]
    parts = [(start + left, start + right) for left, right in zip(edges, edges[1:]) if block[left:right].strip()]
    sizes = token_counts(text[left:right] for left, right in parts)
    return [window for part, size in zip(parts, sizes)
            for window in ([part] if size <= budget else token_windows(text[part[0]:part[1]], budget, base=part[0]))]

def method1_tree(document, T):
    """Spans of the document cut along its tree at budget T (A3-A7, A5b)."""
    document = with_blocks(document)
    text = document["text"]
    nodes, stats = build_tree(document)
    sizes = dict(zip((node["node_id"] for node in nodes), subtree_tokens(nodes, text)))
    children = defaultdict(list)
    for node in nodes[1:]:
        children[node["parent_id"]].append(node)
    elements = sorted(document.get("elements", []), key=lambda element: element["start_char"])
    starts = [element["start_char"] for element in elements]
    labels = {element["start_char"]: element["label"] for element in elements}

    def tokens(span):
        return token_counts([text[span[0]:span[1]]])[0]

    def region(start, end):
        """A6/A7: a region packed from whole blocks; a block larger than T is split first."""
        edges = [start, *starts[bisect_right(starts, start):bisect_left(starts, end)], end]
        blocks = [(left, right) for left, right in zip(edges, edges[1:]) if text[left:right].strip()]
        units = [part for block, size in zip(blocks, token_counts(text[left:right] for left, right in blocks))
                 for part in ([block] if size <= T else split_block(*block, text, labels.get(block[0]) == "table", T))]
        return pack(units, token_counts(text[left:right] for left, right in units), T)

    def join_heading(packed, opened):
        """A5b: a last packed piece under MIN_TOKENS goes with the first piece of the opened child after it, if that fits T."""
        if packed and opened and tokens(packed[-1]) < MIN_TOKENS and tokens((packed[-1][0], opened[0][1])) <= T:
            return packed[:-1], [(packed[-1][0], opened[0][1])] + opened[1:]
        return packed, opened

    def cut(node):
        """A3-A5: the node whole if it fits, else its own text and children, fitting pieces packed in order."""
        start, end = node["start_char"], node["end_char"]
        below = children[node["node_id"]]
        if sizes[node["node_id"]] <= T:
            return [(start, end)]
        if not below:
            return region(start, end)
        own = region(start, below[0]["start_char"]) if text[start:below[0]["start_char"]].strip() else []
        pieces, units, unit_sizes = [], list(own), token_counts(text[left:right] for left, right in own)
        for child in below:
            if sizes[child["node_id"]] <= T:
                units.append((child["start_char"], child["end_char"]))
                unit_sizes.append(sizes[child["node_id"]])
            else:
                packed, opened = join_heading(pack(units, unit_sizes, T), cut(child))
                pieces += packed + opened
                units, unit_sizes = [], []
        return pieces + pack(units, unit_sizes, T)

    return cut(nodes[0])


def tree_nodes(document):
    """The tree in the chunk.json node format (as base.section_nodes), titles = label + title, without the root."""
    nodes, stats = build_tree(with_blocks(document))
    return [{"node_id": node["node_id"], "parent_id": None if node["parent_id"] == "n0000" else node["parent_id"],
             "level": node["level"], "title": f"{node['label']} {node['title']}".strip(),
             "start_char": node["start_char"], "end_char": node["end_char"]} for node in nodes[1:]]