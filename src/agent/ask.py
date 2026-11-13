"""Agent ask mode (spec/agent_v1.md, Ask mode): PDF + question -> cached index -> hybrid retrieval within the budget ->
answer from the provider list. One run record per question; the question and answer text only with record_text."""
import hashlib
from pathlib import Path

from src.agent import index, providers
from src.agent.pipeline import SPEC, agent_run_id, build, chunker_info, plan, plan_inputs, plan_stack
from src.common import manifest
from src.common.cost_logger import CostLogger
from src.common.paths import AGENT_CACHE
from src.eval.embed import EMBEDDER

SETTING = "method1_tree_T384_noprefix"


def text_record(text, record_text):
    record = {"sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "characters": len(text)}
    return {**record, "text": text} if record_text else record


def ask_pdf(pdf_path, question, budget=1250, fast=False, from_extraction=None, context_only=False, record_text=False,
            machine="laptop", cache_root=AGENT_CACHE, embed=index.embed, answer=providers.answer):
    """{answer, provider entry and model, context, sources, tokens read, cache hit, run record path}."""
    if budget not in index.BUDGETS:
        raise ValueError(f"budget must be one of {index.BUDGETS}, not {budget}")
    logger = CostLogger()
    planned = plan(pdf_path, fast, from_extraction, logger, cache_root)
    folder = index.index_folder(planned, SETTING, cache_root)
    run_id = agent_run_id()
    with logger.stage("load_index"):
        found = index.cached_index(folder, planned["parser"], chunker_info())
    if found:
        document, chunk_doc, info = found
    else:
        document, chunk_doc = build(planned, run_id, logger)
        info = index.index_info(document["parser"], chunker_info())
        with logger.stage("embed") as stage:
            index.save_index(folder, document, chunk_doc, info, embed)
            stage["chunks"] = len(chunk_doc["chunks"])
    with logger.stage("retrieve"):
        chunks = index.load_chunks(folder / "chunks.json")
        context, used, read = index.retrieve(question, embed([question])[0], chunks, index.chunk_vectors(folder, chunks),
                                             document["text"], budget)
    sources = [{"chunk_id": chunk_doc["chunks"][position]["chunk_id"], "pages": chunk_doc["chunks"][position]["pages"]}
               for position in read]
    reply = None
    if not context_only:
        with logger.stage("answer"):
            reply = answer(question, context)

    stack = {"agent_mode": "ask", **plan_stack(planned, document), "embedder": EMBEDDER,
             "cache": {"hit": bool(found), "folder": manifest.project_path(folder)}, "budget": budget,
             "tokens_read": int(used), "chunks_read": sources, "question": text_record(question, record_text),
             "context_only": context_only,
             "answer": text_record(reply["answer"], record_text) if reply else None,
             "answer_provider": {key: reply[key] for key in ("entry", "provider", "model")} if reply else None}
    outputs = [folder / name for name in index.FILES]
    record = manifest.build_manifest(run_id, SPEC, stack, plan_inputs(planned), outputs, logger.summary(), machine)
    return {"answer": reply["answer"] if reply else None,
            "provider": {key: reply[key] for key in ("entry", "provider", "model")} if reply else None,
            "context": context, "sources": sources, "tokens_read": int(used), "cache_hit": bool(found),
            "run_record": manifest.write_manifest(record)}
