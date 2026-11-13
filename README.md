# Self-optimized agent chunking

A pre-registered study of chunking for retrieval over PDFs, and an agent built on its results. A *setup* is a parser
(Docling or pdfplumber) times a chunker setting (fixed-token, recursive, LangChain, sentence, semantic, LLM-regex,
page, and an own structure-tree method). Every setup is scored with one frozen retrieval scorer, so the only thing
that changes between setups is how the text was extracted and cut.

All decisions are written into the spec before they are run: `spec/spec_v1.md` (frozen 2026-10-26),
`spec/spec_v1.1.md` (chunker pool, oracle, cost) and `spec/spec_v1.2.md` (held-out sets, scorer, analysis rules,
RQ5, answer-quality check, corrections and results). The agent has its own spec, `spec/agent_v1.md`.
**When this README and the spec disagree, the spec wins.**

## Research questions

RQ1 is the study's main question and RQ5 is numbered as in the spec. RQ1-RQ4 are labels added on 2026-11-13 for work
already done (see the spec note "Question numbering"); the "planned" column says when each was designed.

| | Question | Planned | Answer | Details |
|---|---|---|---|---|
| RQ1 | How much retrieval quality is lost by using one fixed parse-and-chunk setup per PDF, and how much can choosing per document recover without questions? | before held-out | Nothing is recovered: oracle minus best single setup is -0.007 [-0.045, 0.023], so per-document choice is NO-GO; use one fixed setup (best: pdfplumber/method1_tree_T384, 0.772; 15 of 26 setups tied). | RESULTS.md §1 |
| RQ2 | At a fixed token budget, which chunk size and chunker retrieve best, and does it hold across document sources? | grid before held-out; per source afterwards | Small chunks (about 256-384 tokens). Holds within every tuning source (rho -0.61 to -0.97) and held-out OHR-Bench; weakens on held-out contracts (3 documents). | RESULTS.md §2 |
| RQ3 | Does the evaluation metric change which chunk size looks best? | afterwards (diagnostic) | Yes. With a fixed number of chunks (top 5 or 10), large chunks (about 900-1,000 tokens) look best because they read more text; at an equal token budget small chunks win; Hit@1 and MRR barely separate sizes. | RESULTS.md §7 |
| RQ4 | Do setups that retrieve better also give better answers? | after held-out, design note first | Partly. Answers confirm the large-chunk penalty (fixed_token 1024 is 0.123 token-F1 below the best on held-out, Holm p < 0.01) but do not separate the small-chunk setups (Spearman with recall 0.75 tuning, 0.43 held-out). | RESULTS.md §5 |
| RQ5 | Does tuning improve retrieval: (a) the parser's settings and (b) the chunker's settings, compared with their defaults? | as in the spec | (a) No: no parser variant beats its default on digital or scanned PDFs; detecting scans is the decisive choice. (b) Against LangChain's default size, tuning gains +0.10 to +0.12 recall (Holm p < 0.01); among our own chunkers, nothing beyond the tuned size. | RESULTS.md §3, §2 |

RQ1 is measured as the oracle gap: per-document best setup (split-half cross-fitted) minus the best single setup, on
Recall@1,250 tokens with a 95% document bootstrap interval (spec v1.1, amended in spec v1.2 "P4 analysis rules"); the
go/no-go rule was frozen before the held-out set was opened.

Main metric: Recall@B, the share of gold-answer characters (whitespace ignored) inside the text read from the
ranked chunks within a budget of B tokens (bge-m3 tokenizer), B ∈ {750, 1,250, 2,000}; retrievers BM25, dense
(bge-m3) and hybrid (reciprocal rank fusion). Scorer: `src/eval/score.py`, frozen as `scorer_v1` on 2026-11-05.

Scope: English PDFs (digital and scanned). No Hindi or multilingual claim is made; the Hindi track has no question
source (spec v1.2, "Scope: Hindi").

## The agent

