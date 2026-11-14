"""The local app (spec/agent_v1.md, App v1) with Streamlit's AppTest: upload, index, ask twice, download. A fake bge-m3
(counted, to show it loads once) and a fake answer provider: no model and no API call. A tuning PDF only; the index
cache and run records live in pytest's temporary folder. Needs the app extra (the Docling environment)."""
import json

import pandas as pd
import pytest

pytest.importorskip("streamlit")
import streamlit as st
from streamlit.testing.v1 import AppTest

from app import explain
from src.agent import index, providers
from src.agent.pipeline import chunk_pdf
from src.common.paths import PROJECT_ROOT
from src.common.pdf_catalog import PDF_MANIFEST
from src.common.split import tuning_ids
from tests.agent.conftest import fake_embed

APP = PROJECT_ROOT / "app" / "streamlit_app.py"
DOC = "cuad_cooltechnologies_inc_10_25_2017_ex_10_71_strategic_alliance_agreement"
QUESTIONS = ["What is the term of the agreement?", "Who are the parties?"]


def pdf_path():
    assert DOC in tuning_ids(), f"{DOC} is not a tuning document"
    return PROJECT_ROOT / pd.read_csv(PDF_MANIFEST).set_index("doc_id").loc[DOC, "file"]


class FakeModel:
    """Stands in for SentenceTransformer: counts how often it is loaded."""
    loads = 0

    def __init__(self, *args, **options):
        FakeModel.loads += 1

    def encode(self, texts, **options):
        return fake_embed(texts)


@pytest.fixture
def app(tmp_path, monkeypatch):
    import sentence_transformers
    monkeypatch.setattr(sentence_transformers, "SentenceTransformer", FakeModel)
    monkeypatch.setattr(providers, "answer", lambda question, context: {
        "answer": f"answer to: {question}", "entry": "fake-a", "provider": "fake", "model": "fake-model"})
    monkeypatch.setattr(providers, "list_entries", lambda: [
        {"position": 1, "name": "fake-a", "provider": "fake", "model": "fake-model", "key_file_found": True, "status": "ready"}])
    monkeypatch.setenv("AGENT_CACHE_DIR", str(tmp_path / "cache"))
    FakeModel.loads = 0
    index.encoder.cache_clear()
    st.cache_resource.clear()
    yield AppTest.from_file(str(APP), default_timeout=120)
    index.encoder.cache_clear()
    st.cache_resource.clear()


def upload(at, data, name="contract.pdf"):
    at.sidebar.radio[0].set_value("fast").run()
    at.file_uploader[0].set_value((name, data, "application/pdf")).run()
    assert not at.exception, at.exception


def ask(at, question):
    at.text_input[0].input(question).run()
    at.button[0].click().run()
    assert not at.exception, at.exception


def test_upload_index_ask_twice_download(app, tmp_path):
    at = app.run()
    assert not at.exception and "50 MB" in at.file_uploader[0].label
    upload(at, pdf_path().read_bytes(), pdf_path().name)
    index_record = json.loads(open(at.session_state["index_record"], encoding="utf-8").read())
    assert index_record["stack"]["agent_mode"] == "app_index" and not index_record["stack"]["cache"]["hit"]
    assert [stage["stage"] for stage in index_record["costs"]["stages"]] == [
        "scan_check", "load_index", "parse", "chunk", "embed", "load_vectors"]
    shown = [element.proto.body for element in at.get("html")]  # the loop stopped; "✓ N chunks ready" remains
    chunks = len(at.session_state["session"]["chunks"])
    assert any('data-state="done"' in body and f"{chunks} chunks ready" in body for body in shown)
    assert not any('data-state="running"' in body for body in shown)
    assert explain.chunker_line(index_record) == "Chunker: method1_tree (structure-tree), 384 tokens, no prefix · parser: pdfplumber"
    assert any(explain.chunker_line(index_record) == caption.value for caption in at.caption)
    assert [expander.label for expander in at.sidebar.expander] == ["Why these settings?"]

    ask(at, QUESTIONS[0])
    at.sidebar.checkbox[0].check().run()
    ask(at, QUESTIONS[1])
    answers = at.session_state["answers"]
    assert [item["question"] for item in answers] == QUESTIONS[::-1]  # newest first
    assert FakeModel.loads == 1  # bge-m3 loaded once across the index and both questions
    for item in answers:
        assert item["answer"] == f"answer to: {item['question']}" and item["provider"]["entry"] == "fake-a"
        assert [row["step"] for row in item["steps"]] == ["Retrieve", "Answer"]
        assert item["sources"] and all(source["pages"] and 0 < len(source["snippet"]) <= 300 for source in item["sources"])
    records = {item["question"]: json.loads(open(item["run_record"], encoding="utf-8").read()) for item in answers}
    assert all(record["stack"]["agent_mode"] == "app_ask" for record in records.values())
    assert QUESTIONS[0] not in json.dumps(records[QUESTIONS[0]])  # "record text" was not ticked
    assert records[QUESTIONS[1]]["stack"]["question"]["text"] == QUESTIONS[1]  # ticked for the second

    downloaded = json.loads(at.session_state["chunk_json"])
    assert at.get("download_button")
    chunked, record_path = chunk_pdf(pdf_path(), tmp_path / "chunk_mode.json", fast=True)
    assert {key: downloaded[key] for key in downloaded if key != "run"} == {key: chunked[key] for key in chunked if key != "run"}
    assert downloaded["document"]["source_file"] == pdf_path().name


def test_same_pdf_again_uses_the_cached_index(app):
    at = app.run()
    upload(at, pdf_path().read_bytes())
    first = at.session_state["index_record"]
    second_session = app.__class__.from_file(str(APP), default_timeout=120).run()
    upload(second_session, pdf_path().read_bytes())
    record = json.loads(open(second_session.session_state["index_record"], encoding="utf-8").read())
    assert second_session.session_state["index_record"] != first and record["stack"]["cache"]["hit"]
    assert "parse" not in [stage["stage"] for stage in record["costs"]["stages"]]
    assert FakeModel.loads == 1


def test_file_over_the_limit_is_refused(app, tmp_path):
    at = app.run()
    upload(at, b"%PDF-1.7\n" + b"0" * (50 * 2**20 + 1))
    assert at.error and "limit is 50 MB" in at.error[0].value
    assert not (tmp_path / "cache" / "uploads").exists()
