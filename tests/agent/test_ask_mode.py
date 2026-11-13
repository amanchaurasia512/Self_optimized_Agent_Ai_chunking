"""Agent ask mode (spec/agent_v1.md, Ask mode) on tuning documents only. No API calls: answers come from fake
providers. Retrieval is checked against scripts/aq_run.contexts with the study's cached bge-m3 vectors. The index cache
and run records live in pytest's temporary folder (tests/agent/conftest.py)."""
import json
from functools import partial

import numpy as np
import pandas as pd
import pytest

import src.agent.ask as ask_module
from scripts.aq_run import contexts
from scripts.p3_score import gold_questions, load_chunks
from src.agent import index, providers
from src.agent.ask import SETTING, ask_pdf
from src.agent.pipeline import chunk_pdf
from src.common.paths import CHUNKS, EMBEDDINGS, EXTRACTED, PROJECT_ROOT
from src.common.pdf_catalog import PDF_MANIFEST
from src.common.split import tuning_ids
from src.eval.embed import text_key

DOCS = ["cuad_cooltechnologies_inc_10_25_2017_ex_10_71_strategic_alliance_agreement", "ohr_academic_2405_14831v1",
        "indian_d3_fundamental_rules"]
PARSERS = ["docling", "pdfplumber"]
QUESTIONS_PER_DOC = 5
STUDY_CACHE = EMBEDDINGS / "bge-m3"


def pdf_path(doc_id):
    assert doc_id in tuning_ids(), f"{doc_id} is not a tuning document"
    return PROJECT_ROOT / pd.read_csv(PDF_MANIFEST).set_index("doc_id").loc[doc_id, "file"]


def sample_questions(parser, doc_id):
    questions = gold_questions(parser, {doc_id})[0]
    return [(question_id, questions[question_id]["question"]) for question_id in sorted(questions)[:QUESTIONS_PER_DOC]]


@pytest.fixture(scope="module")
def study_vectors():
    """Text key -> the study's cached vector, for the chunk texts and sample questions of DOCS only (memory-mapped)."""
    needed = {text_key(chunk["index_text"]) for parser in PARSERS for doc_id in DOCS
              for chunk in load_chunks(CHUNKS / parser / SETTING / f"{doc_id}.json")}
    needed |= {text_key(question) for parser in PARSERS for doc_id in DOCS for qid, question in sample_questions(parser, doc_id)}
    found = {}
    for keys_path in sorted(STUDY_CACHE.glob("*.keys.json")):
        rows = {key: row for row, key in enumerate(json.loads(keys_path.read_text(encoding="utf-8"))) if key in needed}
        if rows:
            matrix = np.load(keys_path.with_name(keys_path.name.replace(".keys.json", ".npy")), mmap_mode="r")
            found.update({key: np.array(matrix[row]) for key, row in rows.items()})
    assert needed <= set(found), f"{len(needed - set(found))} texts are missing from the study cache"
    return found


class Counting:
    """An embed function from a lookup table that counts what it was asked to embed."""

    def __init__(self, table):
        self.table, self.calls = table, []

    def __call__(self, texts):
        self.calls.append(len(texts))
        return np.stack([self.table[text_key(text)] for text in texts])


def ask_from_extraction(doc_id, parser, question, tmp_path, embed, **options):
    return ask_pdf(pdf_path(doc_id), question, from_extraction=EXTRACTED / parser / f"{doc_id}.json",
                   cache_root=tmp_path / "cache", embed=embed, **options)


@pytest.mark.parametrize("parser", PARSERS)
@pytest.mark.parametrize("doc_id", DOCS)
def test_retrieval_equals_aq_run_contexts(doc_id, parser, study_vectors, tmp_path):
    questions = sample_questions(parser, doc_id)
    cached = {key: row for row, key in enumerate(study_vectors)}
    vectors = np.stack(list(study_vectors.values()))
    sample = pd.DataFrame([{"doc_id": doc_id, "question_id": qid, "question": question} for qid, question in questions])
    expected = contexts(sample, [(parser, SETTING)], cached, vectors)
    embed = Counting(study_vectors)
    for question_id, question in questions:
        result = ask_from_extraction(doc_id, parser, question, tmp_path, embed, context_only=True)
        assert (result["context"], result["tokens_read"]) == expected[(parser, SETTING, doc_id, question_id)]
        assert result["answer"] is None and result["provider"] is None


@pytest.mark.parametrize("budget", index.BUDGETS)
def test_budget_never_exceeded(budget, study_vectors, tmp_path):
    for parser in PARSERS:
        for question_id, question in sample_questions(parser, DOCS[2]):
            result = ask_from_extraction(DOCS[2], parser, question, tmp_path, Counting(study_vectors),
                                         context_only=True, budget=budget)
            assert 0 < result["tokens_read"] <= budget


def test_other_budget_refused(study_vectors, tmp_path):
    with pytest.raises(ValueError, match="budget must be one of"):
        ask_from_extraction(DOCS[0], "docling", "What is the term?", tmp_path, Counting(study_vectors), budget=1000)


