# Spec v1: frozen decisions

- Version: v1
- Date frozen: 2026-10-26
- Rule: changing any line below means a new spec version (v2) and a full re-run. Never change a rule after seeing results unless the reason is written first.

## Environment

| Item | Value |
| --- | --- |
| OS | Ubuntu 26.04.1 LTS |
| Python | 3.14.4 |
| Packages | requirements.txt (pip freeze, 2026-10-26) |

## Tokenizer (the ruler)

| Item | Value |
| --- | --- |
| Model | BAAI/bge-m3 |
| Revision | 5617a9f61b028005a4858fdac845db406aefb181 |
| Library | tokenizers (no torch) |
| Special tokens | Not counted (add_special_tokens=False) |
| Truncation | Never when counting |
| Text counted | Exact chunk text as stored in chunk.json |
| Heading prefix | Counted in budgets when the prefix switch is on; outside the chunk size limit |
| Overlap | Repeated text counted once in budgets |

## Budgets and sizes

| Item | Value |
| --- | --- |
| Token budgets | 750, 1,250 (main), 2,000 (upper bound) |
| Chunk size cap | Max 1,024 tokens (re-split above); merge chunks under 100 |
| Chunks larger than a budget | At 750, compare only chunkers whose chunks fit; at 1,250 and 2,000, all chunkers |

## Embedders and retrievers

| Item | Value |
| --- | --- |
| Main embedder | bge-m3, 1,024 dimensions, no truncation |
| Robustness embedder | nomic-embed-text-v1.5 (search_query / search_document prefixes) |
| Backup embedders | Cohere API (own index, version and date recorded); Qwen3-Embedding-0.6B |
| Retrievers | BM25, dense (bge-m3), hybrid (RRF) |
| Reranker | None in main runs |

## Scoring rules

| Item | Value |
| --- | --- |
| Main metric | Recall@1,250: share of gold-span characters inside the retrieved text |
| Hit@B | Retrieved text overlaps any part of a gold span |
| Full@B | 100% of the gold span inside the retrieved text (spaces and case normalised) |
| Retrieved text | Chunks in rank order until the token budget is full; duplicates counted once |
| Comparison metrics | Hit@5 and Hit@10 (top-k) |
| Tie rule | Clustered bootstrap, 2,000 resamples grouped by document, 95% intervals; overlapping intervals = tie |
| Tie-breaker | Cheaper option wins (fewer index tokens) |
| Key comparisons | Paired test with Holm correction |

## Parsers

| Parser | Role |
| --- | --- |
| Docling | Main |
| pdfplumber | Cheap baseline |
| LlamaParse (OCRia-1) | Paid comparison: scans and complex tables; record mode, credits and date |

## Chunkers

| Chunker | Settings |
| --- | --- |
| Fixed token | Sizes 256, 512, 1,024; overlap 0 |
| Recursive split-then-merge | Target 512; overlap 0, 8, 32, 64 |
| Paragraph group | 2 paragraphs, 1 overlapping |
| Dynamic token size | Range 128 to 512 |
| Page-based | One page per chunk |
| Section + table-aware | One section per chunk; row chunks for tables; no overlap |

All chunkers get the same post-processing (merge under 100, re-split over 1,024). Heading-path prefix is an on/off switch.

## LLMs

| Item | Value |
| --- | --- |
| Agent (live) | Gemini Flash-Lite, then Sarvam, then Groq (fallback order) |
| Research runs | One fixed model per run (to be chosen before P4) |
| Repeats | Code-only chunkers: 1 run; LLM-using parts: 2 to 3 runs |

## Runs

- One complete setup per run; switch one thing at a time; the tokenizer never switches.
- Scope: English main experiment; Hindi/bilingual subset as a separate parallel track.

## Decided by experiment (before the main run)

- Section definition: 2 to 3 candidate rules tried on 1 to 2 tuning PDFs, then frozen here as v1.1.
- Questions per PDF: one universal rule, proportional to length and spread across content types.
