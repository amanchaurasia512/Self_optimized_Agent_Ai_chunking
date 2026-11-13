# Agent spec v1 (2026-11-13)

## Purpose
A tool that takes any PDF and either (1) returns a chunk.json ready for a RAG index, or (2) answers questions about
the PDF. Its defaults come from the study (spec/spec_v1.2.md, RESULTS.md). It does not tune itself per document:
the study found per-document choice gives no gain on held-out (P4-FINAL-20261106-1: NO-GO).

## What "self-optimised" means here
The agent adapts where the study showed it matters, and fixes what the study showed does not:
- Adapts: scan detection per page. Pages without a text layer go through OCR; pages with one do not
  (RQ5: scan detection is the decisive parser choice; pdfplumber reads nothing from scans).
- Adapts: the reading budget. Retrieval reads ranked chunks until a token budget is filled; the budget can be set
  per question.
- Fixed: parser settings (RQ5a: no variant beats the default) and chunk size (256-384 tokens best at a fixed
  budget, within every source with enough documents).

## Defaults
- Parser: Docling default (Auto OCR on bitmap pages), version as in docs/environment.md. Same recall as pdfplumber
  on shared questions, but it keeps far more answer text (held-out loss 16.3% vs 27.6%) and reads scans.
- Chunker: method1_tree T384, no prefix. Thorough (default): docling/method1_tree_T384_noprefix (0.752, statistically
  tied with the best on held-out, P4-FINAL-20261106-1). Fast: pdfplumber/method1_tree_T384_noprefix, the study's best
  single setup (0.772).
- Tokenizer and embedder: bge-m3, same revision as the study (src/chunk/base.py).
- Retrieval: hybrid BM25 + bge-m3, reciprocal rank fusion k = 60 (scorer_v1), reading by token budget
  (read_ranking). Default budget 1,250 tokens; allowed 750 / 1,250 / 2,000.
- Answering (ask mode only): the AQ answer prompt (answers only from the retrieved text, "not found" when absent),
  default model gemini-3.5-flash-lite. Providers, models and keys come from the answer-provider list (see Answer
  providers); keys are read only through src/agent/providers.py. src/chunk/llm.py stays the study's client.
  Deployment key handling belongs to the app spec.

## Answer providers (added 2026-11-13, Part B prerequisite)
- List: ~/.config/pdf-agent/providers.json, an ordered list of entries {name, provider (gemini or groq), model,
  key_file}. Example with placeholder paths: docs/providers.example.json. Keys are read only from key_file, at call
  time, and are never printed, logged or stored; error messages are checked for the key text and redacted.
