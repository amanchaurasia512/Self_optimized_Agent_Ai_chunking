"""The command line's timing line (spec/agent_v1.md): every number comes from the run record's stage timings. Tuning
documents only, from their existing extractions; fake embeddings and a fake answer, so no model and no API call."""
import json
import re
import sys
from functools import partial
from pathlib import Path

import pandas as pd
import pytest

import src.agent.ask as ask_module
from src.agent.__main__ import INDEX_STAGES, main
from src.common.paths import EXTRACTED, PROJECT_ROOT
from src.common.pdf_catalog import PDF_MANIFEST
from src.common.split import tuning_ids

DOC = "cuad_cooltechnologies_inc_10_25_2017_ex_10_71_strategic_alliance_agreement"
EXTRACTION = EXTRACTED / "docling" / f"{DOC}.json"
TIME_LINE = re.compile(r"^time: total \d+\.\d s(?: \| [a-z ()]+ \d+\.\d s)+$", re.MULTILINE)


def pdf_path():
    assert DOC in tuning_ids(), f"{DOC} is not a tuning document"
    return PROJECT_ROOT / pd.read_csv(PDF_MANIFEST).set_index("doc_id").loc[DOC, "file"]


def run_cli(arguments, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["python -m src.agent", *arguments])
    main()
    return capsys.readouterr().out


def stage_seconds(output):
    """(run record costs, {label: seconds} printed on the time line)."""
    record_path = re.search(r"^run record: (.+)$", output, re.MULTILINE).group(1)
    costs = json.loads(Path(record_path).read_text(encoding="utf-8"))["costs"]
    line = TIME_LINE.search(output).group(0)
    parts = [part.strip().removesuffix(" s").rpartition(" ") for part in line.removeprefix("time: ").split("|")]
    printed = {label: float(value) for label, space, value in parts}
    return costs, printed


def summed(costs, names):
    return round(sum(stage["wall_seconds"] for stage in costs["stages"] if stage["stage"] in names), 1)


def test_chunk_output_has_total_parse_and_chunk_time(tmp_path, monkeypatch, capsys):
    output = run_cli(["chunk", str(pdf_path()), "-o", str(tmp_path / "chunk.json"), "--from-extraction", str(EXTRACTION)],
                     monkeypatch, capsys)
    costs, printed = stage_seconds(output)
    assert list(printed) == ["total", "parse", "chunk"]
    assert printed == {"total": round(costs["totals"]["wall_seconds"], 1), "parse": summed(costs, ("parse",)),
                       "chunk": summed(costs, ("chunk",))}


@pytest.mark.parametrize("context_only", [False, True])
def test_ask_output_has_index_retrieve_and_answer_time(context_only, tmp_path, monkeypatch, capsys, fake_embedding):
    fake_answer = lambda question, context: {"answer": "five years", "entry": "fake", "provider": "fake", "model": "m"}
    monkeypatch.setattr(ask_module, "ask_pdf", partial(ask_module.ask_pdf, cache_root=tmp_path / "cache", embed=fake_embedding,
                                                       answer=fake_answer))
    arguments = ["ask", str(pdf_path()), "What is the term?", "--from-extraction", str(EXTRACTION)]
    arguments += ["--context-only"] if context_only else []
    for index_state in ("built", "cached"):
        output = run_cli(arguments, monkeypatch, capsys)
        costs, printed = stage_seconds(output)
        expected = {"total": round(costs["totals"]["wall_seconds"], 1), f"index ({index_state})": summed(costs, INDEX_STAGES),
                    "retrieve": summed(costs, ("retrieve",))}
        expected |= {} if context_only else {"answer": summed(costs, ("answer",))}
        assert printed == expected
        if not context_only:
            lines = output.splitlines()
            assert lines[lines.index(next(line for line in lines if line.startswith("answered by:"))) + 1].startswith("time:")
