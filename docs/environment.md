# Environment: package versions per stage

Every value below is copied from the run records in `runs/*.json` (fields `environment.python`, `stack.parser`,
`stack.tokenizer`, `stack.embedder`, `stack.chunker.version`, `stack.llm`). Run records are never edited; where a
record does not store a version, the table says **not recorded**. Compiled on 2026-11-12 from 247 run records.

Two machines are involved:
- **Kaggle** (`environment.machine` = `kaggle`, `kaggle-cpu`, `kaggle-gpu-t4`, `kaggle-gpu-t4x2`): Docling extraction,
  most chunking, and GPU embedding. Python 3.13.15 (runs up to 2026-11-02) and 3.13.16 (from 2026-11-03).
- **Laptop** (`laptop`): pdfplumber and LlamaParse extraction, some chunking, CPU embedding, all scoring and
  analysis. Python 3.14.4 in every laptop record.

## P1: extraction

| Parser | Version (from records) | Runs | Machine, Python |
|---|---|---|---|
| Docling | 2.143.0 | P1-KN02-20261027-1, P1-KN06-20261029-1, P1-KN07/08/09-20261030-1 | Kaggle, 3.13.15 |
| Docling | **2.144.0** | P1-KN04-20261028-1 (15 OHR PDFs) | Kaggle, 3.13.15 |
| Docling | 2.143.0 | P1-P2-KN02-20261103-1 (18 held-out PDFs) | Kaggle, 3.13.16 |
| Docling (RQ5a variants) | 2.143.0 | P1-RQ5-KN01-20261109-1 … -7 | Kaggle, 3.13.16 |
| pdfplumber | 0.11.10 | P0-LOCAL, P1-LOCAL | laptop, 3.14.4 |
| LlamaParse | SDK 2.19.0, parse version "latest" | 3 of the P1-LOCAL records | laptop, 3.14.4 |

- P1-KN04 is the only record with Docling 2.144.0. All 25 tuning extractions in `data/extracted/docling/` record
  2.143.0 in their own `parser.version` field, so the 2.144.0 output is not among the tuning extractions (P1-KN06
  re-extracted 38 PDFs with 2.143.0). The spec's "pinned Docling setup" (H4) refers to P1-KN06.
- Docling is not installed in the local venv and is not in `requirements.txt`; every Docling run is a Kaggle run.
- "parse version latest" for LlamaParse is not a fixed version.

## P2: chunking

| Component | Version (from records) | Runs |
|---|---|---|
| Tokenizer | BAAI/bge-m3, revision `5617a9f61b028005a4858fdac845db406aefb181` | every chunking record (192) and P0-LOCAL |
| langchain-text-splitters | 1.1.3 (inside chunker version `1.0+langchain-text-splitters-1.1.3`) | langchain_recursive, langchain_default |
| adaptive-chunking | commit `ea87ce8` (inside chunker version) | recursive, sentence, semantic, llm_regex |
| stanza | 1.15.0 (inside chunker version) | sentence |
| langchain-experimental | 0.4.2 (inside chunker version) | semantic |
| Semantic-chunker embedder | qwen3-emb-0.6b, revision `97b0c61`, fp32 (inside chunker version) | semantic (P2-KN01, P2-P2-KN03) |
| Own method 1 | 1.0+tree-v4 → 1.1 (+A13) → 1.2 (+A9 whole-prefix) | method1_tree |
| LLM for llm_regex | gemini-3.5-flash-lite (`stack.llm.model`) | 9 llm_regex records (P2-LOCAL, P2-P2-KN03, P2-P4-KN01; 3 each) |

Machines: Kaggle (P2-KN01, P2-P2-KN03/04, P2-P3-KN02/03/04, P2-P4-KN01, P2-RQ5-KN01; Python 3.13.15 / 3.13.16) and
laptop (P2-LOCAL; Python 3.14.4).

## P3: embedding

| Component | Version (from records) | Runs |
|---|---|---|
| Embedder | BAAI/bge-m3, revision `5617a9f61b028005a4858fdac845db406aefb181`, float32, normalised, max_length 8192, dim 1024 | 19 records |
| Device | cuda | P3-KN01…04, P3-P4-KN01, P3-RQ5-KN01 (Kaggle, 3.13.16) |
| Device | cpu | P3-LOCAL-20261106-1, -20261106-2, -20261110-1, -20261111-1 (laptop, 3.14.4) |

## P3 scoring, P4, RQ5 analysis, gap checks

Laptop, Python 3.14.4. Scorer `scorer_v1` (`stack.scorer.version`; two earlier records say `scorer_v1-dev`, which are
development runs). Embedder revision as above. Records: P3-LOCAL-20261105-*, P3-FINAL-20261106-1, P3-RQ5D-20261110-1,
P3-RQ5S-20261111-1, P3-FIXEDK-20261112-1, P4-LOCAL-20261105-1, P4-FINAL-20261106-1, P5-LOCAL-*.

## AQ: answer quality

| Component | Version | Source |
|---|---|---|
| Answering LLM | gemini-3.5-flash-lite | P6-LOCAL-20261110-1/2/3 (`stack.llm`), laptop, 3.14.4 |
| Judge | Qwen3-8B, 4-bit, greedy, on Kaggle | **no run record**; the spec says the weights revision is in the run output, which is not in `runs/` |

## Not recorded in any run record

- **torch**: not recorded.
- **sentence-transformers**: not recorded.
- **transformers, tokenizers**: not recorded.
- **CUDA / GPU driver**: not recorded (only the machine label, e.g. `kaggle-gpu-t4`).

`requirements.txt` (the laptop venv) pins torch 2.15.0, sentence-transformers 6.2.0, transformers 5.22.1,
tokenizers 0.23.3, pdfplumber 0.11.10, langchain-text-splitters 1.1.3, langchain-experimental 0.4.2, stanza 1.15.0
and llama_cloud 2.19.0. Those pins describe the laptop at the time the file was written; they are not evidence of what
ran on Kaggle.

## Future runs

From 2026-11-12, `src/common/manifest.py` (`build_manifest`) writes `environment.packages` into every new run record.
It holds the installed versions of docling, pdfplumber, torch, sentence-transformers, transformers,
langchain-text-splitters, pandas and numpy, with null for a package that is not installed (e.g. docling on the laptop).
The first records with this block are P3-GOLDDROP-20261112-1 and P3-SIZESRC-20261112-1. Records written before that
date are unchanged and have no `packages` block. Kaggle notebooks pick up the change only when they run the updated
`manifest.py`.
