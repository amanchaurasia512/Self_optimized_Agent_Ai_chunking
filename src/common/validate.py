"""Layer 1 checks for chunk.json: schema, offsets, links, provenance, coverage."""
import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "spec" / "chunk.schema.json"


def load_validator(schema_path=SCHEMA_PATH):
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def schema_errors(chunk_doc, validator):
    return [f"{'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
            for error in validator.iter_errors(chunk_doc)]


def offset_mismatches(chunks, source_text):
    return [chunk["chunk_id"] for chunk in chunks
            if source_text[chunk["start_char"]:chunk["end_char"]] != chunk["text"]]


def link_errors(chunk_doc):
    chunk_ids = [chunk["chunk_id"] for chunk in chunk_doc["chunks"]]
    known_chunks, known_nodes = set(chunk_ids), {node["node_id"] for node in chunk_doc["nodes"]}
    errors = [f"duplicate chunk_id: {chunk_id}" for chunk_id in sorted(known_chunks) if chunk_ids.count(chunk_id) > 1]
    for chunk in chunk_doc["chunks"]:
        targets = {"prev_id": known_chunks, "next_id": known_chunks, "parent_node_id": known_nodes}
        errors += [f"{chunk['chunk_id']}: {field} -> {chunk[field]}"
                   for field, valid_ids in targets.items() if chunk[field] is not None and chunk[field] not in valid_ids]
    return errors


def text_coverage(chunks, source_text):
    covered = bytearray(len(source_text))
    for chunk in chunks:
        start, end = chunk["start_char"], min(chunk["end_char"], len(source_text))
        covered[start:end] = b"\x01" * max(end - start, 0)
    content_positions = [index for index, char in enumerate(source_text) if not char.isspace()]
    return sum(covered[index] for index in content_positions) / len(content_positions) if content_positions else 0.0


def layer1_report(chunk_doc, source_text, validator):
    errors = schema_errors(chunk_doc, validator)
    if errors:
        return {"schema_valid": False, "schema_errors": errors, "passed": False}
    chunks = chunk_doc["chunks"]
    mismatches, broken_links = offset_mismatches(chunks, source_text), link_errors(chunk_doc)
    complete = sum(bool(chunk["pages"]) and bool(chunk["section_path"]) for chunk in chunks)
    return {
        "schema_valid": True,
        "offset_match_rate": 1 - len(mismatches) / len(chunks),
        "offset_mismatches": mismatches,
        "link_errors": broken_links,
        "provenance_complete_rate": complete / len(chunks),
        "text_coverage": text_coverage(chunks, source_text),
        "passed": not mismatches and not broken_links,
    }