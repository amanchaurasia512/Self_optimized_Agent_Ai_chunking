"""Agent test 4, LLM comparison (spec v1.2 note "Agent test 4: LLM comparison, design before running", 2026-11-23).
Step A saves each question's retrieved context (thorough mode, budget 1,250, the AT4-KN01 index, no LLM call); step B
answers from the saved contexts only, with gemini-3.5-flash-lite (entry gemini-a only, paced) or qwen2.5:3b (Ollama,
local). Both steps append one JSON line per qid and skip qids already saved, so a restart goes on where it stopped.
One run record per session, naming the previous session's record in continues. A test of the tool, not a research
claim: no study document is used (sealed study PDFs are refused), so no --final gate. Steps, from the repo root:
    .venv-docling/bin/python -m src.agent.test4_llm contexts
    .venv/bin/python -m src.agent.test4_llm answers --model gemini
    .venv/bin/python -m src.agent.test4_llm answers --model qwen
    .venv/bin/python -m src.agent.test4_llm summary      token counts per model -> llm_summary.json
Each answer line holds the token counts from the model's own response (Gemini usage metadata: input, output, thinking;
Ollama prompt_eval_count and eval_count), never estimates.
Prints ids and counts only."""
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from scripts.aq_run import ANSWER_PROMPT, INTERVAL
from src.agent import providers
from src.agent.pipeline import SPEC
from src.common import manifest
from src.common.manifest import RUNS_DIR, project_path
from src.common.paths import DATA

BUDGET = 1250
OUTPUT = DATA / "agent_test4"
QUESTIONS, CACHE = OUTPUT / "questions.csv", OUTPUT / "cache"
CONTEXTS = "contexts.jsonl"
SETTING = "method1_tree_T384_noprefix"  # the AT4-KN01 index (src/agent/ask.SETTING)
MAX_OUTPUT_TOKENS, TRIES, ERROR_WAIT = 256, 3, 30
MODELS = {
    "gemini": {"model": "gemini-3.5-flash-lite", "entry": "gemini-a", "file": "answers_gemini-3.5-flash-lite.jsonl",
               "paced_seconds": round(INTERVAL, 3),
               # thinking off; if the model refuses it, its lowest thinking level (the setting sent is recorded)
               "thinking": ({"thinking_budget": 0}, {"thinking_level": "MINIMAL"})},
    "qwen": {"model": "qwen2.5:3b", "file": "answers_qwen2.5-3b.jsonl", "paced_seconds": None,
             # num_ctx set so the ~1,250-token context is never cut by Ollama's default window; prompt tokens recorded
             "options": {"temperature": 0, "num_predict": MAX_OUTPUT_TOKENS, "num_ctx": 8192}},
}


def qid(pdf, question):
    return hashlib.sha256(f"{pdf}|{question}".encode("utf-8")).hexdigest()[:12]


def read_questions(questions_file):
    rows = pd.read_csv(questions_file, dtype=str, keep_default_na=False).to_dict("records")
    return [{"qid": qid(row["pdf"], row["question"]), **row} for row in rows]


def read_lines(path):
    path = Path(path)
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def append_line(handle, line):
    handle.write(json.dumps(line, ensure_ascii=False) + "\n")
    handle.flush()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- session run records ----------

def session_id(records_dir):
    """A-LOCAL-{date}-{n} in runs/ (as pipeline.agent_run_id); A-TEST-{date}-{n} for test records elsewhere."""
    source = "LOCAL" if Path(records_dir).resolve() == RUNS_DIR.resolve() else "TEST"
    prefix = f"A-{source}-{datetime.now():%Y%m%d}"
    numbers = [int(path.stem.rsplit("-", 1)[1]) for path in Path(records_dir).glob(f"*{prefix}-*.json")]
    return f"{prefix}-{max(numbers, default=0) + 1}"


def previous_session(records_dir, mode, output):
    """The run id of the newest session record of this step writing to this output file, or None."""
    records = [json.loads(path.read_text(encoding="utf-8")) for path in Path(records_dir).glob("*A-*.json")]
    found = sorted((record for record in records if record["stack"].get("agent_mode") == mode
                    and record["stack"].get("output") == project_path(output)), key=lambda record: record["created_at"])
    return found[-1]["run_id"] if found else None