The agent turns the study's results into a tool (`spec/agent_v1.md`). It does not tune itself per document, because
RQ1 found no gain from that. It adapts where the study showed it matters: it detects scanned pages, and it reads
ranked chunks up to a token budget.

| Mode | Parser | Chunker |
|---|---|---|
| thorough (default) | Docling (reads scans, keeps more answer text) | `docling/method1_tree_T384_noprefix` (0.752, tied with the best) |
| fast (`--fast`) | pdfplumber; the whole document goes to Docling if any page has no text layer | `pdfplumber/method1_tree_T384_noprefix` (0.772, the best single setup) |

```bash
python -m src.agent chunk <pdf> -o <chunks.json>            # thorough; needs the Docling environment
python -m src.agent chunk <pdf> -o <chunks.json> --fast     # fast
python -m src.agent chunk <pdf> -o <chunks.json> --from-extraction data/extracted/<parser>/<doc>.json   # tests
python -m pytest tests/agent -v
```

The output follows `spec/chunk.schema.json`, the same format as the study's chunk files. Each run writes a run record
`A-LOCAL-…` with the parser used and why, pages without a text layer, time and peak memory per step, and package
versions. The `ask` mode (RAG question answering) is Part B and not built yet.

Checks so far: for 3 tuning documents × 2 parsers, the agent's chunks equal the study's files exactly; thorough mode on
a laptop CPU reproduces the study's Kaggle GPU extraction exactly; `--fast` on a scanned PDF falls back to Docling.

## Sealed held-out rule

- `pdfs/split.csv` is locked. Documents whose split starts with `held_out` (`held_out`, `held_out_c`,
  `held_out_ood`, `held_out_hindi`) are sealed.
- Scripts read the split file and refuse held-out documents unless run with `--final`. `--final` was used once,
  for the final evaluation (P3-FINAL-20261106-1). **Do not run anything with `--final`** to reproduce tuning
  results; reading the existing held-out score files is the only held-out access needed to reproduce the analyses.
- Any change to a frozen part (scorer, chunker version, spec decision) needs a new version and a spec note.
- Project rules for AI-assisted coding are in `CLAUDE.md`.

## Repository layout

| Path | Contents |
|---|---|
| `spec/` | Frozen specs v1, v1.1, v1.2 (design notes, amendments, results), `agent_v1.md` and `chunk.schema.json` |
| `src/parse/` | Parsers: Docling, pdfplumber, LlamaParse (backup) |
| `src/chunk/` | Shared chunking base, all chunkers (`chunkers.py`), own method 1 (`method1.py`, `tree.py`), LLM client (`llm.py`) |
| `src/gold/` | Gold placement rules (`matching.py`) |
| `src/eval/` | `score.py` (scorer_v1), `embed.py` (bge-m3 cache), `stats.py` (bootstrap settings) |
| `src/common/` | Run records (`manifest.py`), project paths (`paths.py`, for new code), split, catalog, cost logger |
| `src/agent/` | The agent: command line (`__main__.py`) and pipeline (`pipeline.py`) |
| `tests/agent/` | Agent tests: schema, reproduction of the study's chunks, parser-choice rule |
| `scripts/` | One script per step, run as modules (`python -m scripts.<name>`); prefix = stage (p1_…, p2_…, p3_…, p4_…, rq5_…, aq_…) |
| `notebooks/kaggle/` | Kaggle notebooks (Docling extraction, GPU chunking, GPU embedding) |
| `pdfs/` | `split.csv`, `catalog.csv` (paths and SHA-256 of every PDF), held-out, RQ5 and scanned picks |
| `configs/` | Gold drop rule and other locked inputs |
| `runs/` | One JSON run record per run (code commit, stack, environment, input hashes, outputs, costs); `runs/tests/` holds test and dev runs, including `runs/tests/agent/` |
| `docs/` | `kaggle_map.csv` (Kaggle notebook → run id), `environment.md` (package versions per stage and for the agent) |
| `data/` | Git-ignored working data: `raw/`, `extracted/`, `gold/`, `chunks/`, `embeddings/`, `external/`, `results/` (a few result files are force-added), `agent_cache/` |

