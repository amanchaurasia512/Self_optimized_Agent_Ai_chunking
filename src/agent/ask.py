"""Agent ask and chat modes (spec/agent_v1.md, Ask mode; Chat and batch modes): PDF + question -> cached index ->
hybrid retrieval within the budget -> answer from the provider list. One run record per question; the question and
answer text only with record_text."""
import hashlib

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


def load_embedder(embed, logger):
    """Loads bge-m3 in its own step, so later steps time only their own work (a fake embed loads nothing)."""
    with logger.stage("load_embedder"):
        if embed is index.embed:
            index.encoder()


def open_index(pdf_path, logger, run_id, fast=False, from_extraction=None, cache_root=AGENT_CACHE, embed=index.embed):
    """Scan check, then the cached index or a new one (parse, chunk, embed), then its chunks and vectors: a session."""
    planned = plan(pdf_path, fast, from_extraction, logger, cache_root)
    folder = index.index_folder(planned, SETTING, cache_root)
    with logger.stage("load_index"):
        found = index.cached_index(folder, planned["parser"], chunker_info())
    if found:
        document, chunk_doc, info = found
    else:
        document, chunk_doc = build(planned, run_id, logger)
        with logger.stage("embed") as stage:
            index.save_index(folder, document, chunk_doc, index.index_info(document["parser"], chunker_info()), embed)
            stage["chunks"] = len(chunk_doc["chunks"])
    with logger.stage("load_vectors"):
        chunks = index.load_chunks(folder / "chunks.json")
        vectors = index.chunk_vectors(folder, chunks)
    return {"planned": planned, "folder": folder, "document": document, "chunk_doc": chunk_doc, "chunks": chunks,
            "vectors": vectors, "cache_hit": bool(found)}


def ask_index(session, question, logger, budget=1250, context_only=False, embed=index.embed, answer=providers.answer):
    """Retrieval and (unless context_only) the answer for one question: {answer, provider, context, sources, tokens
    read}."""
    if budget not in index.BUDGETS:
        raise ValueError(f"budget must be one of {index.BUDGETS}, not {budget}")
    with logger.stage("retrieve"):
        context, used, read = index.retrieve(question, embed([question])[0], session["chunks"], session["vectors"],
                                             session["document"]["text"], budget)
    chunk_list = session["chunk_doc"]["chunks"]
    sources = [{"chunk_id": chunk_list[position]["chunk_id"], "pages": chunk_list[position]["pages"]} for position in read]
    reply = None
    if not context_only:
        with logger.stage("answer"):
            reply = answer(question, context)
    return {"answer": reply["answer"] if reply else None,
            "provider": {key: reply[key] for key in ("entry", "provider", "model")} if reply else None,
            "context": context, "sources": sources, "tokens_read": int(used)}


def write_ask_record(run_id, session, question, result, logger, budget, context_only, record_text, machine, mode="ask"):
    planned, folder = session["planned"], session["folder"]
    stack = {"agent_mode": mode, **plan_stack(planned, session["document"]), "embedder": EMBEDDER,
             "cache": {"hit": session["cache_hit"], "folder": manifest.project_path(folder)}, "budget": budget,
             "tokens_read": result["tokens_read"], "chunks_read": result["sources"],
             "question": text_record(question, record_text), "context_only": context_only,
             "answer": text_record(result["answer"], record_text) if result["provider"] else None,
             "answer_provider": result["provider"]}
    outputs = [folder / name for name in index.FILES]
    return manifest.write_manifest(manifest.build_manifest(run_id, SPEC, stack, plan_inputs(planned), outputs,
                                                           logger.summary(), machine))


def ask_pdf(pdf_path, question, budget=1250, fast=False, from_extraction=None, context_only=False, record_text=False,
            machine="laptop", cache_root=AGENT_CACHE, embed=index.embed, answer=providers.answer):
    """{answer, provider entry and model, context, sources, tokens read, cache hit, run record path}."""
    if budget not in index.BUDGETS:
        raise ValueError(f"budget must be one of {index.BUDGETS}, not {budget}")
    logger, run_id = CostLogger(), agent_run_id()
    session = open_index(pdf_path, logger, run_id, fast, from_extraction, cache_root, embed)
    result = ask_index(session, question, logger, budget, context_only, embed, answer)
    record = write_ask_record(run_id, session, question, result, logger, budget, context_only, record_text, machine)
    return {**result, "cache_hit": session["cache_hit"], "run_record": record}


def chat(pdf_path, questions, budget=1250, fast=False, record_text=False, machine="laptop", cache_root=AGENT_CACHE,
         embed=index.embed, answer=providers.answer):
    """Opens the index and bge-m3 once, then yields one result per question from the questions iterable (stops at
    the first empty one). The first run record also holds the opening steps."""
    if budget not in index.BUDGETS:
        raise ValueError(f"budget must be one of {index.BUDGETS}, not {budget}")
    logger, run_id = CostLogger(), agent_run_id()
    load_embedder(embed, logger)
    session = open_index(pdf_path, logger, run_id, fast, None, cache_root, embed)
    yield {"opened": True, "cache_hit": session["cache_hit"], "chunks": len(session["chunks"]),
           "parser": session["planned"]["parser"]}
    for question in questions:
        if not question.strip():
            return
        result = ask_index(session, question, logger, budget, embed=embed, answer=answer)
        record = write_ask_record(run_id, session, question, result, logger, budget, False, record_text, machine, "chat")
        yield {**result, "cache_hit": session["cache_hit"], "run_record": record}
        logger, run_id = CostLogger(), agent_run_id()
