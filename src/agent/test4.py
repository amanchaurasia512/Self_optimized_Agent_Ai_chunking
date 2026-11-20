"""Agent test 4 (scaled), spec note "Agent test 4 (scaled): unseen documents with gold answers, design before running
(2026-11-20)": 50 MP-DocVQA val documents (scanned) and 50 CUAD contracts (digital) the study never used, 3 questions
each, batch mode in thorough mode at budget 1,250. A test of the tool, not a research claim. Writes only
pdfs/agent_test4_picks.csv and data/agent_test4/ (never pdfs/split.csv, catalog.csv or the study's picks).
Steps, from the repo root:
    .venv/bin/python -m src.agent.test4 select           draw, download, build the PDFs, write questions.csv
    .venv/bin/python -m src.agent.test4 plan             the run commands and a time estimate for this laptop
    .venv-docling/bin/python -m src.agent.test4 index    build every index (per document; failures recorded)
    .venv-docling/bin/python -m src.agent batch ...      the answers (printed by plan)
    .venv-docling/bin/python -m src.agent.test4 report   F1, contained, not found, times, memory, failures
Prints ids and counts only."""
import argparse
import json
import shutil
from pathlib import Path

import pandas as pd

from scripts.p1_cuad_download import REPO_ID as CUAD_REPO, doc_id_for, pdf_paths_by_title
from scripts.p1_cuad_select import CUAD_JSON, gold_spans
from scripts.rq5_scanned_select import MAX_PAGES, MIN_PAGES, page_list
from src.agent.unseen_scanned import (MIN_QUESTIONS, QUESTIONS_PER_DOC, SEED, SEPARATOR, TEST_PICKS, spread,
                                      study_documents)
from src.common.manifest import PROJECT_ROOT, RUNS_DIR, file_sha256, project_path
from src.common.paths import DATA
from src.common.pdf_catalog import PDF_MANIFEST
from src.common.split import SPLIT_FILE

DOCUMENTS = 50  # per kind
BUDGET = 1250
PICKS = PROJECT_ROOT / "pdfs" / "agent_test4_picks.csv"
OUTPUT = DATA / "agent_test4"
PDFS, CACHE = OUTPUT / "pdfs", OUTPUT / "cache"
QUESTIONS, BATCH_QUESTIONS, ANSWERS, SUMMARY = (OUTPUT / name for name in
                                                ("questions.csv", "batch_questions.csv", "answers.csv", "summary.json"))
INDEX_STEPS = ("scan_check", "parse", "chunk", "embed")
# Laptop CPU rates for the estimate, measured in thorough mode: scanned from the unseen scanned test (66 OCR pages),
# digital from the app's thorough index runs on digital PDFs (every page with a text layer).
SCANNED_RECORDS = ("A-LOCAL-20261113-16",)
DIGITAL_RECORDS = ("A-LOCAL-20261113-11", "A-LOCAL-20261113-13", "A-LOCAL-20261113-17", "A-LOCAL-20261113-19")
KAGGLE_ABOVE_HOURS = 3


# ---------- select ----------

def scanned_draw():
    """MP-DocVQA val with the rules of scripts/rq5_scanned_select.py, as src/agent/unseen_scanned.select reads it;
    the study's documents and the first agent test's picks excluded by id; 50 drawn with seed 42."""
    from huggingface_hub import HfApi, HfFileSystem
    from scripts.rq5_scanned_select import REPO, doc_names
    system = HfFileSystem()
    revision = HfApi().dataset_info(REPO.removeprefix("datasets/")).sha
    files = sorted(system.glob(f"{REPO}@{revision}/data/val-*.parquet"))
    names = doc_names(system, files[0])
    questions = pd.concat([pd.read_parquet(f"hf://{path}", columns=["questionId", "doc_id", "page_ids"], filesystem=system)
                           .assign(file=path.rsplit("/", 1)[1]) for path in files], ignore_index=True)
    if names:
        questions["doc_id"] = questions["doc_id"].map(lambda number: names[number])
    questions["pages"] = questions["page_ids"].map(page_list)
    documents = questions.groupby("doc_id").agg(page_lists=("pages", "nunique"), pages=("pages", lambda pages: len(pages.iloc[0])),
                                                 questions=("questionId", "nunique"),
                                                 files=("file", lambda files: " ".join(sorted(set(files))))).reset_index()
    excluded = study_documents() | set(pd.read_csv(TEST_PICKS)["doc_id"])
    eligible = documents[(documents["page_lists"] == 1) & documents["pages"].between(MIN_PAGES, MAX_PAGES)
                         & (documents["questions"] >= MIN_QUESTIONS) & ~documents["doc_id"].isin(excluded)]
    drawn = eligible.sort_values("doc_id").sample(DOCUMENTS, random_state=SEED)
    print(f"scanned: val documents {len(documents):,} | eligible {len(eligible)} (excluded by id: "
          f"{len(excluded & set(documents['doc_id']))}) | drawn {len(drawn)} | dataset revision {revision[:12]}")
    return drawn.assign(revision=revision)


