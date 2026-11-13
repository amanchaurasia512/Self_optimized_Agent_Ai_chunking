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
  model gemini-3.5-flash-lite. The API key is read through src/chunk/llm.py (~/.config/gemini/api_key), as
  CLAUDE.md requires; deployment key handling belongs to the app spec. The model can be swapped.

## Parser choice
Scan detection is automatic per page. The parser for digital pages is a user setting: thorough (default) uses the
Docling setup above, docling/method1_tree_T384_noprefix; fast (--fast) uses the pdfplumber setup above,
pdfplumber/method1_tree_T384_noprefix, which loses more answer text (held-out 27.6% vs 16.3% of questions). The
agent does not pick the parser per document: P4 found per-document choice no better than one fixed setup.

## Modes
- chunk: `python -m src.agent chunk <pdf> -o <chunks.json> [--fast]`
- ask: `python -m src.agent ask <pdf> "<question>" [--budget 1250] [--fast]`
  The index is built once per file and cached by SHA-256; later questions reuse it.

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
