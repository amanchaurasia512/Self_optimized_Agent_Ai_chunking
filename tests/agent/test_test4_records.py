"""Agent test 4 run records: both write paths (runs/ and a test records dir) of test4.write_record and
test4_llm.write_session, so a missing import in either branch fails here. Records go to pytest's tmp_path only."""
import json

import pytest

from src.agent import test4, test4_llm


@pytest.fixture
def runs(test_runs_dir, monkeypatch):
    """runs/ points at the conftest temporary runs folder in both modules."""
    monkeypatch.setattr(test4, "RUNS_DIR", test_runs_dir)
    monkeypatch.setattr(test4_llm, "RUNS_DIR", test_runs_dir)
    return test_runs_dir


def test_write_record_runs_dir(runs):
    path = test4.write_record({"run_id": "A-LOCAL-20261127-1"}, runs)
    assert path == runs / "A-LOCAL-20261127-1.json"
    assert json.loads(path.read_text(encoding="utf-8"))["run_id"] == "A-LOCAL-20261127-1"


def test_write_record_tests_dir(runs, tmp_path):
    records = tmp_path / "runs_tests"
    path = test4.write_record({"run_id": "A-LOCAL-20261127-1"}, records)
    assert path == records / "test_at4_index_A-LOCAL-20261127-1.json"
    assert not list(runs.iterdir())
    with pytest.raises(FileExistsError):
        test4.write_record({"run_id": "A-LOCAL-20261127-1"}, records)


@pytest.mark.parametrize("use_runs", [True, False])
def test_write_session_both_dirs(runs, tmp_path, use_runs):
    records = runs if use_runs else tmp_path / "runs_tests"
    source = tmp_path / "questions.csv"
    source.write_text("pdf,question,gold\n", encoding="utf-8")
    path = test4_llm.write_session(records, "A-TEST-20261127-1", {"agent_mode": "test4_contexts"}, [source],
                                   tmp_path / "out.csv", {}, "laptop")
    expected = "A-TEST-20261127-1.json" if use_runs else "test_at4llm_A-TEST-20261127-1.json"
    assert path == records / expected
    assert json.loads(path.read_text(encoding="utf-8"))["run_id"] == "A-TEST-20261127-1"