def build_scanned(drawn):
    """The val parquet files when missing, then one PDF per document as rq5_scanned_build.py builds it, and 3 questions
    each (seed 42, from its questions sorted by questionId) with their answer lists."""
    import img2pdf
    from huggingface_hub import hf_hub_download
    from scripts.rq5_scanned_build import IMAGES, SOURCE, answer_list, picked_questions
    from scripts.rq5_scanned_select import REPO
    for name in sorted({name for names in drawn["files"] for name in names.split()}):
        if not (SOURCE / name).exists():
            hf_hub_download(REPO.removeprefix("datasets/"), f"data/{name}", repo_type="dataset",
                            revision=drawn["revision"].iloc[0], local_dir=SOURCE.parent)
    questions, picks, rows = picked_questions(drawn), [], []
    for doc in sorted(drawn["doc_id"]):
        doc_questions = questions[questions["doc_id"] == doc].sort_values("questionId")
        pages = page_list(doc_questions["page_ids"].iloc[0])
        first = doc_questions.iloc[0]
        images = [first[column]["bytes"] if first[column] is not None else None for column in IMAGES[:len(pages)]]
        assert all(images), f"{doc}: page images missing"
        target = PDFS / f"mpdocvqa_{doc}.pdf"
        target.write_bytes(img2pdf.convert(images))
        source = drawn.loc[drawn["doc_id"] == doc].iloc[0]
        picks.append({"kind": "scanned", "doc_id": f"mpdocvqa_{doc}", "source": "MP-DocVQA val", "pages": len(pages),
                      "questions": int(source["questions"]), "files": source["files"], "revision": source["revision"],
                      "pdf": project_path(target), "sha256": file_sha256(target)})
        for row in doc_questions.sample(QUESTIONS_PER_DOC, random_state=SEED).itertuples(index=False):
            answers = answer_list(row.answers)
            assert not any(SEPARATOR in answer for answer in answers), f"{doc}: an answer holds '{SEPARATOR}'"
            rows.append({"pdf": project_path(target), "question": row.question, "gold": SEPARATOR.join(answers),
                         "kind": "scanned"})
    return picks, rows


def digital_draw():
    """CUAD contracts not among the study's documents (pdfs/catalog.csv, pdfs/split.csv), with at least 3 questions
    whose gold has a span that occurs once in the contract (the P1 CUAD rule) and exactly one PDF in the CUAD repo
    (the p1_cuad_download rule); 50 drawn with seed 42. Returns (drawn contracts, their usable spans, PDF paths)."""
    spans = gold_spans(json.loads(CUAD_JSON.read_text(encoding="utf-8"))["data"])
    usable = spans[spans["occurrences"] == 1]
    catalog = pd.read_csv(PDF_MANIFEST, dtype=str)
    study_ids = set(catalog["doc_id"]) | set(pd.read_csv(SPLIT_FILE)["doc_id"])
    study_titles = set(catalog.loc[catalog["source_dataset"] == "CUAD v1", "source_title"])
    paths = pdf_paths_by_title()
    contracts = usable.groupby("contract")["category"].nunique().rename("questions").reset_index()
    unseen = contracts[~contracts["contract"].isin(study_titles) & ~contracts["contract"].map(doc_id_for).isin(study_ids)]
    eligible = unseen[(unseen["questions"] >= MIN_QUESTIONS) & unseen["contract"].map(lambda title: len(paths.get(title, [])) == 1)]
    drawn = eligible.sort_values("contract").sample(DOCUMENTS, random_state=SEED)
    print(f"digital: CUAD contracts {spans['contract'].nunique()} | not study documents {len(unseen)} | eligible "
          f"{len(eligible)} | drawn {len(drawn)}")
    return drawn, usable, paths


