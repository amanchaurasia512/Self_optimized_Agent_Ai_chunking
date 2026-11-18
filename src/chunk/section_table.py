"""Extension item 3 (spec v1.2, "Extension", clarification and amendment of 2026-11-18; added after the main study):
one chunk per top-level section of the frozen tree (tree.py v4; pdfplumber through rule A13), each Docling table row its
own chunk with the table's header row in the prefix (as method 1 rule A7), no other prefix. Shared post-processing,
except that table-row chunks skip merge-under-100 (amendment): the base's functions are reused unchanged, and only the
merge and chunk building have a separate path here, used by this chunker alone. pdfplumber has no table labels, so
there it is sections only."""
import re

from src.chunk.base import (MAX_TOKENS, MIN_TOKENS, SPEC_VERSION, TOKENIZER, content_type, error_codes, make_prefix,
                            node_path, owner_node, pages_of, section_nodes, span_tokens, split_long, table_header,
                            token_counts, trim)
from src.chunk.method1 import with_blocks
from src.chunk.tree import build_tree
from datetime import datetime, timezone


def tables_of(document):
    return [(element["start_char"], element["end_char"]) for element in document.get("elements", [])
            if element["label"] == "table"]


def table_rows(start, end, text):
    """The lines of a table part, a line with no letter or digit (a rule line) joined to the row above."""
    rows = []
    for match in re.finditer(r"[^\n]+", text[start:end]):
        span = (start + match.start(), start + match.end())
        if rows and not any(char.isalnum() for char in match.group()):
            rows[-1] = (rows[-1][0], span[1])
        else:
            rows.append(span)
    return rows


def section_table(document):
    """Spans: the text cut at every top-level section start and every table edge; table parts split into rows."""
    document = with_blocks(document)
    text = document["text"]
    nodes, stats = build_tree(document)
    tables = tables_of(document)
    cuts = sorted({0, len(text), *(node["start_char"] for node in nodes[1:] if node["parent_id"] == nodes[0]["node_id"]),
                   *(edge for table in tables for edge in table)})
    spans = []
    for left, right in zip(cuts, cuts[1:]):
        inside = any(start <= left and right <= end for start, end in tables)
        spans += table_rows(left, right, text) if inside else [(left, right)]
    return spans


def merge_small_keeping_rows(spans, text, is_row):
    """base.merge_small, except that a table-row chunk is never joined with a neighbour (amendment)."""
    merged = []
    for span in spans:
        if merged and not is_row(merged[-1]) and not is_row(span):
            joined = (merged[-1][0], max(merged[-1][1], span[1]))
            small = min(span_tokens(merged[-1], text), span_tokens(span, text)) < MIN_TOKENS
            if small and span_tokens(joined, text) <= MAX_TOKENS:
                merged[-1] = joined
                continue
        merged.append(span)
    return merged


def post_process_keeping_rows(spans, text, is_row):
    """base.post_process (trim, re-split over MAX_TOKENS, merge under MIN_TOKENS) with the row exemption."""
    trimmed = [trim(span, text) for span in spans]
    pieces = [piece for span in trimmed if span[1] > span[0] for piece in split_long(span, text)]
    return merge_small_keeping_rows(pieces, text, is_row)


def build_chunks_keeping_rows(spans, document, nodes):
    """base.build_chunks with the row exemption; the prefix is the table header only (no heading path)."""
    text, elements = document["text"], document.get("elements", [])
    tables = tables_of(document)
    final = post_process_keeping_rows(spans, text, lambda span: any(start <= span[0] and span[1] <= end for start, end in tables))
    texts = [text[span[0]:span[1]] for span in final]
    node_starts = [node["start_char"] for node in nodes]
    by_id = {node["node_id"]: node for node in nodes}
    owners = [owner_node(span[0], nodes, node_starts) for span in final]
    paths = [node_path(owner, by_id) for owner in owners]
    prefixes = [make_prefix([], table_header(span, elements, text), None) for span in final]
    counts, prefix_counts = token_counts(texts), token_counts([prefix or "" for prefix in prefixes])
    ids = [f"c{index:05d}" for index in range(len(final))]
    chunks = []
    for index, span in enumerate(final):
        pages = pages_of(span, document["pages"])
        chunks.append({"chunk_id": ids[index], "text": texts[index], "start_char": span[0], "end_char": span[1],
                       "pages": pages, "section_path": [node["title"] for node in paths[index]],
                       "token_count": counts[index], "prefix": prefixes[index], "prefix_token_count": prefix_counts[index],
                       "prev_id": ids[index - 1] if index else None,
                       "next_id": ids[index + 1] if index + 1 < len(ids) else None,
                       "parent_node_id": owners[index]["node_id"] if owners[index] else None,
                       "content_type": content_type(span, elements),
                       "errors": error_codes(texts[index], counts[index], pages)})
    return chunks


def chunk_document_keeping_rows(document, spans, chunker, run_id, source, heading_prefix=False, nodes=None,
                                prefix_budget=None):
    """base.chunk_document for section_table. The header prefix is part of the design, so the setting must be run with
    --heading-prefix (its name then says 'prefix'); the heading path itself is never added."""
    if not heading_prefix:
        raise ValueError("section_table puts the table header in the prefix: run it with --heading-prefix")
    nodes = nodes if nodes is not None else section_nodes(document)
    return {
        "schema_version": "1.0",
        "document": {"doc_id": document["doc_id"], "file_hash": source["sha256"], "source_file": source["file"],
                     "page_count": len(document["pages"]),
                     "parser": {"name": document["parser"]["name"], "version": document["parser"]["version"]}},
        "run": {"run_id": run_id, "chunker": chunker, "spec_version": SPEC_VERSION, "tokenizer": TOKENIZER,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
        "nodes": nodes, "chunks": build_chunks_keeping_rows(spans, document, nodes),
        "quality": {"layer1": {}, "layer2": {}}, "edges": [],
    }
