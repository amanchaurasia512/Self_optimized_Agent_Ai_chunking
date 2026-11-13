"""Unseen scanned test (spec/agent_v1.md): 5 MP-DocVQA val documents the study never used, 3 questions each, through
batch mode in thorough mode. Reuses the RQ5(a) selection and PDF-building functions; writes only to the agent test
set (pdfs/agent_test_picks.csv, data/agent_test/mpdocvqa/), never to pdfs/split.csv, catalog.csv or the study's
picks. Run from the repo root: select, download and build in the study environment (img2pdf), run in the Docling one:
    .venv/bin/python -m src.agent.unseen_scanned select   (then download, build)
    .venv-docling/bin/python -m src.agent.unseen_scanned run
Prints ids and counts only."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.rq5_scanned_select import MAX_PAGES, MIN_PAGES, PICKS_FILE, REPO, doc_names, page_list
from src.agent.batch import run_batch
from src.agent.pipeline import agent_run_id
from src.common.manifest import PROJECT_ROOT, file_sha256, project_path
from src.common.paths import AGENT_CACHE, DATA
from src.common.split import SPLIT_FILE

DOCUMENTS, QUESTIONS_PER_DOC, MIN_QUESTIONS, SEED = 5, 3, 3, 42
TEST_PICKS = PROJECT_ROOT / "pdfs" / "agent_test_picks.csv"
OUTPUT = DATA / "agent_test" / "mpdocvqa"
QUESTIONS_JSON, BATCH_CSV, ANSWERS_CSV, SUMMARY = (OUTPUT / name for name in
                                                   ("questions.json", "batch_questions.csv", "answers.csv", "summary.json"))
INDEX_STEPS = ("scan_check", "parse", "chunk", "embed")
SEPARATOR = " | "  # answer alternatives, as scripts/aq_run.token_f1 and contained take them


def study_documents():
    """MP-DocVQA ids the study uses (its picks and every split entry), which the agent test must not take."""
    split_ids = {doc_id.removeprefix("mpdocvqa_") for doc_id in pd.read_csv(SPLIT_FILE)["doc_id"]}
    return set(pd.read_csv(PICKS_FILE)["doc_id"]) | split_ids


def select():
    """As scripts/rq5_scanned_select.py reads val (ids and page lists only), then the agent-test draw (seed 42)."""
    from huggingface_hub import HfApi, HfFileSystem
    system = HfFileSystem()
    revision = HfApi().dataset_info(REPO.removeprefix("datasets/")).sha
    files = sorted(system.glob(f"{REPO}@{revision}/data/val-*.parquet"))
    names = doc_names(system, files[0])
    questions = pd.concat([pd.read_parquet(f"hf://{path}", columns=["questionId", "doc_id", "page_ids"], filesystem=system)
                           .assign(file=path.rsplit("/", 1)[1]) for path in files], ignore_index=True)
    if names:
        questions["doc_id"] = questions["doc_id"].map(lambda index: names[index])
    questions["pages"] = questions["page_ids"].map(page_list)
    documents = questions.groupby("doc_id").agg(page_lists=("pages", "nunique"), pages=("pages", lambda pages: len(pages.iloc[0])),
                                                 questions=("questionId", "nunique"),
                                                 files=("file", lambda files: " ".join(sorted(set(files))))).reset_index()
    excluded = study_documents()
    eligible = documents[(documents["page_lists"] == 1) & documents["pages"].between(MIN_PAGES, MAX_PAGES)
                         & (documents["questions"] >= MIN_QUESTIONS) & ~documents["doc_id"].isin(excluded)]
    picks = eligible.sort_values("doc_id").sample(DOCUMENTS, random_state=SEED).assign(revision=revision)
    TEST_PICKS.parent.mkdir(parents=True, exist_ok=True)
    picks.to_csv(TEST_PICKS, index=False)
    print(f"val documents {len(documents):,} | eligible {len(eligible)} (study documents excluded: "
          f"{len(excluded & set(documents['doc_id']))}) | dataset revision {revision[:12]}")
    print(picks[["doc_id", "pages", "questions", "files"]].to_string(index=False), f"\nsaved {TEST_PICKS}")


def download():
    """The val parquet files holding the picks, into the study's MP-DocVQA source folder when missing."""
    from huggingface_hub import hf_hub_download
    from scripts.rq5_scanned_build import SOURCE
    picks = pd.read_csv(TEST_PICKS)
    needed = sorted({name for names in picks["files"] for name in names.split()})
    for name in needed:
        if not (SOURCE / name).exists():
            hf_hub_download(REPO.removeprefix("datasets/"), f"data/{name}", repo_type="dataset",
                            revision=picks["revision"].iloc[0], local_dir=SOURCE.parent)
        print(f"{name}: {(SOURCE / name).stat().st_size / 1e6:.0f} MB")