def build_digital(drawn, usable, paths):
    """Each drawn contract's PDF from the CUAD repo, and 3 questions (seed 42, from its usable categories sorted by
    name); the gold is every usable span of the category, as ' | ' alternatives."""
    from huggingface_hub import hf_hub_download
    from pypdf import PdfReader
    from scripts.p1_cuad_download import CUAD_DIR
    picks, rows = [], []
    for title in sorted(drawn["contract"]):
        source_path = paths[title][0]
        target = PDFS / f"{doc_id_for(title)}.pdf"
        shutil.copyfile(hf_hub_download(CUAD_REPO, source_path, repo_type="dataset", local_dir=CUAD_DIR), target)
        spans = usable[usable["contract"] == title]
        picks.append({"kind": "digital", "doc_id": doc_id_for(title), "source": "CUAD v1", "pages": len(PdfReader(target).pages),
                      "questions": int(spans["category"].nunique()), "files": source_path, "revision": None,
                      "pdf": project_path(target), "sha256": file_sha256(target)})
        categories = pd.Series(sorted(spans["category"].unique())).sample(QUESTIONS_PER_DOC, random_state=SEED)
        for category in categories:
            group = spans[spans["category"] == category]
            answers = list(dict.fromkeys(group["answer_text"].str.strip()))
            assert not any(SEPARATOR in answer for answer in answers), f"{title}: an answer holds '{SEPARATOR}'"
            rows.append({"pdf": project_path(target), "question": group["question"].iloc[0],
                         "gold": SEPARATOR.join(answers), "kind": "digital"})
    return picks, rows


def known_hashes():
    """SHA-256 of every study PDF (pdfs/catalog.csv) and of the first agent test's PDFs."""
    first_test = DATA / "agent_test" / "mpdocvqa"
    return set(pd.read_csv(PDF_MANIFEST, dtype=str)["sha256"].dropna()) | {file_sha256(path) for path in first_test.glob("*.pdf")}


def select():
    PDFS.mkdir(parents=True, exist_ok=True)
    scanned_picks, scanned_rows = build_scanned(scanned_draw())
    digital_picks, digital_rows = build_digital(*digital_draw())
    picks = pd.DataFrame(scanned_picks + digital_picks)
    reused = picks[picks["sha256"].isin(known_hashes())]
    if len(reused):
        raise SystemExit(f"stopped: picks with the SHA-256 of a study or agent-test PDF: {', '.join(reused['doc_id'])}")
    picks.to_csv(PICKS, index=False)
    questions = pd.DataFrame(scanned_rows + digital_rows)
    questions.to_csv(QUESTIONS, index=False)
    for kind, group in picks.groupby("kind"):
        print(f"{kind}: {len(group)} documents | {group['pages'].sum():,} pages (median {group['pages'].median():.0f}, "
              f"max {group['pages'].max()}) | {(questions['kind'] == kind).sum()} questions")
    print(f"saved {project_path(PICKS)}, {project_path(QUESTIONS)}; PDFs in {project_path(PDFS)}")


# ---------- plan ----------

def seconds_per_page(run_ids):
    """Index seconds (scan check, parse, chunk, embed) per page over the named run records."""
    seconds = pages = 0.0
    for run_id in run_ids:
        record = json.loads((RUNS_DIR / f"{run_id}.json").read_text(encoding="utf-8"))
        documents = record["stack"].get("documents") or [record["stack"]]
        seconds += sum(stage["wall_seconds"] for stage in record["costs"]["stages"] if stage["stage"] in INDEX_STEPS)
        pages += sum(document["pages"] for document in documents)
    return seconds / pages


