"""Method 1 v2, cross-references (spec v1.2, "method 1 v2 (cross-references): clarification before any code", X1-X12;
extension item 5, added after the main study). Cuts are method1_tree v1 noprefix (X1, checked against the v1 chunk
files); the prefix field holds "[refers to: <label> - <title>]" for nodes of the document's own tree (tree.py v4) that
the chunk's text points to. Labels and referring words come from the document itself; no word lists. Version 2.1:
the amendment after the D4 smoke test (X5' descendant search, X2' no labels at block or line starts, X4' two words)."""
import json
import re
from bisect import bisect_right
from collections import Counter, defaultdict

from src.chunk.base import chunk_document, token_counts
from src.chunk.method1 import with_blocks
from src.chunk.tree import build_tree
from src.common.manifest import PROJECT_ROOT

CHUNKS = PROJECT_ROOT / "data" / "chunks"
PREFIX_SHARE = 0.10  # X8: the cap of rule A9, 10% of T
PAREN = re.compile(r"\((\d+|[A-Za-z]|[ivxlcdm]{2,4}|[IVXLCDM]{2,4})\)")
NUMBER = re.compile(r"(?<![\w.(])(\d+(?:\.\d+)*)(?:-?([A-Z]))?(?!\w)((?:\((?:\d+|[A-Za-z]|[ivxlcdm]{2,4}|[IVXLCDM]{2,4})\))*)")
WORD_BEFORE = re.compile(r"([A-Za-z][A-Za-z-]*)\.?\s+$")
NODE_NUMBER = re.compile(r"(?:[A-Z](?:\.?[A-Z])+\.?\s*)?(\d+(?:\.\d+)*)(?:-?([A-Z]))?[.)]?")
NODE_ROMAN = re.compile(r"([A-Z](?:\.?[A-Z])+)\.?\s+([IVXLCDM]+)\.?")
CHAIN_GAP = re.compile(r"\s+(?:[A-Za-z][A-Za-z-]*\s+){0,2}")  # X4': up to two words
REPORTS = {}


def node_key(node):
    """X2: a referable label as (kind, value): paren "(3)" -> ("paren", "3"); dotted, heading or word number
    ("6.", "13-A", "FR 9") -> ("number", "6"); word roman ("CHAPTER II") -> ("roman", "CHAPTER II"). Others: None."""
    label = node["label"].strip()
    if match := PAREN.fullmatch(label):
        return "paren", match[1]
    if match := NODE_ROMAN.fullmatch(label):
        return "roman", f"{match[1].replace('.', '')} {match[2]}"
    if node["style"] and node["style"][0] in ("dotted", "word", "heading") and (match := NODE_NUMBER.fullmatch(label)):
        return "number", match[1] + (match[2] or "")
    return None


def own_word(style):
    return style[1].lower() if style and style[0] == "word" else None


def preceding_word(text, start):
    match = WORD_BEFORE.search(text, max(0, start - 40), start)
    return (match[1].lower(), match.start(1)) if match else (None, start)


def referring_words(text, number_styles, node_starts):
    """X3d: per number style, the word most often directly before a number equal to one of its label values (labels at
    their own node start not counted), kept if it stands before at least 2 distinct values; ties: alphabetical."""
    counts, values = defaultdict(Counter), defaultdict(lambda: defaultdict(set))
    for match in NUMBER.finditer(text):
        word, word_start = preceding_word(text, match.start())
        number = match[1] + (match[2] or "")
        if word and match.start() not in node_starts and word_start not in node_starts:
            for style in (style for style, numbers in number_styles.items() if number in numbers):
                counts[style][word] += 1
                values[style][word].add(number)
    learned = {}
    for style, counter in counts.items():
        word = min(counter, key=lambda word: (-counter[word], word))
        if len(values[style][word]) >= 2:
            learned[style] = word
    return learned


def at_block_or_line_start(position, text, block_starts):
    """X2': only spaces between the start of the line or of the parser block holding the position and the position."""
    line_start = text.rfind("\n", 0, position) + 1
    block_start = block_starts[bisect_right(block_starts, position) - 1] if block_starts and block_starts[0] <= position else 0
    return not text[max(line_start, block_start):position].strip()


