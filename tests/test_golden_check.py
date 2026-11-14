"""GOLDEN_200 validity check (spec v1.2, 2026-11-14) on fake data: Wilson intervals, the tuning-only guard, labelling
that saves after every answer, stops after a batch of 20 and resumes, the expansion rule, and the report. The fake
documents, extraction and gold live in pytest's temporary folder; no real label is written."""
import json

import pandas as pd
import pytest

from scripts import golden_check

DOCS = {"fake_a": "A", "fake_b": "B"}


@pytest.fixture
def fake(tmp_path, monkeypatch):
    source, extracted, gold, output = (tmp_path / name for name in ("source", "extracted", "gold", "output"))
    for folder in (source, extracted / "docling", gold):
        folder.mkdir(parents=True)
    spans = []
    for doc, stem in DOCS.items():
        text = "".join(f"Rule {index}: the answer to item {index} is {index * 7}. " for index in range(60))
        items = [{"id": f"{stem}-Q{index:03d}", "question": f"What is item {index}?", "answer": str(index * 7),
                  "source_location": ["Page 1"], "required_evidence": [f"the answer to item {index} is {index * 7}"]}
                 for index in range(60)]
        (source / f"{stem}_GOLDEN_200.json").write_text(json.dumps(items), encoding="utf-8")
        (extracted / "docling" / f"{doc}.json").write_text(json.dumps(
            {"text": text, "pages": [{"page": 1, "start_char": 0, "end_char": len(text)}]}), encoding="utf-8")
        for index, item in enumerate(items):
            start = text.find(item["required_evidence"][0])
            placed = index % 10 != 0  # every tenth question is not placed, to show the page fallback
            spans.append({"doc_id": doc, "question_id": item["id"], "certain": placed,
                          "start": start if placed else None, "end": start + len(item["required_evidence"][0]) if placed else None})
    (gold / "spans_docling.jsonl").write_text("\n".join(json.dumps(span) for span in spans), encoding="utf-8")
    monkeypatch.setattr(golden_check, "DOCS", DOCS)
    monkeypatch.setattr(golden_check, "tuning_ids", lambda: set(DOCS))
    for name, value in {"SOURCE": source, "EXTRACTED": extracted, "GOLD": gold, "OUTPUT": output,
                        "SAMPLE_FILE": output / "sample.csv", "LABELS_FILE": output / "labels.csv"}.items():
        monkeypatch.setattr(golden_check, name, value)
    return output


def answers(*keys):
    """A fake input(): each y / n / s key is followed by its note ('n' gets one, the others none); other keys stand alone."""
    script = iter([part for key in keys for part in ([key, "fake note" if key == "n" else ""] if key in "yns" else [key])])
    return lambda prompt: next(script)


def test_wilson_matches_known_values():
    assert golden_check.wilson(0, 20)[1] == pytest.approx(0.1611, abs=1e-4)
    assert golden_check.wilson(3, 20) == pytest.approx((0.0524, 0.3604), abs=1e-4)
    assert golden_check.wilson(10, 20) == pytest.approx((0.2993, 0.7007), abs=1e-4)


def test_refuses_documents_that_are_not_tuning(fake, monkeypatch):
    monkeypatch.setattr(golden_check, "tuning_ids", lambda: {"fake_a"})
    with pytest.raises(ValueError, match="fake_b"):
        golden_check.draw_sample()


def test_real_documents_are_tuning_and_d2_is_not_listed():
    assert set(golden_check.checked_docs()) == {"indian_d1", "indian_d3_fundamental_rules", "indian_d4_rti_act"}
    assert "indian_d2_ccs_conduct_rules" not in golden_check.DOCS


def test_sample_is_seeded_and_drawn_once(fake):
    golden_check.draw_sample()
    sample = pd.read_csv(fake / "sample.csv")
    assert sample.groupby("doc_id").size().to_dict() == {"fake_a": 20, "fake_b": 20} and set(sample["batch"]) == {1}
    assert sample["question_id"].is_unique
    first = sample["question_id"].tolist()
    assert [row["question_id"] for doc in DOCS for row in golden_check.batch_rows(doc, 1)] == first  # same seed, same draw
    with pytest.raises(FileExistsError):
        golden_check.draw_sample()


def test_label_saves_each_answer_stops_after_a_batch_and_resumes(fake, capsys):
    golden_check.draw_sample()
    golden_check.label(answers("y", "n", "q"))
    labels = pd.read_csv(fake / "labels.csv", keep_default_na=False)
    assert labels["label"].tolist() == ["valid", "invalid"] and labels["note"].tolist() == ["", "fake note"]
    golden_check.label(answers(*["y"] * 25))  # one session labels at most 20
    assert len(pd.read_csv(fake / "labels.csv")) == 22
    shown = capsys.readouterr().out
    assert ">>>the answer to item" in shown and "NOT placed by the study; start of cited page 1" in shown
    first = shown.split("\n---- ")[1].splitlines()  # the first question screen of the session
    stars, equals = "*" * 80, "=" * 80
    assert first[0].startswith("1 / 20 · A · A-Q") and len("---- " + first[0]) == 80 and first[0].endswith("-")
    assert first[1].startswith("Q: What is item") and first[2] == stars and first[3].startswith("ANSWER:")
    assert first[4] == "EVIDENCE:" and first.index(stars, 3) + 1 == first.index(equals)
    assert first[first.index(equals) + 1].startswith("CONTEXT") and first.count(equals) == 2
    golden_check.label(answers("x", "maybe", "s", "q"))  # unknown keys are asked again
    assert pd.read_csv(fake / "labels.csv")["label"].iloc[-1] == "unsure"


def test_expansion_only_when_the_rule_triggers(fake):
    golden_check.draw_sample()
    with pytest.raises(ValueError, match="not due"):
        golden_check.expand("fake_a")
    golden_check.label(answers(*(["n"] * 3 + ["y"] * 17)))  # fake_a batch 1: 3 of 20 invalid
    golden_check.label(answers(*(["s"] * 3 + ["y"] * 17)))  # fake_b: unsure does not count
    with pytest.raises(ValueError):
        golden_check.expand("fake_b")
    golden_check.expand("fake_a")
    sample = pd.read_csv(fake / "sample.csv")
    assert (sample["doc_id"].eq("fake_a") & sample["batch"].eq(2)).sum() == 20 and sample["question_id"].is_unique
    with pytest.raises(ValueError):
        golden_check.expand("fake_a")  # once only


def test_report_rates_and_intervals(fake, capsys):
    golden_check.draw_sample()
    golden_check.label(answers(*(["n"] * 3 + ["y"] * 17)))
    golden_check.label(answers(*(["n"] + ["s"] * 2 + ["y"] * 17)))
    labels = pd.read_csv(fake / "labels.csv", dtype=str, keep_default_na=False).merge(
        pd.read_csv(fake / "sample.csv", dtype={"question_id": str}), on=["doc_id", "question_id"])
    table = golden_check.rates(labels)
    assert table.loc["fake_a", "invalid_rate"] == 0.15 and table.loc["fake_a", ["low", "high"]].tolist() == pytest.approx([0.0524, 0.3604], abs=1e-4)
    assert table.loc["overall", ["labelled", "invalid", "unsure"]].tolist() == [40, 4, 2]
    assert table.loc["fake_b", "invalid_or_unsure_rate"] == 0.15
    golden_check.report()
    shown = capsys.readouterr().out
    assert "expansion due" in shown and "['fake_a']" in shown and "fake note" in shown
