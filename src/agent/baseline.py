"""Baseline before the app (spec/agent_v1.md): 60 tuning questions from the AQ sample, batch mode in fast mode at
budget 1,250, a fresh index cache; time per step (median, 95th percentile, max), token F1 and contained, and the
nearest AQ setup on the same questions. Run from the repo root in the Docling environment:
    .venv-docling/bin/python -m src.agent.baseline"""
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.aq_run import F1_FILE, SAMPLE_FILE
from src.agent.batch import run_batch
from src.agent.pipeline import agent_run_id
from src.common.paths import AGENT_CACHE, PROJECT_ROOT, RESULTS
from src.common.pdf_catalog import PDF_MANIFEST
from src.common.split import SPLIT_FILE, tuning_ids

SAMPLE_SIZE, SEED, BUDGET = 60, 42, 1250
AQ_SETUP, AQ_MODEL = ("docling", "method1_tree_T384_noprefix"), "gemini-3.5-flash-lite"  # AQ answer model
OUTPUT = RESULTS / "agent"
QUESTIONS_FILE, ANSWERS_FILE, SUMMARY_FILE = (OUTPUT / name for name in
                                               ("baseline_questions.csv", "baseline_answers.csv", "baseline_summary.json"))
INDEX_STEPS = ("scan_check", "load_index", "parse", "chunk", "embed", "load_vectors")
QUESTION_STEPS = ("retrieve", "pace", "answer")


def draw_questions():
    """The 60 questions: tuning documents only, seed 42; columns pdf, question, gold plus their ids."""
    sample = pd.read_csv(SAMPLE_FILE, dtype=str)
    drawn = sample[sample["doc_id"].isin(tuning_ids())].sample(SAMPLE_SIZE, random_state=SEED)
    files = pd.read_csv(PDF_MANIFEST).set_index("doc_id")["file"]
    return pd.DataFrame({"pdf": drawn["doc_id"].map(files), "question": drawn["question"], "gold": drawn["reference"],
                         "doc_id": drawn["doc_id"], "question_id": drawn["question_id"], "source": drawn["source"]})


def check_split(questions):
    """Every question's document must be tuning in pdfs/split.csv; stops before anything runs otherwise."""
    split = pd.read_csv(SPLIT_FILE).set_index("doc_id")["split"]
    sealed = sorted(set(questions.loc[questions["doc_id"].map(split) != "tuning", "doc_id"]))
    if sealed:
        raise SystemExit(f"refused: {len(sealed)} document(s) are not tuning in pdfs/split.csv")
    return len(questions)


def spread(values):
    values = np.asarray(list(values), dtype=float)
    return {"n": len(values), "median": round(float(np.median(values)), 3),
            "p95": round(float(np.percentile(values, 95)), 3), "max": round(float(values.max()), 3)}


def steps_by(stages, key, names):
    """{document or question number: {step: seconds}} from the batch run record's tagged steps."""
    totals = defaultdict(Counter)
    for stage in stages:
        if key in stage and stage["stage"] in names:
            totals[stage[key]][stage["stage"]] += stage["wall_seconds"]
    return totals


def timing(stages):
    """Medians, 95th percentiles and maxima: per document for index building, per question for answering."""
    documents, questions = steps_by(stages, "document", INDEX_STEPS), steps_by(stages, "question", QUESTION_STEPS)
    report = {"load_embedder_seconds": sum(stage["wall_seconds"] for stage in stages if stage["stage"] == "load_embedder"),
              "index_per_document": {"total": spread(sum(steps.values()) for steps in documents.values())},
              "per_question": {}}
    for name in INDEX_STEPS:
        found = [steps[name] for steps in documents.values() if name in steps]
        if found:
            report["index_per_document"][name] = spread(found)
    for name in QUESTION_STEPS:
        report["per_question"][name] = spread(steps.get(name, 0.0) for steps in questions.values())
    report["per_question"]["retrieve_and_answer"] = spread(steps["retrieve"] + steps["answer"] for steps in questions.values())
    return report


def quality(answers):
    """Mean token F1 and contained; the nearest AQ setup on the same questions; the Docling-fallback questions
    (exact setup match) on their own."""
    aq = pd.read_csv(F1_FILE, dtype={"question_id": str})
    aq = aq[(aq["parser"] == AQ_SETUP[0]) & (aq["setting"] == AQ_SETUP[1])][["question_id", "f1", "contained"]]
    paired = answers.merge(aq, on="question_id", suffixes=("", "_aq"))
    means = lambda frame, suffix="": {"f1": round(frame[f"f1{suffix}"].mean(), 3),
                                      "contained": round(frame[f"contained{suffix}"].astype(float).mean(), 3)}
    exact = paired[paired["parser"] == AQ_SETUP[0]]
    return {"agent": {"questions": len(answers), **means(answers)},
            "aq_nearest": {"setup": "/".join(AQ_SETUP), "note": "parser differs (docling vs pdfplumber); same chunker, "
                           "budget, prompt and answer model", "questions": len(paired),
                           "agent": means(paired), "aq": means(paired, "_aq")},
            "aq_exact_docling_fallback": {"questions": len(exact), "agent": means(exact), "aq": means(exact, "_aq")},
            "by_source": {source: means(group) for source, group in answers.groupby("source")},
            "answers_by_entry": answers["provider_entry"].value_counts().to_dict(),
            "answers_by_other_model": int((answers["model"] != AQ_MODEL).sum())}


def main():
    questions = draw_questions()
    checked = check_split(questions)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    questions.to_csv(QUESTIONS_FILE, index=False)
    cache_root = AGENT_CACHE / "baseline" / agent_run_id()
    print(f"{checked} questions, all tuning, from {questions['doc_id'].nunique()} documents -> {QUESTIONS_FILE}\n"
          f"fresh index cache: {cache_root}")
    answers, record_path = run_batch(QUESTIONS_FILE, ANSWERS_FILE, BUDGET, fast=True, cache_root=cache_root)
    stages = json.loads(Path(record_path).read_text(encoding="utf-8"))["costs"]["stages"]
    summary = {"run_record": str(Path(record_path).relative_to(PROJECT_ROOT)), "timing_seconds": timing(stages),
               **quality(answers)}
    SUMMARY_FILE.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"answers -> {ANSWERS_FILE}\nsummary -> {SUMMARY_FILE}\nrun record: {record_path}")


if __name__ == "__main__":
    main()
