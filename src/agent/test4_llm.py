"""Agent test 4, LLM comparison (spec v1.2 note "Agent test 4: LLM comparison, design before running", 2026-11-23).
Step A saves each question's retrieved context (thorough mode, budget 1,250, the AT4-KN01 index, no LLM call); step B
answers from the saved contexts only, with gemini-3.5-flash-lite (entry gemini-a only, paced) or qwen2.5:3b (Ollama,
local). --chunker picks the index (spec v1.2 "Agent test 4, run 2", 2026-11-26): method1_tree_T384_noprefix (run 1,
the default) or langchain_recursive_size256_overlap0_noprefix (run 2: chunked from run 1's saved Docling extractions,
outputs in data/agent_test4/run2_<setting>/). Both steps append one JSON line per qid and skip qids already saved, so a restart goes on where it stopped.
One run record per session, naming the previous session's record in continues. A test of the tool, not a research
claim: no study document is used (sealed study PDFs are refused), so no --final gate. Steps, from the repo root:
    .venv-docling/bin/python -m src.agent.test4_llm contexts [--chunker langchain_recursive_size256_overlap0_noprefix]
    .venv/bin/python -m src.agent.test4_llm answers --model gemini
    .venv/bin/python -m src.agent.test4_llm answers --model qwen
    .venv/bin/python -m src.agent.test4_llm summary      measures and token counts -> llm_summary.json, llm_pairs.csv
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

import numpy as np
import pandas as pd

from scripts.aq_run import ANSWER_PROMPT, INTERVAL, contained, token_f1
from scripts.p4_analyse import resampled_means
from scripts.rq5_parser_compare import holm
from src.agent import providers
from src.agent.pipeline import SETUPS, SPEC
from src.common import manifest
from src.common.manifest import RUNS_DIR, project_path
from src.common.paths import DATA
from src.eval.stats import LEVEL, RESAMPLES, SEED

BUDGET = 1250
OUTPUT = DATA / "agent_test4"
QUESTIONS, CACHE = OUTPUT / "questions.csv", OUTPUT / "cache"
CONTEXTS = "contexts.jsonl"
RUN1_SETTING = "method1_tree_T384_noprefix"  # the AT4-KN01 index (src/agent/ask.SETTING until 2026-11-24)
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


def run_dir(setting):
    """data/agent_test4 for run 1; data/agent_test4/run2_<setting> for run 2, so run 1's files are never touched."""
    return OUTPUT if setting == RUN1_SETTING else OUTPUT / f"run2_{setting}"


def saved_extraction(pdf, setting):
    """Run 2 chunks run 1's saved thorough-mode Docling extraction (no new parsing); run 1 parses (None)."""
    return None if setting == RUN1_SETTING else CACHE / manifest.file_sha256(pdf) / f"docling_{RUN1_SETTING}" / "extraction.json"


# ---------- step A: contexts ----------

def cached_folder(pdf, cache_root, setting=RUN1_SETTING):
    """This PDF's index folder of the setting when it is complete and current; None otherwise (never rebuilt here)."""
    from src.agent import index
    from src.agent.pipeline import chunker_info
    planned = {"parser": "docling", "pdf_sha": manifest.file_sha256(pdf), "from_extraction": saved_extraction(pdf, setting)}
    folder = index.index_folder(planned, setting, cache_root)
    return folder if index.cached_index(folder, "docling", chunker_info(setting)) else None


