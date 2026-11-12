# Project rules for Claude Code

## Research integrity (never break these)
- The held-out PDFs are sealed. Never run any script with `--final`, and never read files of documents whose split is
  not `tuning` in pdfs/split.csv, unless I explicitly ask in this session.
- Never change `scorer_v1` (src/eval/score.py), the frozen spec decisions in spec/spec_v1.2.md, or any frozen chunker
  version without telling me first. Any change to a frozen part needs a new version and a spec note.
- Never delete or overwrite run records (runs/). Test runs go to runs/tests/ with a clear name.
- Spec first: before a new experiment, write its design into spec/spec_v1.2.md, then the code.
- No hand-tuned rules, word lists or thresholds that only fit our test questions; only general, data-driven rules.

## Code style
- Short, clean code; comprehensions welcome; clear names; never `_` throwaway variables.
- Run scripts as modules from the repo root: `python -m scripts.<name>`.
- Prefer reusing existing functions (scorer, P1 gold rules, p4_analyse) over rewriting them.

## Git
- Do not commit or push. Stage nothing. I review the diff and commit myself.
- At the end of each task, show the diff summary and the command output.

## Keys and secrets
- Never print, log or commit API keys. The Gemini key lives in ~/.config/gemini/api_key; read it only through src/chunk/llm.py.