def write_session(records_dir, run_id, stack, inputs, output, costs, machine):
    """runs/<id>.json, or runs/tests/test_at4llm_<id>.json for test sessions; never rewritten."""
    record = manifest.build_manifest(run_id, SPEC, stack, inputs, [output], costs, machine)
    records_dir = Path(records_dir)
    if records_dir.resolve() == RUNS_DIR.resolve():
        return manifest.write_manifest(record)
    path = records_dir / f"test_at4llm_{run_id}.json"
    if path.exists():
        raise FileExistsError(f"run record already exists: {path}")
    records_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return path


# ---------- step A: contexts ----------

def cached_folder(pdf, cache_root):
    """The AT4-KN01 index folder of this PDF when it is complete and current; None otherwise (never rebuilt here)."""
    from src.agent import index
    from src.agent.pipeline import chunker_info
    folder = Path(cache_root) / manifest.file_sha256(pdf) / f"docling_{SETTING}"
    return folder if index.cached_index(folder, "docling", chunker_info()) else None


def contexts(questions_file, output_dir, cache_root, records_dir, machine, limit=None):
    from src.agent import index
    from src.agent.ask import ask_index, load_embedder, open_index
    from src.agent.batch import sealed_pdfs
    from src.common.cost_logger import CostLogger
    from src.eval.embed import EMBEDDER
    questions = read_questions(questions_file)
    pdfs = list(dict.fromkeys(row["pdf"] for row in questions))
    sealed = sealed_pdfs(pdfs)
    if sealed:
        raise SystemExit(f"refused, not tuning documents in pdfs/split.csv: {', '.join(sorted(sealed.values()))}")
    output = Path(output_dir) / CONTEXTS
    saved = {line["qid"] for line in read_lines(output)}
    todo = [row for row in questions if row["qid"] not in saved][:limit]
    run_id, started = session_id(records_dir), now()
    continues = previous_session(records_dir, "test4_contexts", output)
    logger, done, failures, current = CostLogger(), [], [], (None, None)
    if todo:
        load_embedder(index.embed, logger)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as handle:
        for row in todo:
            base = {key: row[key] for key in ("qid", "pdf", "kind", "question", "gold")}
            try:
                if current[0] != row["pdf"]:  # one open index at a time; questions come grouped by PDF
                    if not cached_folder(row["pdf"], cache_root):
                        raise LookupError(f"no complete AT4-KN01 index in {project_path(cache_root)}")
                    current = (row["pdf"], open_index(row["pdf"], logger, run_id, False, None, cache_root, index.embed))
                result = ask_index(current[1], row["question"], logger, BUDGET, context_only=True)
                line = {**base, "context": result["context"], "tokens_read": result["tokens_read"],
                        "chunk_ids": [source["chunk_id"] for source in result["sources"]]}
                done.append(row["qid"])
            except Exception as error:  # a test of the tool: record the step-A failure and go on
                line = {**base, "failure": f"{type(error).__name__}: {error}"}
                failures.append({"qid": row["qid"], "reason": line["failure"]})
            append_line(handle, line)
    stack = {"agent_mode": "test4_contexts", "parser_mode": "thorough", "setting": SETTING, "budget": BUDGET,
             "embedder": EMBEDDER, "cache_root": project_path(cache_root), "questions": project_path(questions_file),
             "output": project_path(output), "continues": continues, "started_at": started, "ended_at": now(),
             "skipped_already_saved": len(questions) - len([row for row in questions if row["qid"] not in saved]),
             "qids_done": done, "failures": failures}
    record = write_session(records_dir, run_id, stack, [Path(questions_file)], output, logger.summary(), machine)
    total = len(saved) + len(done) + len(failures)
    print(f"contexts: {len(done)} new, {len(failures)} failed, {stack['skipped_already_saved']} skipped as saved | "
          f"{total} of {len(questions)} saved -> {project_path(output)}\nrun record: {project_path(record)}")


# ---------- step B: answers ----------