## Environment

- **Study environment (`.venv`):** Python 3.14.4, `pip install -r requirements.txt`, then `pip install -e .`
  (makes `src` importable from anywhere). Docling is not in it; every Docling extraction in the study ran on Kaggle
  (Docling 2.143.0).
- **Agent / Docling environment (`.venv-docling`):** for the agent's thorough mode. Built with
  `pip install -e . --no-deps`, then `docling==2.143.0` and the packages chunk mode imports. It differs from the
  study environment in 3 packages that Docling needs (huggingface_hub, typer, websockets); the study `.venv` is
  left unchanged.
- See `docs/environment.md` for exact versions. The Gemini key for LLM steps is read only through
  `src/chunk/llm.py` (from `~/.config/gemini/api_key`).

## Reproducing each stage

Every script writes a run record to `runs/`. Run ids follow `P{phase}-{source}-{date}-{n}`, where `source` is
`LOCAL`, a Kaggle notebook id (e.g. `KN03`, `P4-KN01`), or a named run (`FINAL`, `RQ5D`, `RQ5S`, `FIXEDK`). Some
Kaggle chunking runs carry a doubled prefix (e.g. `P2-P2-KN03-…`); these are the real file names and are kept as they
are. The run ids below are the ones the results come from. Use `--help` on any script for all options.

### P1: documents, extraction, gold

```bash
python -m scripts.p1_split                       # tuning / held-out split (already done: pdfs/split.csv is locked)
python -m scripts.p1_extract_pdfplumber          # pdfplumber extraction of every catalogue PDF (never overwrites)
python -m scripts.p1_gold_drop_rule --fit <reviewed sheets>   # fit the drop rule (locked in configs/gold_drop_rule.json)
python -m scripts.p1_gold_match                  # place gold answers in each parser's text -> data/gold/spans_<parser>.jsonl
```

Docling extraction runs on Kaggle (notebooks `p1-kn02`, `p1-kn06`, `p2-kn02`):

```bash
python -m scripts.p1_extract_docling --input <pdf dir> --output data/extracted/docling --run-source <notebook id>
```

### P2: chunking

One call per chunker setting; each writes `data/chunks/<parser>/<setting>/<doc>.json` for both parsers.
Chunker names: `fixed_token`, `page`, `recursive`, `sentence`, `langchain_default`, `langchain_recursive`,
`semantic`, `llm_regex`, `method1_tree`. The full setting grid is in spec v1.1 and spec v1.2 ("Grid extension").

```bash
python -m scripts.p2_chunk --chunker recursive --set size=512 overlap=0
python -m scripts.p2_chunk --chunker method1_tree --set T=256 --heading-prefix
```

Most settings were chunked on Kaggle (notebooks `p2-kn01` … `p4-kn01`, `rq5-kn01`; mapping in `docs/kaggle_map.csv`).

### P3: embedding and scoring

```bash
python -m scripts.p3_embed --name <part name> --machine laptop --run-source LOCAL   # bge-m3 cache (GPU runs: Kaggle p3-kn01…04)
python -m scripts.p3_score                       # every complete setting x both parsers x tuning documents -> P3-LOCAL-20261105-4
python -m scripts.p3_checks --results data/results/p3/<run id>.csv.gz
python -m scripts.p3_sanity --results data/results/p3/<run id>.csv.gz
python -m scripts.p3_hand_check --results data/results/p3/<run id>.csv.gz
```

The held-out scores (P3-FINAL-20261106-1) were made once with `p3_score --final`; do not re-run.

### P4: best single, oracle and gap

```bash
python -m scripts.p4_analyse --run P3-LOCAL-20261105-4 --original-run P3-LOCAL-20261105-2           # tuning
python -m scripts.p4_analyse --run P3-FINAL-20261106-1 --original-run P3-LOCAL-20261105-2 \
    --settings <13 primary settings from spec v1.2>                                                 # held-out: P4-FINAL-20261106-1
```