- Prompt: the AQ answer prompt (scripts/aq_run.ANSWER_PROMPT), imported unchanged. Temperature 0.
- Order: entries are tried in list order; an entry marked exhausted is skipped until its reset.
- Daily limit (a 429 whose quota or message says "per day", as in aq_run's paced()): the entry is marked exhausted
  in ~/.config/pdf-agent/state.json until its reset (now + the provider's retry delay when given, else the next
  midnight US Pacific), and the next entry is tried. state.json holds entry names and reset times only.
- Per-minute limit (any other 429) or overload (503): wait and retry the same entry, using the provider's retry
  delay when given, else 15 / 30 / 60 / 120 / 240 s (as src/chunk/llm.py); after the last wait, try the next entry
  without marking this one exhausted.
- Any other error (e.g. a rejected key): stop with a message naming the entry and its key_file path, not the key.
- All entries exhausted or rate-limited: stop with a message listing each entry and its reset time.
- Result: the answer plus the entry name, provider and model, recorded in the ask run record.
- Transport: Gemini through google-genai; Groq through its OpenAI-compatible HTTP API (httpx), no extra SDK.

## Parser choice
Scan detection is automatic per page. The parser for digital pages is a user setting: thorough (default) uses the
Docling setup above, docling/method1_tree_T384_noprefix; fast (--fast) uses the pdfplumber setup above,
pdfplumber/method1_tree_T384_noprefix, which loses more answer text (held-out 27.6% vs 16.3% of questions). The
agent does not pick the parser per document: P4 found per-document choice no better than one fixed setup.

Scan rule (added 2026-11-13): a page has no text layer when pdfplumber finds no characters on it. In fast mode, if
any page has no text layer, the whole document goes to Docling (pdfplumber reads nothing from scans), and the reason
is recorded. Every run record stores the parser used, the reason, the page count and the numbers of the pages
without a text layer. --from-extraction starts from an existing extraction file instead of parsing (tests and
reproduction): the parser and doc_id come from that file, and the source fields come from pdfs/catalog.csv when the
document is catalogued (as in the study), otherwise from the PDF's file name and SHA-256.

## Modes
- chunk: `python -m src.agent chunk <pdf> -o <chunks.json> [--fast]`
- ask: `python -m src.agent ask <pdf> "<question>" [--budget 750|1250|2000] [--fast] [--from-extraction <file>]
  [--context-only] [--record-text]`
  The index is built once per file and cached by SHA-256; later questions reuse it.
- providers: `python -m src.agent providers add --name <name> --provider gemini|groq --model <model>` asks for the
  key with hidden input, saves it to ~/.config/pdf-agent/keys/<name> (owner-only) and appends the entry to
  providers.json; `providers list` shows names, models and status, never keys.

## Ask mode (Part B, added 2026-11-13)
- Index cache: data/agent_cache/<PDF SHA-256>/<parser>_method1_tree_T384_noprefix/ (a from-extraction index gets
  its own folder, suffixed with the extraction file's hash): extraction.json (the document text the chunk offsets
  point into), chunks.json (the chunk.json), the bge-m3 vectors saved with src/eval/embed.save_part (its
  embedder.json check refuses another embedder), and index.json (parser and version, chunker, tokenizer, embedder).
  In fast mode the scan check runs first, so the cache is keyed by the parser actually used; its result is
  cached per PDF (<SHA-256>/scan.json), so later questions skip it. A cache whose
  index.json does not match the current chunker, tokenizer, embedder or installed parser version is rebuilt.
- Embedding: as scripts/p3_embed.py (bge-m3 pinned revision, float32, normalised, max length 8,192, batch 16;
  CUDA when available, else CPU). On a cache hit only the question is embedded.
- Retrieval: exactly as scripts/aq_run.contexts: scripts/p3_score.load_chunks, BM25 on prefix + text, dense cosine,
  hybrid_ranking (RRF k = 60), read_ranking within the budget; the context is the read parts joined by blank lines.
  Budgets: 750, 1,250 (default) or 2,000 only.
- Answer: src/agent/providers.answer (see Answer providers); --context-only stops before any API call.
- Output: the answer, the chunks read (ids and pages) and the provider entry and model.
- Run record (one per ask): mode, parser and reason, pages and pages without text, cache hit, budget, tokens read,
  chunks read (ids and pages), provider entry and model, time and peak memory per step (scan_check, load_index or
  parse / chunk / embed, retrieve, answer), package versions. The question and answer are stored as SHA-256 and
  length only; their text only with --record-text (run records are committed; PDFs may be private).

## chunk.json
chunk.json follows spec/chunk.schema.json unchanged, the same format as the study's chunk files (every chunk has
pages). Agent-only facts (pages OCR'd, step timings, parser mode) go in the run record, not in chunk.json.

## Performance (measure first, change only what keeps output the same)
- Every run records time per step (parse, chunk, embed, index, retrieve, answer), peak memory and GPU use.
- Parsing: OCR only on pages without a text layer; among parser settings RQ5(a) found equal in quality, use the
  fastest; layout models on GPU when available.
- Embedding: fp16 on GPU, max length near the chunk size, chunks sorted by length, large batches, dense vectors only.
- Cache: chunks and vectors stored per PDF SHA-256; later questions embed only the question.
- CPU server: int8 bge-m3 (ONNX Runtime) and all cores for parsing.
- Quality guard: a speed change is kept only if, on 3 tuning documents, the top-ranked chunks (or extracted text)
  match the float32 / default output; otherwise it is dropped and recorded.

## Code rules
- New code lives in src/agent/ only. It imports the study's parser, chunker and scorer functions and never modifies
  src/parse, src/chunk or src/eval (scorer_v1 stays frozen).
- No hand-written rules for particular documents or questions.
- Every agent run writes a run record (A-LOCAL-... or A-KAGGLE-...) with package versions and step timings.
- For retrieval, chunk fields are converted to read_ranking's keys the same way as scripts/p3_score.load_chunks.

## Tests
1. Unit (laptop): chunk.json validates against the schema; caching works; the budget is never exceeded.
2. Reproduction (laptop): starting from the study's extraction of 3 tuning documents, agent chunks equal the study's
   docling/method1_tree_T384_noprefix chunk files exactly (and pdfplumber's for --fast).
3. Smoke (laptop, CPU): one short digital PDF end to end, chunk and ask; needs the docling extra:
   pip install -e ".[docling]".
4. Unseen PDFs (Kaggle GPU): 10 new PDFs in no split (digital and scanned, short and long). Record time per page,
   peak memory, pages OCR'd and failures. Before running, write 3 questions per PDF with their answers, then report
   how many the agent finds. A smoke test, not a research claim.
5. Server: repeat test 4's timing on the deployment machine before choosing it.

## Out of scope (v1)
Hindi and other languages; per-document tuning; tables as structured data; user accounts. The app and deployment
(Streamlit, Docker, hosting) get their own spec entry after these tests pass.