def test_cache_reused_and_rebuilt_on_version_change(study_vectors, tmp_path, monkeypatch):
    builds = []
    original_build = ask_module.build
    monkeypatch.setattr(ask_module, "build", lambda *args: builds.append(1) or original_build(*args))
    embed = Counting(study_vectors)
    question = sample_questions("docling", DOCS[0])[0][1]
    first = ask_from_extraction(DOCS[0], "docling", question, tmp_path, embed, context_only=True)
    chunk_count = len(json.loads((tmp_path / "cache").glob("*/*/chunks.json").__next__().read_text())["chunks"])
    assert not first["cache_hit"] and builds == [1] and embed.calls == [chunk_count, 1]
    second = ask_from_extraction(DOCS[0], "docling", question, tmp_path, embed, context_only=True)
    assert second["cache_hit"] and builds == [1] and embed.calls[2:] == [1]  # only the question is embedded
    assert second["context"] == first["context"]

    index_file = next((tmp_path / "cache").glob("*/*/index.json"))
    info = json.loads(index_file.read_text(encoding="utf-8"))
    info["chunker"]["version"] = "an older version"
    index_file.write_text(json.dumps(info), encoding="utf-8")
    third = ask_from_extraction(DOCS[0], "docling", question, tmp_path, embed, context_only=True)
    assert not third["cache_hit"] and builds == [1, 1]
    assert json.loads(index_file.read_text(encoding="utf-8"))["chunker"]["version"] != "an older version"


def test_cached_chunks_equal_chunk_mode_output(study_vectors, tmp_path):
    ask_from_extraction(DOCS[1], "pdfplumber", sample_questions("pdfplumber", DOCS[1])[0][1], tmp_path,
                        Counting(study_vectors), context_only=True)
    cached = json.loads(next((tmp_path / "cache").glob("*/*/chunks.json")).read_text(encoding="utf-8"))
    chunked, record_path = chunk_pdf(pdf_path(DOCS[1]), tmp_path / "chunk_mode.json",
                                     from_extraction=EXTRACTED / "pdfplumber" / f"{DOCS[1]}.json")
    assert {key: cached[key] for key in cached if key != "run"} == {key: chunked[key] for key in chunked if key != "run"}


@pytest.fixture
def fake_provider_answer(tmp_path):
    """providers.answer with a provider list in tmp_path and a fake adapter: the first entry hits its daily limit."""
    secret = "FAKE-SECRET-KEY-ask-91c2e7"
    key_file = tmp_path / "keys" / "fake"
    key_file.parent.mkdir()
    key_file.write_text(secret, encoding="utf-8")
    entries = [{"name": name, "provider": "fake", "model": model, "key_file": str(key_file)}
               for name, model in [("first", "model-limited"), ("second", "model-ok")]]
    config = tmp_path / "providers.json"
    config.write_text(json.dumps(entries), encoding="utf-8")

    def adapter(model, key, prompt):
        if model == "model-limited":
            raise providers.RateLimit("daily")
        return "five years"

    return secret, partial(providers.answer, config_file=config, state_file=tmp_path / "state.json",
                           adapters={"fake": adapter}, sleep=lambda seconds: None)


@pytest.mark.parametrize("record_text", [False, True])
def test_ask_end_to_end_with_fake_provider(record_text, study_vectors, tmp_path, fake_provider_answer, capsys):
    secret, answer = fake_provider_answer
    question = sample_questions("docling", DOCS[0])[0][1]
    result = ask_pdf(pdf_path(DOCS[0]), question, from_extraction=EXTRACTED / "docling" / f"{DOCS[0]}.json",
                     cache_root=tmp_path / "cache", embed=Counting(study_vectors), answer=answer, record_text=record_text)
    assert result["answer"] == "five years"
    assert result["provider"] == {"entry": "second", "provider": "fake", "model": "model-ok"}
    assert result["sources"] and all(source["pages"] for source in result["sources"])
    record_text_seen = result["run_record"].read_text(encoding="utf-8")
    record = json.loads(record_text_seen)
    assert record["run_id"].startswith("A-LOCAL-") and record["stack"]["agent_mode"] == "ask"
    assert record["stack"]["answer_provider"] == result["provider"]
    assert record["stack"]["chunks_read"] == result["sources"]
    assert {stage["stage"] for stage in record["costs"]["stages"]} >= {"scan_check", "load_index", "parse", "chunk",
                                                                      "embed", "retrieve", "answer"}
    stored = json.dumps(record, ensure_ascii=False)
    assert (json.dumps(question, ensure_ascii=False)[1:-1] in stored) == record_text
    assert ("five years" in stored) == record_text
    assert (record["stack"]["question"].get("text") == question) == record_text
    assert record["stack"]["question"]["characters"] == len(question)
    captured = capsys.readouterr()
    assert all(secret not in text for text in [record_text_seen, json.dumps(result, default=str), captured.out, captured.err])


def test_real_embedding_matches_study_vectors(study_vectors):
    """The agent's own bge-m3 (laptop CPU) against the study's cached vectors (Kaggle GPU) for one document."""
    chunks = load_chunks(CHUNKS / "docling" / SETTING / f"{DOCS[0]}.json")
    questions = sample_questions("docling", DOCS[0])
    texts = [chunk["index_text"] for chunk in chunks] + [question for qid, question in questions]
    agent = index.embed(texts)
    study = np.stack([study_vectors[text_key(text)] for text in texts])
    cosine = (agent * study).sum(axis=1)
    print(f"\nminimum cosine agent vs study over {len(texts)} texts: {cosine.min():.7f}; "
          f"max abs difference {np.abs(agent - study).max():.2e}")
    assert cosine.min() >= 0.9999
    document_text = json.loads((EXTRACTED / "docling" / f"{DOCS[0]}.json").read_text(encoding="utf-8"))["text"]
    for position, (qid, question) in enumerate(questions):
        mine = index.retrieve(question, agent[len(chunks) + position], chunks, agent[:len(chunks)], document_text, 1250)
        theirs = index.retrieve(question, study[len(chunks) + position], chunks, study[:len(chunks)], document_text, 1250)
        assert mine == theirs
