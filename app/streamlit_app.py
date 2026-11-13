"""PDF chunking agent, local app v1 (spec/agent_v1.md, App v1). Run from the repo root in the Docling environment:
    .venv-docling/bin/streamlit run app/streamlit_app.py
Upload a PDF, build its index (cached by SHA-256), ask questions, download its chunk.json. The pipeline is
src/agent/ask.open_index and ask_index; this file only shows it."""
import hashlib
import json
import os
from functools import partial
from pathlib import Path

import streamlit as st

from src.agent import index, pipeline, providers
from src.agent.ask import ProgressLogger, ask_index, open_index, write_ask_record, write_index_record
from src.common.cost_logger import CostLogger
from src.common.paths import AGENT_CACHE

MAX_MB = 50  # also server.maxUploadSize in .streamlit/config.toml
SNIPPET = 300  # characters of each chunk read shown under the answer
BUDGETS = index.BUDGETS
CACHE_ROOT = Path(os.environ.get("AGENT_CACHE_DIR", AGENT_CACHE))
MACHINE = os.environ.get("AGENT_MACHINE", "laptop")
STEPS = {"scan_check": "Scan check", "load_index": "Cache lookup", "parse": "Parse", "chunk": "Chunk", "embed": "Embed",
         "load_vectors": "Load vectors", "retrieve": "Retrieve", "answer": "Answer"}


@st.cache_resource(show_spinner="Loading bge-m3 (once per server process)")
def embedder():
    return index.encoder()


@st.cache_resource(show_spinner="Loading the Docling converter (once per server process)")
def converter():
    return pipeline.docling_converter()


def step_table(stages):
    return [{"step": STEPS.get(stage["stage"], stage["stage"]), "seconds": round(stage["wall_seconds"], 2)}
            for stage in stages]


def saved_upload(uploaded):
    """(PDF path under the cache's uploads folder, SHA-256); refuses files over the limit."""
    data = uploaded.getvalue()
    if len(data) > MAX_MB * 2**20:
        st.error(f"{uploaded.name} is {len(data) / 2**20:.1f} MB; the limit is {MAX_MB} MB.")
        st.stop()
    sha = hashlib.sha256(data).hexdigest()
    path = CACHE_ROOT / "uploads" / sha / Path(uploaded.name).name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return path, sha


def build_index(pdf_path, fast):
    """open_index with a progress line per step and embedding progress by chunks; writes the app_index run record."""
    with st.status("Building the index", expanded=True) as status:
        lines = {}
        bar = st.empty()

        def on_step(name, state, seconds):
            if state == "start":
                lines[name] = st.empty()
                lines[name].write(f"{STEPS.get(name, name)}…")
            else:
                lines[name].write(f"{STEPS.get(name, name)}: {seconds:.1f} s")

        def on_embedded(done, total):
            bar.progress(done / total, text=f"Embedded {done} of {total} chunks")

        logger, run_id = ProgressLogger(on_step), pipeline.agent_run_id()
        session = open_index(pdf_path, logger, run_id, fast, None, CACHE_ROOT, partial(index.embed, progress=on_embedded))
        record = write_index_record(run_id, session, logger, MACHINE, "app_index")
        state = "cached" if session["cache_hit"] else "built"
        status.update(label=f"Index {state}: {len(session['chunks'])} chunks ({session['planned']['parser']})",
                      state="complete", expanded=False)
    return session, logger.stages, record


def sidebar():
    st.sidebar.header("Settings")
    mode = st.sidebar.radio("Parser mode", ["thorough", "fast"],
                            help="Thorough: Docling for every PDF. Fast: pdfplumber, Docling if any page has no text.")
    budget = st.sidebar.selectbox("Reading budget (tokens)", BUDGETS, index=BUDGETS.index(1250))
    record_text = st.sidebar.checkbox("Record text", help="Store the question and answer text in the run record.")
    st.sidebar.header("Answer providers")
    try:
        for row in providers.list_entries():
            found = "" if row["key_file_found"] else ", key file missing"
            st.sidebar.caption(f"{row['position']}. {row['name']} ({row['provider']}, {row['model']}): {row['status']}{found}")
    except providers.ProviderError as error:
        st.sidebar.warning(str(error))
    return mode == "fast", budget, record_text


def show_answer(item):
    st.markdown(f"**Q:** {item['question']}")
    st.write(item["answer"])
    st.caption(f"answered by {item['provider']['entry']} ({item['provider']['provider']}, {item['provider']['model']}) · "
               f"{item['tokens_read']} of {item['budget']} tokens read · "
               + " · ".join(f"{row['step'].lower()} {row['seconds']:.2f} s" for row in item["steps"]))
    with st.expander(f"Sources ({len(item['sources'])} chunks)"):
        for source in item["sources"]:
            st.markdown(f"**{source['chunk_id']}**, p. {', '.join(map(str, source['pages']))}")
            st.text(source["snippet"])


def main():
    st.set_page_config(page_title="PDF chunking agent", page_icon="📄")
    st.title("PDF chunking agent")
    fast, budget, record_text = sidebar()
    embedder()
    uploaded = st.file_uploader(f"PDF (at most {MAX_MB} MB)", type=["pdf"])
    if not uploaded:
        st.info("Upload a PDF to build its index.")
        return
    pdf_path, sha = saved_upload(uploaded)
    key = (sha, fast)
    if st.session_state.get("index_key") != key:
        if not fast:
            converter()
        session, steps, record = build_index(pdf_path, fast)
        st.session_state.update(index_key=key, session=session, index_steps=steps, index_record=str(record), answers=[],
                                chunk_json=json.dumps(session["chunk_doc"], ensure_ascii=False, indent=2))
    session = st.session_state["session"]
    st.caption(f"{uploaded.name}: {session['planned']['page_count']} pages, {len(session['chunks'])} chunks, "
               f"parser {session['planned']['parser']} ({session['planned']['reason']}), "
               f"index {'cached' if session['cache_hit'] else 'built'} · "
               + " · ".join(f"{row['step'].lower()} {row['seconds']:.1f} s" for row in step_table(st.session_state["index_steps"])))
    st.download_button("Download chunk.json", st.session_state["chunk_json"], file_name=f"{pdf_path.stem}.chunks.json",
                       mime="application/json")

    question = st.text_input("Question")
    if st.button("Ask", disabled=not question.strip()):
        logger, run_id = CostLogger(), pipeline.agent_run_id()
        try:
            with st.spinner("Retrieving and answering"):
                result = ask_index(session, question, logger, budget, embed=index.embed, answer=providers.answer)
        except providers.ProviderError as error:
            st.error(str(error))
            st.stop()
        record = write_ask_record(run_id, session, question, result, logger, budget, False, record_text, MACHINE, "app_ask")
        chunk_list = session["chunk_doc"]["chunks"]
        texts = {chunk["chunk_id"]: chunk["text"] for chunk in chunk_list}
        st.session_state["answers"].insert(0, {
            "question": question, "answer": result["answer"], "provider": result["provider"], "budget": budget,
            "tokens_read": result["tokens_read"], "steps": step_table(logger.stages), "run_record": str(record),
            "sources": [{**source, "snippet": texts[source["chunk_id"]][:SNIPPET]} for source in result["sources"]]})
    for item in st.session_state["answers"]:
        show_answer(item)


main()