def plan():
    from scripts.aq_run import INTERVAL
    picks, questions = pd.read_csv(PICKS), pd.read_csv(QUESTIONS)
    rates = {"scanned": seconds_per_page(SCANNED_RECORDS), "digital": seconds_per_page(DIGITAL_RECORDS)}
    index_seconds = {kind: picks.loc[picks["kind"] == kind, "pages"].sum() * rate for kind, rate in rates.items()}
    answer_seconds = len(questions) * INTERVAL
    total = sum(index_seconds.values()) + answer_seconds
    for kind, rate in rates.items():
        print(f"{kind}: {picks.loc[picks['kind'] == kind, 'pages'].sum():,} pages x {rate:.1f} s/page = "
              f"{index_seconds[kind] / 3600:.1f} h")
    print(f"answers: {len(questions)} x {INTERVAL:.2f} s = {answer_seconds / 60:.0f} min | total about {total / 3600:.1f} h "
          f"on this laptop's CPU\n\nlaptop:\n  .venv-docling/bin/python -m src.agent.test4 index\n"
          f"  .venv-docling/bin/python -m src.agent batch {project_path(BATCH_QUESTIONS)} -o {project_path(ANSWERS)} "
          f"--cache-root {project_path(CACHE)} --budget {BUDGET}\n  .venv-docling/bin/python -m src.agent.test4 report")
    if total / 3600 > KAGGLE_ABOVE_HOURS:
        print(f"\nover {KAGGLE_ABOVE_HOURS} h: index on Kaggle (notebooks/kaggle/agent-test4-kn01.ipynb), unzip its output at "
              f"the repo root, then run the batch and report commands above (every index is then a cache hit)")


# ---------- index ----------

def index_documents(cache_root=CACHE, machine="laptop", source="LOCAL"):
    """Builds or loads every PDF's thorough index one at a time; a document that fails is recorded with its error and
    left out of batch_questions.csv. One run record for the step."""
    from src.agent import index
    from src.agent.ask import load_embedder, open_index
    from src.agent.batch import sealed_pdfs, tag
    from src.agent.pipeline import SPEC, agent_run_id, chunker_info, plan_stack
    from src.common import manifest
    from src.common.cost_logger import CostLogger
    from src.eval.embed import EMBEDDER
    questions = pd.read_csv(QUESTIONS, dtype=str, keep_default_na=False)
    kinds = dict(zip(questions["pdf"], questions["kind"]))
    pdfs = list(kinds)
    sealed = sealed_pdfs(pdfs)
    if sealed:
        raise SystemExit(f"refused, not tuning documents in pdfs/split.csv: {', '.join(sorted(sealed.values()))}")
    logger, run_id = CostLogger(), agent_run_id(source)
    load_embedder(index.embed, logger)
    documents, failures = [], []
    for number, pdf in enumerate(pdfs, start=1):
        start, status = len(logger.stages), "ok"
        try:
            session = open_index(pdf, logger, run_id, False, None, cache_root, index.embed)
            documents.append({"document": number, "pdf": pdf, "kind": kinds[pdf],
                              **plan_stack(session["planned"], session["document"]),
                              "pdf_sha256": session["planned"]["pdf_sha"], "cache_hit": session["cache_hit"],
                              "chunks": len(session["chunks"])})
        except Exception as error:  # a test of the tool: record the failure and go on with the next document
            status = f"{type(error).__name__}: {error}"
            failures.append({"document": number, "pdf": pdf, "kind": kinds[pdf], "error": status})
        tag(logger, start, document=number)
        print(f"{number}/{len(pdfs)} {Path(pdf).stem}: {status}")
    indexed = {document["pdf"] for document in documents}
    questions[questions["pdf"].isin(indexed)].to_csv(BATCH_QUESTIONS, index=False)
    stack = {"agent_mode": "test4_index", "parser_mode": "thorough", "chunker": chunker_info(), "embedder": EMBEDDER,
             "cache_root": manifest.project_path(cache_root), "documents": documents, "failures": failures}
    record = manifest.build_manifest(run_id, SPEC, stack, [QUESTIONS, *map(Path, pdfs)], [BATCH_QUESTIONS],
                                     logger.summary(), machine)
    print(f"{len(documents)} indexed, {len(failures)} failed -> {project_path(BATCH_QUESTIONS)}\n"
          f"run record: {manifest.write_manifest(record)}")


