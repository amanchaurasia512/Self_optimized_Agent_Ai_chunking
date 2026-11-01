"""P2-R01: shared chunking base. A chunker returns character spans over the frozen parser text; this module turns them
into spec v1 chunks: shared post-processing, exact offsets, bge-m3 token counts, provenance, heading prefix, error flags."""
from bisect import bisect_right
from datetime import datetime, timezone
from functools import cache

from tokenizers import Tokenizer

TOKENIZER = {"name": "BAAI/bge-m3", "revision": "5617a9f61b028005a4858fdac845db406aefb181"}
SPEC_VERSION = "v1.1"
MIN_TOKENS, MAX_TOKENS = 100, 1024
SPLIT_TOKENS = 1000  # re-split target under MAX_TOKENS: a re-tokenised piece can come out a few tokens longer
WORD_START = "\u2581"  # sentencepiece marks a token that starts a new word
HEADING_LABELS = {"title", "section_header"}
CONTENT_TYPES = {"table": "table", "list_item": "list"}


@cache
def tokenizer():
    return Tokenizer.from_pretrained(TOKENIZER["name"], revision=TOKENIZER["revision"])


def token_counts(texts):
    return [len(encoding.ids) for encoding in tokenizer().encode_batch(list(texts), add_special_tokens=False)]


def span_tokens(span, text):
    return token_counts([text[span[0]:span[1]]])[0]

def token_windows(text, size, overlap=0, base=0):
    """Spans of at most `size` tokens; each next window starts `overlap` tokens back. Cuts fall on word starts."""
    encoding = tokenizer().encode(text, add_special_tokens=False)
    offsets, tokens = encoding.offsets, encoding.tokens  # each access copies the whole list, so read them once
    word_start = [token.startswith(WORD_START) for token in tokens]
    spans, first = [], 0
    while first < len(offsets):
        last = min(first + size, len(offsets))
        if last < len(offsets):
            last = next((cut for cut in range(last, first, -1) if word_start[cut]), last)
        spans.append((base + offsets[first][0], base + offsets[last - 1][1]))
        if last == len(offsets):
            break
        restart = max(last - overlap, first + 1)
        first = next((cut for cut in range(restart, first, -1) if word_start[cut]), restart)
    return spans

def trim(span, text):
    start, end = span
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def split_long(span, text):
    if span_tokens(span, text) <= MAX_TOKENS:
        return [span]
    return [trim(piece, text) for piece in token_windows(text[span[0]:span[1]], SPLIT_TOKENS, base=span[0])]


def merge_small(spans, text):
    merged = []
    for span in spans:
        if merged:
            joined = (merged[-1][0], max(merged[-1][1], span[1]))
            small = min(span_tokens(merged[-1], text), span_tokens(span, text)) < MIN_TOKENS
            if small and span_tokens(joined, text) <= MAX_TOKENS:
                merged[-1] = joined
                continue
        merged.append(span)
    return merged


def post_process(spans, text):
    """Spec v1, shared by every chunker: re-split spans over MAX_TOKENS, then merge spans under MIN_TOKENS into the
    previous one when the result stays within MAX_TOKENS."""
    trimmed = [trim(span, text) for span in spans]
    pieces = [piece for span in trimmed if span[1] > span[0] for piece in split_long(span, text)]
    return merge_small(pieces, text)


def section_nodes(document):
    """Provisional flat sections from the parser's headings (Docling); the frozen section rule comes in P2-R06."""
    text = document["text"]
    headings = [element for element in document.get("elements", []) if element["label"] in HEADING_LABELS]
    ends = [heading["start_char"] for heading in headings[1:]] + [len(text)]
    return [{"node_id": f"n{index:04d}", "parent_id": None, "level": 1,
             "title": text[heading["start_char"]:heading["end_char"]].strip(),
             "start_char": heading["start_char"], "end_char": end}
            for index, (heading, end) in enumerate(zip(headings, ends))]


def owner_node(start, nodes, node_starts):
    position = bisect_right(node_starts, start)
    return nodes[position - 1] if position else None


def content_type(span, elements):
    covered = {"table": 0, "list": 0}
    for element in elements:
        kind = CONTENT_TYPES.get(element["label"])
        if kind:
            covered[kind] += max(0, min(span[1], element["end_char"]) - max(span[0], element["start_char"]))
    kind = max(covered, key=covered.get)
    return kind if 2 * covered[kind] > span[1] - span[0] else "prose"


def pages_of(span, pages):
    return [page["page"] for page in pages if page["start_char"] < span[1] and span[0] < page["end_char"]]


def error_codes(text, tokens, pages):
    codes = [] if MIN_TOKENS <= tokens <= MAX_TOKENS else ["C3"]
    codes += [] if any(char.isalnum() for char in text) else ["C5"]
    return codes + ([] if pages else ["C6"])


def build_chunks(spans, document, nodes, heading_prefix=False):
    text, elements = document["text"], document.get("elements", [])
    final = post_process(spans, text)
    texts = [text[span[0]:span[1]] for span in final]
    node_starts = [node["start_char"] for node in nodes]
    owners = [owner_node(span[0], nodes, node_starts) for span in final]
    paths = [[owner["title"]] if owner else [] for owner in owners]
    prefixes = [" > ".join(path) + "\n" if heading_prefix and path else None for path in paths]
    counts, prefix_counts = token_counts(texts), token_counts([prefix or "" for prefix in prefixes])
    ids = [f"c{index:05d}" for index in range(len(final))]
    chunks = []
    for index, span in enumerate(final):
        pages = pages_of(span, document["pages"])
        chunks.append({"chunk_id": ids[index], "text": texts[index], "start_char": span[0], "end_char": span[1],
                       "pages": pages, "section_path": paths[index], "token_count": counts[index],
                       "prefix": prefixes[index], "prefix_token_count": prefix_counts[index],
                       "prev_id": ids[index - 1] if index else None,
                       "next_id": ids[index + 1] if index + 1 < len(ids) else None,
                       "parent_node_id": owners[index]["node_id"] if owners[index] else None,
                       "content_type": content_type(span, elements),
                       "errors": error_codes(texts[index], counts[index], pages)})
    return chunks


def chunk_document(document, spans, chunker, run_id, source, heading_prefix=False):
    nodes = section_nodes(document)
    return {
        "schema_version": "1.0",
        "document": {"doc_id": document["doc_id"], "file_hash": source["sha256"], "source_file": source["file"],
                     "page_count": len(document["pages"]),
                     "parser": {"name": document["parser"]["name"], "version": document["parser"]["version"]}},
        "run": {"run_id": run_id, "chunker": chunker, "spec_version": SPEC_VERSION, "tokenizer": TOKENIZER,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
        "nodes": nodes, "chunks": build_chunks(spans, document, nodes, heading_prefix),
        "quality": {"layer1": {}, "layer2": {}}, "edges": [],
    }