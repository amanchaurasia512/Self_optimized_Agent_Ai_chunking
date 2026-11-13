"""Shared for the agent tests: every run record goes to pytest's temporary folder, never to runs/.
Real `python -m src.agent` runs are not affected and still write to runs/."""
import hashlib

import numpy as np
import pytest

from src.common import manifest


@pytest.fixture(autouse=True)
def test_runs_dir(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(manifest, "RUNS_DIR", runs)
    return runs


def fake_embed(texts):
    """A fixed unit vector per text (from its hash): enough to rank, no model."""
    seeds = [int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16) for text in texts]
    vectors = np.stack([np.random.default_rng(seed).standard_normal(64) for seed in seeds]).astype(np.float32)
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


@pytest.fixture
def fake_embedding():
    return fake_embed
