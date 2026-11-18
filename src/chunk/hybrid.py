"""Extension item 4 (spec v1.2, docling_hybrid clarification 83bbf6c, rules (4) and (5); added after the main study):
Docling HybridChunker, max 512 bge-m3 tokens. The chunk texts come from scripts/ext_docling_hybrid_convert.py (Docling
environment); here, with no Docling import, they are mapped to contiguous spans of the frozen Docling extraction.
(4) Located in order, whitespace ignored, after removing the serializer's list bullet ("- " at a line start). A located
chunk runs from the previous span's end (document start for the first) to its last matched non-space character; the
last runs to the document end. (5) An unlocated chunk is not repaired: its text joins the next located chunk's span."""
import json
import re
from functools import cache

from src.common.manifest import PROJECT_ROOT

HYBRID_CHUNKS = PROJECT_ROOT / "data" / "extracted" / "docling_hybrid"
DOCLING_VERSION = "2.143.0"
LIST_BULLET = re.compile(r"(?m)^- ")
SPACE = re.compile(r"\s+")


@cache
def mapping(doc_id, text):
    """(spans, report) for one document: rules (4) and (5)."""
    saved = json.loads((HYBRID_CHUNKS / f"{doc_id}.json").read_text(encoding="utf-8"))
    if saved["chunker"]["docling"] != DOCLING_VERSION:
        raise ValueError(f"HybridChunker output from Docling {saved['chunker']['docling']}, expected {DOCLING_VERSION}")
    kept = [position for position, char in enumerate(text) if not char.isspace()]
    squeezed = "".join(text[position] for position in kept)
    ends, after, unlocated = [], 0, []
    for chunk in saved["chunks"]:
        target = SPACE.sub("", LIST_BULLET.sub("", chunk["text"]))
        found = squeezed.find(target, after) if target else -1
        if found < 0:
            unlocated.append(chunk)
            continue
        after = found + len(target)
        ends.append(kept[after - 1] + 1)
    ends = [*ends[:-1], len(text)] if ends else [len(text)]
    spans = list(zip([0, *ends[:-1]], ends))
    report = {"hybrid_chunks": len(saved["chunks"]), "located": len(saved["chunks"]) - len(unlocated),
              "unlocated": len(unlocated), "unlocated_chars": sum(len(chunk["text"]) for chunk in unlocated),
              "unlocated_labels": sorted({label for chunk in unlocated for label in chunk["labels"]}),
              "text_identical": saved["comparison"]["text_identical"]}
    return spans, report


def docling_mapping(document):
    if document["parser"]["name"] != "docling":
        raise ValueError(f"docling_hybrid is defined for Docling only; got parser {document['parser']['name']!r}")
    return mapping(document["doc_id"], document["text"])


def docling_hybrid(document):
    """Contiguous spans of the frozen text for the shared post-processing."""
    return docling_mapping(document)[0]


def hybrid_report(document):
    """Per document, for the run record: chunks located and unlocated (rule 5), and the text comparison."""
    return docling_mapping(document)[1]