def find_references(text, nodes, keyed, block_starts):
    """X2-X4: candidate references in document order as {"start", "end", "path"}; a path is a list of (key, styles)
    from outermost to innermost, styles None meaning any style."""
    node_starts = {node["start_char"] for node in nodes}
    number_styles = defaultdict(set)
    for node in nodes:
        if keyed.get(node["node_id"], ("",))[0] == "number":
            number_styles[node["style"]].add(keyed[node["node_id"]][1])
    learned = referring_words(text, number_styles, node_starts)
    present = set(keyed.values())
    atoms, consumed = [], set()
    for match in NUMBER.finditer(text):
        number, parens = match[1] + (match[2] or ""), PAREN.findall(match[3])
        word, word_start = preceding_word(text, match.start())
        styles = {style for style, numbers in number_styles.items() if number in numbers
                  and word and word in (own_word(style), learned.get(style))}
        start = word_start if styles else match.start()
        if ("number", number) not in present or not (styles or parens) or start in node_starts or match.start() in node_starts:
            continue
        atoms.append({"start": start, "end": match.end(),
                      "path": [(("number", number), styles or None), *((("paren", inner), None) for inner in parens)]})
        consumed.update(range(match.start(), match.end()))
    for word in {value.split()[0] for kind, value in present if kind == "roman"}:
        for match in re.finditer(rf"(?<![\w.])(?i:{re.escape(word)})\.?\s+([IVXLCDM]+)\b", text):
            key = ("roman", f"{word} {match[1]}")
            if key in present and match.start() not in node_starts:
                atoms.append({"start": match.start(), "end": match.end(), "path": [(key, None)]})
    for match in PAREN.finditer(text):
        key = ("paren", match[1])
        if key in present and match.start() not in consumed and match.start() not in node_starts:
            atoms.append({"start": match.start(), "end": match.end(), "path": [(key, None)]})
    atoms = sorted((atom for atom in atoms if not at_block_or_line_start(atom["start"], text, block_starts)),
                   key=lambda atom: atom["start"])
    return chain(atoms, text, nodes, keyed), learned


def level_of(atom, nodes, keyed):
    key, styles = atom["path"][0]
    return min(node["level"] for node in nodes if keyed.get(node["node_id"]) == key and (styles is None or node["style"] in styles))


def chain(atoms, text, nodes, keyed):
    """X4, X4': a reference followed, after at most two words, by one of a higher tree level is the inner part of it."""
    references = []
    for atom in atoms:
        previous = references[-1] if references else None
        if (previous and CHAIN_GAP.fullmatch(text, previous["end"], atom["start"])
                and level_of(atom, nodes, keyed) < previous["level"]):
            previous.update(end=atom["end"], path=atom["path"] + previous["path"], level=level_of(atom, nodes, keyed))
        else:
            references.append({**atom, "level": level_of(atom, nodes, keyed)})
    return references


def resolve(reference, keyed, children, parent, deepest):
    """X5' (amended X5): (status, node). Outer label: for the deepest node holding the reference and then each ancestor,
    nearest first, search all its descendants; the first with any match decides, the shallowest match wins, a tie at
    that depth is ambiguous. Inner labels (X4): among the outer node's descendants, shallowest first."""
    def shallowest(node, key, styles):
        frontier = children[node["node_id"]]
        while frontier:
            found = [item for item in frontier if keyed.get(item["node_id"]) == key and (styles is None or item["style"] in styles)]
            if found:
                return found
            frontier = [child for item in frontier for child in children[item["node_id"]]]
        return []

    (key, styles), *inner = reference["path"]
    scope, found = deepest, []
    while scope is not None and not found:
        found = shallowest(scope, key, styles)
        scope = parent.get(scope["node_id"])
    for key, styles in inner:
        if len(found) != 1:
            break
        found = shallowest(found[0], key, styles)
    return ("resolved", found[0]) if len(found) == 1 else ("ambiguous" if found else "unresolved", None)


def reference_text(node):
    label = node["label"].strip().rstrip(".")
    return f"[refers to: {label} - {node['title']}]" if node["title"] else f"[refers to: {label}]"


def capped(added, budget):
    """X8: (prefix, number kept): whole references dropped from the last until the prefix fits the budget."""
    for kept in range(len(added), 0, -1):
        prefix = " ".join(added[:kept]) + "\n"
        if not budget or token_counts([prefix])[0] <= budget:
            return prefix, kept
    return None, 0


