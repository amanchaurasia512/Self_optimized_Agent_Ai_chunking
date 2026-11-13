"""Shared for the agent tests: every run record goes to pytest's temporary folder, never to runs/.
Real `python -m src.agent` runs are not affected and still write to runs/."""
import pytest

from src.common import manifest


@pytest.fixture(autouse=True)
def test_runs_dir(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(manifest, "RUNS_DIR", runs)
    return runs