class GeminiCaller:
    """gemini-a only, paced one start every INTERVAL seconds; thinking off, or the lowest level if off is refused."""

    def __init__(self, spec, sleep, clock):
        self.entry = providers.named_entry(spec["entry"])
        if self.entry["model"] != spec["model"] or self.entry["provider"] != "gemini":
            raise SystemExit(f"entry {spec['entry']} is {self.entry['provider']}/{self.entry['model']}, not gemini/{spec['model']}")
        self.choices, self.sleep, self.clock, self.last_start = list(spec["thinking"]), sleep, clock, None
        self.fallback_reason, self.accepted = None, False

    def settings(self):
        return {"max_output_tokens": MAX_OUTPUT_TOKENS, "thinking_config": self.choices[0]}

    def info(self):
        return {"entry": self.entry["name"], "provider": "gemini", "model": self.entry["model"], "temperature": 0,
                "max_output_tokens": MAX_OUTPUT_TOKENS, "thinking_sent": self.choices[0],
                "thinking_fallback_reason": self.fallback_reason, "paced_seconds": round(INTERVAL, 3)}

    def __call__(self, prompt):
        if self.last_start is not None:
            self.sleep(max(0.0, self.last_start + INTERVAL - self.clock()))
        self.last_start = self.clock()
        try:
            reply = providers.ask_entry(self.entry, prompt, self.settings())
        except providers.ProviderError as error:
            # Gemini's 400 does not name the field; before any call is accepted it is taken as the thinking setting
            # being refused (the other fields are those aq_run and providers already send), and the next one is tried.
            if self.accepted or "INVALID_ARGUMENT" not in str(error) or len(self.choices) == 1:
                raise
            self.fallback_reason = f"{self.choices.pop(0)} refused: {str(error)[-160:]}"
            return self(prompt)
        self.accepted = True
        return reply


class QwenCaller:
    """qwen2.5:3b through the Ollama adapter, local, not paced."""

    def __init__(self, spec):
        self.options, self.model = spec["options"], providers.ollama_model(spec["model"])

    def info(self):
        return {"provider": "ollama", **self.model, "options": self.options}

    def settings(self):
        return self.options

    def __call__(self, prompt):
        return providers.ask_ollama(self.model["tag"], prompt, self.options)


def answer_with_retries(caller, prompt, sleep):
    """(reply, tries, seconds of the answering call) or (None, tries, reason). RateLimit passes through (stops)."""
    reason = None
    for attempt in range(1, TRIES + 1):
        start = time.monotonic()
        try:
            return caller(prompt), attempt, round(time.monotonic() - start, 3)
        except providers.RateLimit:
            raise
        except Exception as error:
            reason = f"{type(error).__name__}: {error}" if str(error) else type(error).__name__
            if attempt < TRIES:
                sleep(ERROR_WAIT)
    return None, TRIES, reason