def build():
    """One PDF per pick (page images in page-list order, lossless), and 3 questions each with their answer lists."""
    import img2pdf  # the study environment (the build script imports it too); the Docling environment only runs the batch
    from scripts.rq5_scanned_build import IMAGES, answer_list, picked_questions
    picks = pd.read_csv(TEST_PICKS)
    assert not set(picks["doc_id"]) & study_documents(), "an agent-test pick is a study document"
    questions = picked_questions(picks)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    saved = []
    for doc in sorted(picks["doc_id"]):
        doc_questions = questions[questions["doc_id"] == doc].sort_values("questionId")
        pages = page_list(doc_questions["page_ids"].iloc[0])
        first = doc_questions.iloc[0]
        images = [first[column]["bytes"] if first[column] is not None else None for column in IMAGES[:len(pages)]]
        assert all(images), f"{doc}: page images missing"
        target = OUTPUT / f"mpdocvqa_{doc}.pdf"
        target.write_bytes(img2pdf.convert(images))
        drawn = doc_questions.sample(QUESTIONS_PER_DOC, random_state=SEED)
        for row in drawn.itertuples(index=False):
            answers = answer_list(row.answers)
            assert not any(SEPARATOR in answer for answer in answers), f"{doc}: an answer holds '{SEPARATOR}'"
            saved.append({"question_id": f"mpdocvqa::{row.questionId}", "doc_id": f"mpdocvqa_{doc}", "question": row.question,
                          "answers": answers, "answer_page": int(row.answer_page_idx) + 1, "pages": len(pages),
                          "pdf": project_path(target), "pdf_sha256": file_sha256(target)})
        print(f"{doc}: {len(pages)} pages | {len(doc_questions)} questions, {QUESTIONS_PER_DOC} drawn | "
              f"{target.stat().st_size / 1e6:.1f} MB")
    QUESTIONS_JSON.write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
    pd.DataFrame([{"pdf": row["pdf"], "question": row["question"], "gold": SEPARATOR.join(row["answers"]),
                   "doc_id": row["doc_id"], "question_id": row["question_id"], "pages": row["pages"]}
                  for row in saved]).to_csv(BATCH_CSV, index=False)
    print(f"{len(saved)} questions -> {QUESTIONS_JSON}, {BATCH_CSV}")


def spread(values):
    values = np.asarray(list(values), dtype=float)
    return {"median": round(float(np.median(values)), 3), "max": round(float(values.max()), 3)}


def summarise(answers, record):
    """Time per page per index step (per document), answer time per question, memory and answer quality."""
    pages = {number: document["pages"] for number, document in enumerate(record["stack"]["documents"], start=1)}
    per_doc = {}
    for stage in record["costs"]["stages"]:
        if "document" in stage and stage["stage"] in INDEX_STEPS:
            steps = per_doc.setdefault(stage["document"], dict.fromkeys(INDEX_STEPS, 0.0))
            steps[stage["stage"]] += stage["wall_seconds"]
    doc_ids = list(dict.fromkeys(answers["doc_id"]))  # batch numbers documents in first-appearance order
    by_doc = [{"document": number, "doc_id": doc_ids[number - 1], "pages": pages[number], "pages_without_text": document["pages_without_text"],
               "parser": document["parser"]["name"],
               **{f"{name}_seconds_per_page": round(steps[name] / pages[number], 3) for name in INDEX_STEPS}}
              for (number, steps), document in zip(sorted(per_doc.items()), record["stack"]["documents"])]
    not_found = answers["answer"].str.strip().str.lower().str.startswith("not found")
    return {"run_record": record["run_id"], "documents": by_doc,
            "seconds_per_page": {name: spread(row[f"{name}_seconds_per_page"] for row in by_doc) for name in INDEX_STEPS},
            "answer_seconds_per_question": {**spread(answers["answer_seconds"]), "mean": round(answers["answer_seconds"].mean(), 3)},
            "peak_ram_mb": record["costs"]["totals"]["peak_ram_mb"], "total_wall_seconds": record["costs"]["totals"]["wall_seconds"],
            "questions": len(answers), "f1": round(answers["f1"].mean(), 3),
            "contained": round(answers["contained"].astype(float).mean(), 3), "not_found": int(not_found.sum()),
            "answers_by_entry": answers["provider_entry"].value_counts().to_dict()}


def run():
    cache_root = AGENT_CACHE / "agent_test" / agent_run_id()
    answers, record_path = run_batch(BATCH_CSV, ANSWERS_CSV, 1250, fast=False, cache_root=cache_root)
    summary = summarise(answers, json.loads(Path(record_path).read_text(encoding="utf-8")))
    SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), f"\nanswers -> {ANSWERS_CSV}\nsummary -> {SUMMARY}\nrun record: {record_path}")


def main():
    steps = {"select": select, "download": download, "build": build, "run": run}
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("step", nargs="?", default="all", choices=[*steps, "all"])
    chosen = arg_parser.parse_args().step
    for name, step in steps.items():
        if chosen in (name, "all"):
            step()


if __name__ == "__main__":
    main()