def cross_references(document, spans, budget):
    """X5-X8 for the final chunk spans: (prefixes, per-document counts, per-reference details)."""
    document = with_blocks(document)
    text = document["text"]
    nodes, stats = build_tree(document)
    keyed = {node["node_id"]: key for node in nodes[1:] if (key := node_key(node))}
    by_id = {node["node_id"]: node for node in nodes}
    children, parent = defaultdict(list), {}
    for node in nodes[1:]:
        children[node["parent_id"]].append(node)
        parent[node["node_id"]] = by_id[node["parent_id"]]
    node_starts = [node["start_char"] for node in nodes]
    block_starts = sorted(element["start_char"] for element in document["elements"])
    references, learned = find_references(text, nodes, keyed, block_starts)
    counts = Counter(found=len(references))
    chunk_starts, prefixes, details = [start for start, end in spans], [], []
    by_chunk = defaultdict(list)
    for reference in references:
        index = bisect_right(chunk_starts, reference["start"]) - 1
        holder = nodes[bisect_right(node_starts, reference["start"]) - 1]
        while holder["end_char"] <= reference["start"] and holder["parent_id"]:
            holder = by_id[holder["parent_id"]]
        status, target = resolve(reference, keyed, children, parent, holder)
        counts[status] += 1
        by_chunk[index].append((reference, status, target))
    for index, (start, end) in enumerate(spans):
        owner = nodes[bisect_right(node_starts, start) - 1]
        ancestors = {owner["node_id"]}
        while owner["parent_id"]:
            owner = by_id[owner["parent_id"]]
            ancestors.add(owner["node_id"])
        items, seen = [], set()
        for reference, status, target in by_chunk[index]:
            if status == "resolved":
                status = ("same_chunk" if start <= target["start_char"] < end else "self" if target["node_id"] in ancestors
                          else "duplicate" if target["node_id"] in seen else "candidate")
                seen.add(target["node_id"])
            items.append({"chunk": index, "start": reference["start"], "reference": text[reference["start"]:reference["end"]],
                          "status": status,
                          "target": target, "added": reference_text(target) if status == "candidate" else None})
        candidates = [item for item in items if item["status"] == "candidate"]
        prefix, attached = capped([item["added"] for item in candidates], budget)
        for rank, item in enumerate(candidates):
            item["status"] = "attached" if rank < attached else "dropped_cap"
        counts.update(item["status"] for item in items if item["target"])  # ambiguous, unresolved: counted above
        counts["chunks_with_refs"] += attached > 0
        prefixes.append(prefix)
        details += items
    report = {name: counts[name] for name in ("found", "resolved", "ambiguous", "unresolved", "same_chunk", "self",
                                               "duplicate", "attached", "dropped_cap", "chunks_with_refs")}
    report["referring_words"] = "; ".join(f"{'/'.join(map(str, style))}: {word}" for style, word in sorted(learned.items(), key=str))
    return prefixes, report, details


def chunk_document_with_xref(document, spans, chunker, run_id, source, heading_prefix=False, nodes=None,
                             prefix_budget=None):
    """base.chunk_document without a heading prefix (X9), then X1 (cuts equal to v1, else stop) and the reference prefix
    (X7, X8: capped at 10% of T)."""
    if heading_prefix:
        raise ValueError("method1_xref has no heading prefix (X9): run it without --heading-prefix")
    chunk_doc = chunk_document(document, spans, chunker, run_id, source, False, nodes, prefix_budget)
    T, parser = chunker["settings"]["T"], document["parser"]["name"]
    v1_path = CHUNKS / parser / f"method1_tree_T{T}_noprefix" / f"{document['doc_id']}.json"
    v1_chunks = json.loads(v1_path.read_text(encoding="utf-8"))["chunks"]
    cuts = [(chunk["start_char"], chunk["end_char"]) for chunk in chunk_doc["chunks"]]
    if cuts != [(chunk["start_char"], chunk["end_char"]) for chunk in v1_chunks]:
        raise ValueError(f"X1: cuts differ from {v1_path}")
    prefixes, report, details = cross_references(document, cuts, prefix_budget)
    for chunk, prefix, count in zip(chunk_doc["chunks"], prefixes, token_counts([prefix or "" for prefix in prefixes])):
        chunk["prefix"], chunk["prefix_token_count"] = prefix, count
    extra = sum(chunk["token_count"] + chunk["prefix_token_count"] for chunk in chunk_doc["chunks"]) - \
        sum(chunk["token_count"] + chunk["prefix_token_count"] for chunk in v1_chunks)
    report.update(cuts_equal_v1=True, extra_index_tokens=extra, extra_per_chunk=round(extra / len(cuts), 2))
    REPORTS[(document["doc_id"], parser, T)] = report
    return chunk_doc


def xref_report(document, T):
    """X11 counts for the run record, from the chunk builder of the same document."""
    return REPORTS.pop((document["doc_id"], document["parser"]["name"], T))
