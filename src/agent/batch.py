"""Agent batch mode (spec/agent_v1.md, Chat and batch modes): a CSV of pdf, question, gold -> bge-m3 loaded once,
every document's index built or loaded first, then every question answered (answer calls paced as scripts/aq_run)
-> a CSV with the answer, provider entry, step times, token F1 and contained; one run record for the batch."""
import time
from collections import Counter
from pathlib import Path

import pandas as pd

from scripts.aq_run import INTERVAL, contained, token_f1
from src.agent import index, providers
from src.agent.ask import SETTING, ask_index, load_embedder, open_index
from src.agent.pipeline import SPEC, agent_run_id, chunker_info, plan_stack
from src.common import manifest
from src.common.cost_logger import CostLogger
from src.common.paths import AGENT_CACHE
from src.common.pdf_catalog import PDF_MANIFEST
from src.common.split import SPLIT_FILE
from src.eval.embed import EMBEDDER

COLUMNS = ("pdf", "question", "gold")


def sealed_pdfs(pdf_paths):
    """{pdf: doc_id} for PDFs that are study documents (same SHA-256) whose split is not tuning."""
    catalog = pd.read_csv(PDF_MANIFEST, dtype=str)
    doc_by_sha = dict(zip(catalog["sha256"], catalog["doc_id"]))
    split = pd.read_csv(SPLIT_FILE).set_index("doc_id")["split"]
    found = {pdf: doc_by_sha.get(manifest.file_sha256(pdf)) for pdf in pdf_paths}
    return {pdf: doc_id for pdf, doc_id in found.items() if doc_id and split.get(doc_id) != "tuning"}


def tag(logger, start, **fields):
    """Marks every step logged since position start with its document or question number."""
    for stage in logger.stages[start:]:
        stage.update(fields)


def seconds(logger, start):
    return {stage["stage"]: stage["wall_seconds"] for stage in logger.stages[start:]}


def run_batch(questions_csv, output_csv, budget=1250, fast=False, cache_root=AGENT_CACHE, machine="laptop",
              embed=index.embed, answer=providers.answer, sleep=time.sleep, clock=time.monotonic, interval=INTERVAL):
    """Writes output_csv (also when a provider error stops the batch part-way) and the run record; returns
    (answer rows as a DataFrame, run record path)."""
    rows = pd.read_csv(questions_csv, dtype=str, keep_default_na=False)
    missing = set(COLUMNS) - set(rows.columns)
    if missing:
        raise ValueError(f"{questions_csv} lacks the column(s) {', '.join(sorted(missing))}")
    if budget not in index.BUDGETS:
        raise ValueError(f"budget must be one of {index.BUDGETS}, not {budget}")
    pdfs = list(dict.fromkeys(rows["pdf"]))
    sealed = sealed_pdfs(pdfs)
    if sealed:
        raise ValueError(f"refused, not tuning documents in pdfs/split.csv: {', '.join(sorted(sealed.values()))}")

    logger, run_id = CostLogger(), agent_run_id()
    load_embedder(embed, logger)
    sessions, index_seconds = {}, {}
    for number, pdf in enumerate(pdfs, start=1):
        start = len(logger.stages)
        sessions[pdf] = open_index(pdf, logger, run_id, fast, None, cache_root, embed)
        tag(logger, start, document=number)
        index_seconds[pdf] = round(sum(seconds(logger, start).values()), 3)

    answered, last_call = [], None
    try:
        for number, row in enumerate(rows.to_dict("records"), start=1):
            start, session = len(logger.stages), sessions[row["pdf"]]
            result = ask_index(session, row["question"], logger, budget, context_only=True, embed=embed)
            with logger.stage("pace"):
                if last_call is not None:
                    sleep(max(0.0, last_call + interval - clock()))
            last_call = clock()
            with logger.stage("answer"):
                reply = answer(row["question"], result["context"])
            tag(logger, start, question=number)
            steps = seconds(logger, start)
            answered.append({**row, "answer": reply["answer"], "provider_entry": reply["entry"],
                             "provider": reply["provider"], "model": reply["model"],
                             "parser": session["planned"]["parser"], "cache_hit": session["cache_hit"],
                             "tokens_read": result["tokens_read"], "index_seconds": index_seconds[row["pdf"]],
                             "retrieve_seconds": steps["retrieve"], "pace_seconds": steps["pace"],
                             "answer_seconds": steps["answer"], "f1": round(token_f1(reply["answer"], row["gold"]), 4),
                             "contained": contained(reply["answer"], row["gold"])})
    finally:
        table = pd.DataFrame(answered)
        Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(output_csv, index=False)
        documents = [{"document": number, **plan_stack(sessions[pdf]["planned"], sessions[pdf]["document"]),
                      "pdf_sha256": sessions[pdf]["planned"]["pdf_sha"], "cache_hit": sessions[pdf]["cache_hit"],
                      "chunks": len(sessions[pdf]["chunks"])} for number, pdf in enumerate(pdfs, start=1)]
        stack = {"agent_mode": "batch", "parser_mode": "fast" if fast else "thorough", "setting": SETTING,
                 "chunker": chunker_info(), "embedder": EMBEDDER, "budget": budget, "pace_seconds": round(interval, 3),
                 "cache_root": manifest.project_path(cache_root), "documents": documents,
                 "questions": len(rows), "answered": len(answered),
                 "answers_by_entry": dict(Counter(row["provider_entry"] for row in answered))}
        record = manifest.build_manifest(run_id, SPEC, stack, [Path(questions_csv), *map(Path, pdfs)],
                                         [Path(output_csv)], logger.summary(), machine)
        record_path = manifest.write_manifest(record)
    return table, record_path
