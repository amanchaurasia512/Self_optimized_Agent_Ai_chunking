"""Unseen scanned test helpers (spec/agent_v1.md): the study's MP-DocVQA documents are excluded, and the summary
divides step time by pages per document. No network, no PDFs read."""
import pandas as pd

from scripts.rq5_scanned_select import PICKS_FILE
from src.agent import unseen_scanned
from src.common.split import SPLIT_FILE


def test_study_documents_are_excluded():
    excluded = unseen_scanned.study_documents()
    assert set(pd.read_csv(PICKS_FILE)["doc_id"]) <= excluded
    split_ids = pd.read_csv(SPLIT_FILE)["doc_id"]
    assert {doc.removeprefix("mpdocvqa_") for doc in split_ids if doc.startswith("mpdocvqa_")} <= excluded
    if unseen_scanned.TEST_PICKS.exists():
        assert not set(pd.read_csv(unseen_scanned.TEST_PICKS)["doc_id"]) & excluded


def test_summary_per_page_and_quality():
    document = lambda pages, empty: {"pages": pages, "pages_without_text": empty, "parser": {"name": "docling"}}
    step = lambda name, seconds, number: {"stage": name, "wall_seconds": seconds, "document": number}
    record = {"run_id": "A-LOCAL-test", "stack": {"documents": [document(10, 10), document(20, 20)]},
              "costs": {"totals": {"peak_ram_mb": 5000.0, "wall_seconds": 400.0},
                        "stages": [step("scan_check", 1.0, 1), step("parse", 100.0, 1), step("chunk", 1.0, 1),
                                   step("embed", 10.0, 1), step("parse", 300.0, 2), step("embed", 20.0, 2),
                                   step("scan_check", 2.0, 2), step("chunk", 2.0, 2)]}}
    answers = pd.DataFrame({"doc_id": ["a", "a", "b"], "answer": ["Not found.", "x", "y"], "answer_seconds": [1.0, 2.0, 3.0],
                            "f1": [0.0, 1.0, 0.5], "contained": [False, True, True], "provider_entry": ["g", "g", "h"]})
    summary = unseen_scanned.summarise(answers, record)
    assert [row["doc_id"] for row in summary["documents"]] == ["a", "b"]
    assert summary["documents"][0]["parse_seconds_per_page"] == 10.0 and summary["documents"][1]["parse_seconds_per_page"] == 15.0
    assert summary["seconds_per_page"]["parse"] == {"median": 12.5, "max": 15.0}
    assert (summary["f1"], summary["contained"], summary["not_found"]) == (0.5, 0.667, 1)
    assert summary["answers_by_entry"] == {"g": 2, "h": 1}
