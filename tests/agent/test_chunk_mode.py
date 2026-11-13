"""Agent chunk mode (spec/agent_v1.md, tests 1 and 2), on tuning documents only, from their existing extractions
(no Docling needed). Run records go to runs/tests/agent/, never to runs/."""
import json

import pandas as pd
import pytest
from jsonschema import Draft202012Validator

from src.agent.pipeline import choose_parser, chunk_pdf
from src.common import manifest
from src.common.paths import CHUNKS, EXTRACTED, PROJECT_ROOT
from src.common.pdf_catalog import PDF_MANIFEST
from src.common.split import tuning_ids

DOCS = ["cuad_cooltechnologies_inc_10_25_2017_ex_10_71_strategic_alliance_agreement", "ohr_academic_2405_14831v1",
        "indian_d3_fundamental_rules"]
PARSERS = ["docling", "pdfplumber"]
STUDY_SETTING = "method1_tree_T384_noprefix"
SCHEMA = json.loads((PROJECT_ROOT / "spec" / "chunk.schema.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def test_runs_dir(monkeypatch):
    runs = PROJECT_ROOT / "runs" / "tests" / "agent"
    runs.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(manifest, "RUNS_DIR", runs)
    return runs


def pdf_path(doc_id):
    assert doc_id in tuning_ids(), f"{doc_id} is not a tuning document"
    return PROJECT_ROOT / pd.read_csv(PDF_MANIFEST).set_index("doc_id").loc[doc_id, "file"]


def run_agent(doc_id, parser, tmp_path):
    output = tmp_path / parser / f"{doc_id}.json"
    return chunk_pdf(pdf_path(doc_id), output, from_extraction=EXTRACTED / parser / f"{doc_id}.json")


@pytest.mark.parametrize("parser", PARSERS)
def test_output_validates_against_schema(parser, tmp_path):
    chunk_doc, record_path = run_agent(DOCS[0], parser, tmp_path)
    errors = [error.message for error in Draft202012Validator(SCHEMA).iter_errors(chunk_doc)]
    assert errors == []
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["run_id"].startswith("A-LOCAL-")
    assert record["stack"]["parser"]["name"] == parser
    assert record["stack"]["pages_without_text"] == len(record["stack"]["pages_without_text_list"])
    assert {stage["stage"] for stage in record["costs"]["stages"]} == {"scan_check", "parse", "chunk"}
    assert "packages" in record["environment"]


@pytest.mark.parametrize("parser", PARSERS)
@pytest.mark.parametrize("doc_id", DOCS)
def test_reproduces_study_chunks(doc_id, parser, tmp_path):
    """Everything equals the study's chunk file except the run block (run id, time, chunker version)."""
    chunk_doc, record_path = run_agent(doc_id, parser, tmp_path)
    study = json.loads((CHUNKS / parser / STUDY_SETTING / f"{doc_id}.json").read_text(encoding="utf-8"))
    for key in ["schema_version", "document", "nodes", "chunks", "quality", "edges"]:
        assert chunk_doc[key] == study[key], f"{doc_id} / {parser}: '{key}' differs from the study's chunk file"
    assert chunk_doc["run"]["chunker"]["settings"] == study["run"]["chunker"]["settings"]
    assert chunk_doc["run"]["tokenizer"] == study["run"]["tokenizer"]


def test_parser_choice_rule():
    assert choose_parser(fast=False, empty_pages=[], page_count=5)[0] == "docling"
    assert choose_parser(fast=True, empty_pages=[], page_count=5)[0] == "pdfplumber"
    parser, reason = choose_parser(fast=True, empty_pages=[2, 4], page_count=5)
    assert parser == "docling" and "2 of 5 pages have no text layer" in reason