# ---------- report ----------

def newest_record(matches):
    """The newest agent run record for which matches(record) holds, or None."""
    records = [json.loads(path.read_text(encoding="utf-8")) for path in RUNS_DIR.glob("A-*.json")]
    found = sorted((record for record in records if matches(record)), key=lambda record: record["created_at"])
    return found[-1] if found else None


def step_rows(record):
    """Per document: kind, pages, pages without text, seconds per page per index step and peak memory."""
    stages = [stage for stage in record["costs"]["stages"] if "document" in stage]
    rows = []
    for document in record["stack"]["documents"]:
        own = [stage for stage in stages if stage["document"] == document["document"]]
        rows.append({"kind": document["kind"], "pages": document["pages"], "pages_without_text": document["pages_without_text"],
                     "peak_ram_mb": max(stage["peak_ram_mb"] for stage in own),
                     **{step: sum(stage["wall_seconds"] for stage in own if stage["stage"] == step) / document["pages"]
                        for step in INDEX_STEPS}})
    return pd.DataFrame(rows)


def kind_summary(kind, steps, answers, failures):
    not_found = answers["answer"].fillna("").str.strip().str.lower().str.startswith("not found")
    return {"documents_indexed": len(steps), "pages": int(steps["pages"].sum()),
            "pages_without_text": int(steps["pages_without_text"].sum()),
            "seconds_per_page": {step: spread(steps[step]) for step in INDEX_STEPS},
            "peak_ram_mb": float(steps["peak_ram_mb"].max()) if len(steps) else None,
            "questions_answered": len(answers), "f1": round(float(answers["f1"].mean()), 3),
            "contained": round(float(answers["contained"].astype(float).mean()), 3), "not_found": int(not_found.sum()),
            "answer_seconds_per_question": spread(answers["answer_seconds"]),
            "failures": [failure for failure in failures if failure["kind"] == kind]}


def report():
    answers_path = project_path(ANSWERS)
    index_record = newest_record(lambda record: record["stack"].get("agent_mode") == "test4_index")
    batch_record = newest_record(lambda record: record["stack"].get("agent_mode") == "batch" and answers_path in record["outputs"])
    if index_record is None or batch_record is None:
        raise SystemExit("needs the test4 index run record and the batch run record that wrote answers.csv")
    answers, steps = pd.read_csv(ANSWERS), step_rows(index_record)
    failures = index_record["stack"]["failures"]
    summary = {"index_run_record": index_record["run_id"], "index_machine": index_record["environment"]["machine"],
               "batch_run_record": batch_record["run_id"], "questions": int(batch_record["stack"]["questions"]),
               "answered": int(batch_record["stack"]["answered"]), "answers_by_entry": batch_record["stack"]["answers_by_entry"],
               "batch_peak_ram_mb": batch_record["costs"]["totals"]["peak_ram_mb"],
               **{kind: kind_summary(kind, steps[steps["kind"] == kind], answers[answers["kind"] == kind], failures)
                  for kind in ("digital", "scanned")}}
    SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), f"\nsummary -> {project_path(SUMMARY)}")


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    arg_parser.add_argument("step", choices=("select", "plan", "index", "report"))
    arg_parser.add_argument("--cache-root", default=str(CACHE), help="index step: cache folder")
    arg_parser.add_argument("--machine", default="laptop", help="index step: machine in the run record")
    arg_parser.add_argument("--source", default="LOCAL", help="index step: run id source, e.g. AT4-KN01 on Kaggle")
    args = arg_parser.parse_args()
    if args.step == "index":
        index_documents(Path(args.cache_root), args.machine, args.source)
    else:
        {"select": select, "plan": plan, "report": report}[args.step]()


if __name__ == "__main__":
    main()