def contexts(questions_file, output_dir, cache_root, records_dir, machine, limit=None, setting=RUN1_SETTING):
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
                    if not cached_folder(row["pdf"], cache_root, setting):
                        raise LookupError(f"no complete {setting} index in {project_path(cache_root)}")
                    current = (row["pdf"], open_index(row["pdf"], logger, run_id, False, saved_extraction(row["pdf"], setting),
                                                      cache_root, index.embed, setting))
                result = ask_index(current[1], row["question"], logger, BUDGET, context_only=True)
                line = {**base, "context": result["context"], "tokens_read": result["tokens_read"],
                        "chunk_ids": [source["chunk_id"] for source in result["sources"]]}
                done.append(row["qid"])
            except Exception as error:  # a test of the tool: record the step-A failure and go on
                line = {**base, "failure": f"{type(error).__name__}: {error}"}
                failures.append({"qid": row["qid"], "reason": line["failure"]})
            append_line(handle, line)
    stack = {"agent_mode": "test4_contexts", "parser_mode": "thorough", "setting": setting, "budget": BUDGET,
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


KINDS = ("digital", "scanned")


def answered_models(output_dir):
    """The models with an answer file in output_dir (run 2 has no qwen2.5:3b answers)."""
    return {key: spec for key, spec in MODELS.items() if (Path(output_dir) / spec["file"]).exists()}


def pairs_table(output_dir):
    """One row per qid with a context: context-contained, and per model F1, answer-contained, not found, seconds
    (empty where the model has no answer)."""
    rows = {line["qid"]: {"qid": line["qid"], "pdf": line["pdf"], "kind": line["kind"],
                          "context_contained": contained(line["context"], line["gold"]), "gold": line["gold"]}
            for line in read_lines(Path(output_dir) / CONTEXTS) if "context" in line}
    for key, spec in answered_models(output_dir).items():
        for line in read_lines(Path(output_dir) / spec["file"]):
            if "answer" in line:
                gold = rows[line["qid"]]["gold"]
                rows[line["qid"]].update({f"f1_{key}": token_f1(line["answer"], gold),
                                          f"contained_{key}": contained(line["answer"], gold),
                                          f"not_found_{key}": line["answer"].strip().lower().startswith("not found"),
                                          f"answer_seconds_{key}": line["answer_seconds"]})
    return pd.DataFrame(rows.values()).drop(columns="gold")


def document_mean(frame, column):
    """Question values averaged per document first, then over documents."""
    return round(float(frame.dropna(subset=[column]).groupby("pdf")[column].mean().mean()), 3)


def paired_difference(frame):
    """Paired document bootstrap of F1 Gemini minus qwen2.5:3b over qids both answered: mean, 95% CI, two-sided p."""
    both = frame.dropna(subset=["f1_gemini", "f1_qwen"])
    difference = both.assign(difference=both["f1_gemini"] - both["f1_qwen"]).groupby("pdf")["difference"].mean()
    means = resampled_means(difference.to_numpy()[:, None], np.random.default_rng(SEED))[:, 0]
    low, high = np.quantile(means, [(1 - LEVEL) / 2, (1 + LEVEL) / 2])
    return {"documents": len(difference), "questions": len(both), "difference": round(float(difference.mean()), 3),
            "low": round(float(low), 3), "high": round(float(high), 3),
            "p": float(min(1.0, 2 * min((means <= 0).mean(), (means >= 0).mean())))}


def failures(lines):
    return {"count": sum("failure" in line for line in lines),
            "reasons": [{"qid": line["qid"], "reason": line["failure"]} for line in lines if "failure" in line]}


def summary(output_dir):
    """llm_summary.json (spec note "Agent test 4: LLM comparison", measures and token counts) and llm_pairs.csv."""
    output_dir = Path(output_dir)
    pairs = pairs_table(output_dir)
    pairs.to_csv(output_dir / "llm_pairs.csv", index=False)
    kinds = {kind: pairs[pairs["kind"] == kind] for kind in KINDS}
    models = answered_models(output_dir)
    comparison = None
    if len(models) == len(MODELS):
        comparison = {kind: paired_difference(frame) for kind, frame in kinds.items()}
        for kind, holm_p in zip(KINDS, holm(np.array([comparison[kind]["p"] for kind in KINDS]))):
            comparison[kind]["holm_p"] = float(holm_p)
    answer_lines = {key: read_lines(output_dir / spec["file"]) for key, spec in models.items()}
    result = {
        "context_contained": {kind: document_mean(frame, "context_contained") for kind, frame in kinds.items()},
        "models": {spec["model"]: {
            **{kind: {"questions": int(frame[f"f1_{key}"].notna().sum()), "f1": document_mean(frame, f"f1_{key}"),
                      "answer_contained": document_mean(frame, f"contained_{key}"),
                      "not_found": document_mean(frame, f"not_found_{key}")} for kind, frame in kinds.items()},
            "step_b_failures": failures(answer_lines[key]),
            "answer_seconds": {"median": float(pairs[f"answer_seconds_{key}"].median()),
                               "iqr": [float(pairs[f"answer_seconds_{key}"].quantile(quantile)) for quantile in (0.25, 0.75)]}}
            for key, spec in models.items()},
        "f1_gemini_minus_qwen": comparison and {"resamples": RESAMPLES, "seed": SEED, "level": LEVEL, **comparison},
        "step_a_failures": failures(read_lines(output_dir / CONTEXTS)),
        "tokens": {spec["model"]: token_summary(answer_lines[key], TOKEN_FIELDS[key]) for key, spec in models.items()}}
    (output_dir / "llm_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "tokens"}),
          f"\n-> {project_path(output_dir / 'llm_summary.json')}, {project_path(output_dir / 'llm_pairs.csv')}")


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    arg_parser.add_argument("step", choices=("contexts", "answers", "summary"))
    arg_parser.add_argument("--model", choices=tuple(MODELS), help="answers step: which model")
    arg_parser.add_argument("--questions", default=str(QUESTIONS))
    arg_parser.add_argument("--chunker", default=RUN1_SETTING, choices=tuple(SETUPS),
                            help="index setting: run 1 (default) or run 2; sets the default output dir")
    arg_parser.add_argument("--output-dir", help="default data/agent_test4 (run 1) or data/agent_test4/run2_<setting>")
    arg_parser.add_argument("--cache-root", default=str(CACHE), help="contexts step: the index cache")
    arg_parser.add_argument("--records-dir", default=str(RUNS_DIR), help="runs/ (default) or runs/tests/ for tests")
    arg_parser.add_argument("--limit", type=int, help="at most this many new qids this session (tests)")
    arg_parser.add_argument("--machine", default="laptop")
    args = arg_parser.parse_args()
    output_dir = Path(args.output_dir or run_dir(args.chunker))
    if args.step == "contexts":
        contexts(Path(args.questions), output_dir, Path(args.cache_root), Path(args.records_dir), args.machine, args.limit,
                 args.chunker)
    elif args.step == "summary":
        summary(output_dir)
    elif args.model is None:
        arg_parser.error("answers needs --model")
    else:
        answers(args.model, Path(args.questions), output_dir, Path(args.records_dir), args.machine, args.limit)


if __name__ == "__main__":
    main()