### RQ5: tuning versus defaults

```bash
# (a) parser settings: pick samples, build scanned PDFs, extract variants, score, compare
python -m scripts.rq5_digital_select
python -m scripts.rq5_scanned_select
python -m scripts.rq5_scanned_build
python -m scripts.p1_extract_pdfplumber --variant layout            # also: tolerance_wide
python -m scripts.p1_extract_docling --input <pdf dir> --output data/extracted/docling_<variant> --variant <variant>   # Kaggle rq5-kn01
python -m scripts.rq5_parser_compare --run P3-RQ5D-20261110-1 --sample digital      # -> P5-LOCAL-20261110-1
python -m scripts.rq5_parser_compare --run P3-RQ5S-20261111-1 --sample scanned      # -> P5-LOCAL-20261112-1
# (b) chunker size: tuned on tuning, tested on the existing held-out scores
python -m scripts.rq5_chunker_compare --tuning-run P3-LOCAL-20261105-4 --heldout-run P3-FINAL-20261106-1   # -> P5-LOCAL-20261110-2
```

Docling variants: `ocr_off`, `table_mode_switched`, `headings`, `replace_broken_text`, `ocr_tesseract`,
`ocr_rapidocr`, `ocr_scale_double`. On the scanned sample `ocr_rapidocr` and `ocr_scale_double` gave text identical
to the default and are not separate settings (spec v1.2, 2026-11-12 correction).

### AQ: answer quality

Stages of one script, in order. `answer` calls gemini-3.5-flash-lite (runs P6-LOCAL-20261110-1…3). The judge
(Qwen3-8B) ran on Kaggle on `judge_jobs.jsonl` and wrote `judgements.jsonl`.

```bash
python -m scripts.aq_run --stage sample
python -m scripts.aq_run --stage answer
python -m scripts.aq_run --stage f1
python -m scripts.aq_run --stage judge-check        # draw 40 cases for the human check
python -m scripts.aq_run --stage label              # label them in the terminal
python -m scripts.aq_run --stage judge-export       # judge prompts for Kaggle
python -m scripts.aq_run --stage judge-check-score  # judge vs human: agreement, kappa
python -m scripts.aq_run --stage analyse            # F1 / contained / judge vs Recall, bootstrap + Holm per set
```

### Gap checks (reporting and diagnostics, 2026-11-12)

```bash
python -m scripts.p3_fixedk                                   # fixed-k recall, Hit@1, MRR, Recall@4,000 on tuning -> P3-FIXEDK-20261112-1
python -m scripts.p3_gold_drop                                # gold drop rate per gold file, split and source (tuning)
python -m scripts.p3_size_by_source --run P3-LOCAL-20261105-4 # size-recall curve within each source (tuning)
```

The held-out versions of `p3_gold_drop` and `p3_size_by_source` read existing scores or gold counts with `--final`
(counts only, after the final evaluation); they were run once and do not need re-running.

## Where results live

| What | Where |
|---|---|
| Run records | `runs/<run id>.json` |
| P3 scores (one row per question, setting, retriever, budget) | `data/results/p3/<run id>.csv.gz` |
| P3 gap checks | `data/results/p3/fixedk_tuning.csv`, `gold_drop_*.csv`, `size_by_source_*.csv` |
| P4 tables | `data/results/p4/<run id>_{primary,original,full}_{setups,documents,left_out}.csv` |
| RQ5 tables | `data/results/rq5/<run id>_{digital,scanned,chunker}.csv` |
| AQ | `data/results/aq/` (sample, answers, F1, judge files, `analysis_<set>.csv`, `analysis_<set>_vs_best.csv`) |
| Agent run records | `runs/tests/agent/A-LOCAL-…json` (test runs); later agent runs in `runs/` |
| Findings | `RESULTS.md` (summary with run ids) and the result notes in `spec/spec_v1.2.md` |