def answers(model_key, questions_file, output_dir, records_dir, machine, limit=None, sleep=time.sleep,
            clock=time.monotonic):
    spec = MODELS[model_key]
    questions = read_questions(questions_file)
    context_lines = {line["qid"]: line for line in read_lines(Path(output_dir) / CONTEXTS)}
    missing = [row["qid"] for row in questions if row["qid"] not in context_lines]
    if missing:
        raise SystemExit(f"step A is not finished: {len(missing)} qids have no context or step-A failure; run contexts first")
    output = Path(output_dir) / spec["file"]
    saved = {line["qid"] for line in read_lines(output)}
    answerable = [context_lines[row["qid"]] for row in questions if "context" in context_lines[row["qid"]]]
    todo = [line for line in answerable if line["qid"] not in saved][:limit]
    run_id, started = session_id(records_dir), now()
    continues = previous_session(records_dir, f"test4_answers_{model_key}", output)
    caller = GeminiCaller(spec, sleep, clock) if model_key == "gemini" else QwenCaller(spec)
    done, failures, stopped = [], [], None
    with output.open("a", encoding="utf-8") as handle:
        for line in todo:
            prompt = ANSWER_PROMPT.format(context=line["context"], question=line["question"])  # never the gold
            try:
                reply, tries, detail = answer_with_retries(caller, prompt, sleep)
            except providers.RateLimit as limit:  # quota or rate limit: nothing saved for this qid; stop the session
                stopped = f"{limit.kind} rate limit at qid {line['qid']}"
                break
            base = {"qid": line["qid"], "pdf": line["pdf"], "kind": line["kind"], "model": spec["model"],
                    "settings": caller.settings(), "tries": tries}
            if reply is None:
                failures.append({"qid": line["qid"], "reason": detail})
                append_line(handle, {**base, "failure": detail})
            else:
                done.append(line["qid"])
                append_line(handle, {**base, **reply, "answer_seconds": detail})
    stack = {"agent_mode": f"test4_answers_{model_key}", "llm": caller.info(), "answer_prompt": ANSWER_PROMPT,
             "contexts": project_path(Path(output_dir) / CONTEXTS), "questions": project_path(questions_file),
             "output": project_path(output), "continues": continues, "started_at": started, "ended_at": now(),
             "skipped_already_saved": len(answerable) - len([line for line in answerable if line["qid"] not in saved]),
             "skipped_step_a_failures": len(questions) - len(answerable), "qids_done": done, "failures": failures,
             "stopped": stopped, "bge_m3_loaded": "sentence_transformers" in sys.modules}
    record = write_session(records_dir, run_id, stack, [Path(questions_file), Path(output_dir) / CONTEXTS], output,
                           {}, machine)
    print(f"answers {spec['model']}: {len(done)} new, {len(failures)} failed, {stack['skipped_already_saved']} skipped "
          f"as saved{f' | stopped: {stopped}' if stopped else ''} | {len(saved) + len(done) + len(failures)} of "
          f"{len(answerable)} saved -> {project_path(output)}\nrun record: {project_path(record)}")


# ---------- summary ----------

TOKEN_FIELDS = {"gemini": ("input_tokens", "output_tokens", "thinking_tokens"), "qwen": ("input_tokens", "output_tokens")}


def token_summary(lines, fields):
    """Totals and median per answer of each count the model's responses reported (answered qids only; a count the
    response did not give is left out and counted as missing, never estimated)."""
    answered = [line for line in lines if "answer" in line]
    summary = {"answers": len(answered)}
    for field in fields:
        counts = pd.Series([line.get(field) for line in answered], dtype="float")
        summary[field] = {"total": int(counts.sum()), "median_per_answer": counts.median() if counts.notna().any() else None,
                          "answers_with_count": int(counts.notna().sum())}
    return summary


def summary(output_dir):
    """llm_summary.json: token counts per model, from the counts saved with each answer."""
    path = Path(output_dir) / "llm_summary.json"
    result = {"tokens": {spec["model"]: token_summary(read_lines(Path(output_dir) / spec["file"]), TOKEN_FIELDS[key])
                         for key, spec in MODELS.items()}}
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result["tokens"]), f"\n-> {project_path(path)}")


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    arg_parser.add_argument("step", choices=("contexts", "answers", "summary"))
    arg_parser.add_argument("--model", choices=tuple(MODELS), help="answers step: which model")
    arg_parser.add_argument("--questions", default=str(QUESTIONS))
    arg_parser.add_argument("--output-dir", default=str(OUTPUT))
    arg_parser.add_argument("--cache-root", default=str(CACHE), help="contexts step: the AT4-KN01 index cache")
    arg_parser.add_argument("--records-dir", default=str(RUNS_DIR), help="runs/ (default) or runs/tests/ for tests")
    arg_parser.add_argument("--limit", type=int, help="at most this many new qids this session (tests)")
    arg_parser.add_argument("--machine", default="laptop")
    args = arg_parser.parse_args()
    if args.step == "contexts":
        contexts(Path(args.questions), Path(args.output_dir), Path(args.cache_root), Path(args.records_dir),
                 args.machine, args.limit)
    elif args.step == "summary":
        summary(Path(args.output_dir))
    elif args.model is None:
        arg_parser.error("answers needs --model")
    else:
        answers(args.model, Path(args.questions), Path(args.output_dir), Path(args.records_dir), args.machine, args.limit)


if __name__ == "__main__":
    main()
