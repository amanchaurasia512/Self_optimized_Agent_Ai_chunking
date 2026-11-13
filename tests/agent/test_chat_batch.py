"""Agent chat and batch modes and the baseline helpers (spec/agent_v1.md, Chat and batch modes; Baseline before the
app), on tuning documents only. Fake embeddings and fake answers: no model and no API call. The index cache and run
records live in pytest's temporary folder."""
import json
from functools import partial

import pandas as pd
import pytest

import src.agent.batch as batch_module
from scripts.aq_run import contained, token_f1
from src.agent import baseline
from src.agent.ask import ask_pdf, chat
from src.agent.batch import run_batch
from src.common.paths import PROJECT_ROOT
from src.common.pdf_catalog import PDF_MANIFEST
from src.common.split import SPLIT_FILE, tuning_ids

DOCS = ["cuad_cooltechnologies_inc_10_25_2017_ex_10_71_strategic_alliance_agreement",
        "cuad_bizzingoinc_20120322_8_k_ex_10_17_7504499_ex_10_17_endorsement_agreement"]
QUESTIONS = ["What is the term of the agreement?", "Who are the parties?", "Can the agreement be assigned?"]


def pdf_path(doc_id):
    assert doc_id in tuning_ids(), f"{doc_id} is not a tuning document"
    return str(PROJECT_ROOT / pd.read_csv(PDF_MANIFEST).set_index("doc_id").loc[doc_id, "file"])


def fake_answer(question, context):
    return {"answer": f"{len(context)} characters", "entry": "fake-a" if "term" in question else "fake-b",
            "provider": "fake", "model": "fake-model"}


def stage_names(record_path):
    return [stage["stage"] for stage in json.loads(record_path.read_text(encoding="utf-8"))["costs"]["stages"]]


def test_chat_opens_once_and_answers_like_ask(tmp_path, fake_embedding):
    results = list(chat(pdf_path(DOCS[0]), iter([*QUESTIONS[:2], "", QUESTIONS[2]]), fast=True,
                        cache_root=tmp_path / "cache", embed=fake_embedding, answer=fake_answer))
    opened, answers = results[0], results[1:]
    assert opened["opened"] and not opened["cache_hit"] and opened["parser"] == "pdfplumber"
    assert len(answers) == 2  # stops at the empty line
    first, second = (stage_names(result["run_record"]) for result in answers)
    assert first[:3] == ["load_embedder", "scan_check", "load_index"] and first[-2:] == ["retrieve", "answer"]
    assert second == ["retrieve", "answer"]  # the index and bge-m3 are not opened again
    for question, result in zip(QUESTIONS, answers):
        single = ask_pdf(pdf_path(DOCS[0]), question, fast=True, cache_root=tmp_path / "cache", embed=fake_embedding,
                         answer=fake_answer)
        assert single["cache_hit"] and {key: single[key] for key in ("answer", "context", "sources", "tokens_read")} == \
            {key: result[key] for key in ("answer", "context", "sources", "tokens_read")}
        assert json.loads(result["run_record"].read_text(encoding="utf-8"))["stack"]["agent_mode"] == "chat"


@pytest.fixture
def questions_csv(tmp_path):
    rows = [{"pdf": pdf_path(doc_id), "question": question, "gold": "characters", "question_id": f"q{number}"}
            for number, (doc_id, question) in enumerate([(DOCS[0], QUESTIONS[0]), (DOCS[1], QUESTIONS[1]),
                                                         (DOCS[0], QUESTIONS[2])], start=1)]
    path = tmp_path / "questions.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_batch_builds_every_index_first_then_answers(questions_csv, tmp_path, fake_embedding):
    waits, moments = [], iter(range(0, 1000, 1))
    table, record_path = run_batch(questions_csv, tmp_path / "answers.csv", fast=True, cache_root=tmp_path / "cache",
                                   embed=fake_embedding, answer=fake_answer, sleep=waits.append,
                                   clock=lambda: float(next(moments)), interval=4.0)
    written = pd.read_csv(tmp_path / "answers.csv", dtype={"question_id": str})
    assert list(written["question_id"]) == ["q1", "q2", "q3"] and len(table) == 3
    assert {"answer", "provider_entry", "model", "index_seconds", "retrieve_seconds", "pace_seconds", "answer_seconds",
            "f1", "contained"} <= set(written.columns)
    assert list(written["f1"]) == [round(token_f1(answer, "characters"), 4) for answer in written["answer"]]
    assert list(written["contained"]) == [contained(answer, "characters") for answer in written["answer"]]
    assert waits == [3.0, 3.0]  # the first call does not wait; later ones fill the 4 s interval
    record = json.loads(record_path.read_text(encoding="utf-8"))
    stages = record["costs"]["stages"]
    assert stages[0]["stage"] == "load_embedder" and sum(stage["stage"] == "load_embedder" for stage in stages) == 1
    last_index_step = max(position for position, stage in enumerate(stages) if "document" in stage)
    first_question_step = min(position for position, stage in enumerate(stages) if "question" in stage)
    assert last_index_step < first_question_step
    assert {stage["document"] for stage in stages if "document" in stage} == {1, 2}
    assert record["stack"]["answers_by_entry"] == {"fake-a": 1, "fake-b": 2}
    assert record["stack"]["answered"] == record["stack"]["questions"] == 3
    assert "What is the term" not in json.dumps(record)  # question text stays in the local CSV


def test_batch_refuses_documents_that_are_not_tuning(questions_csv, tmp_path, fake_embedding, monkeypatch):
    split = pd.read_csv(SPLIT_FILE)
    split.loc[split["doc_id"] == DOCS[1], "split"] = "held_out"  # pretend: the file itself stays a tuning PDF
    pretend = tmp_path / "split.csv"
    split.to_csv(pretend, index=False)
    monkeypatch.setattr(batch_module, "SPLIT_FILE", pretend)
    calls = []
    with pytest.raises(ValueError, match=DOCS[1]):
        run_batch(questions_csv, tmp_path / "answers.csv", fast=True, cache_root=tmp_path / "cache",
                  embed=lambda texts: calls.append(texts), answer=fake_answer)
    assert not calls and not (tmp_path / "cache").exists() and not (tmp_path / "answers.csv").exists()


def test_baseline_draws_60_tuning_questions_with_seed_42():
    first, second = baseline.draw_questions(), baseline.draw_questions()
    assert first.equals(second) and len(first) == 60 and first["question_id"].is_unique
    assert set(first["doc_id"]) <= tuning_ids() and baseline.check_split(first) == 60
    with pytest.raises(SystemExit, match="not tuning"):
        baseline.check_split(pd.DataFrame({"doc_id": ["no_such_document"]}))


def test_baseline_timing_groups_steps_by_document_and_question():
    step = lambda name, seconds, **tags: {"stage": name, "wall_seconds": seconds, **tags}
    stages = [step("load_embedder", 6.0), step("scan_check", 1.0, document=1), step("parse", 2.0, document=1),
              step("scan_check", 1.0, document=2), step("load_index", 0.5, document=2),
              *[step(name, seconds, question=number) for number in (1, 2)
                for name, seconds in (("retrieve", 0.2 * number), ("pace", 0.0), ("answer", 1.0 * number))]]
    report = baseline.timing(stages)
    assert report["load_embedder_seconds"] == 6.0
    assert report["index_per_document"]["total"] == {"n": 2, "median": 2.25, "p95": 2.925, "max": 3.0}
    assert report["index_per_document"]["parse"]["n"] == 1
    assert report["per_question"]["answer"]["max"] == 2.0 and report["per_question"]["retrieve_and_answer"]["n"] == 2
