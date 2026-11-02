# Spec v1.1: extended chunker pool, oracle and cost formulas

Date: 2026-11-01. Written before any retrieval result (P3 not started). Everything in spec v1 still holds
unless changed here.

## Reason
The oracle gap (best setup per PDF minus best single setup) is limited by the candidate pool. A small or
uniform pool would make the gap small because of our choices. v1.1 widens the pool across six kinds of
chunker, from free to paid, so the gap measures chunking, not our selection.

## Chunker pool (setup = parser x chunker)

| Kind | Chunker | Settings | Parsers | Source |
|---|---|---|---|---|
| Size | Fixed token | 256, 512, 1,024; overlap 0 | all | v1 |
| Text | Recursive split-then-merge | target 512; overlap 0, 8, 32, 64; separators of the Adaptive Chunking paper (ekimetrics/adaptive-chunking, MIT, pinned commit) | all | v1 |
| Text | Sentence groups | 5 sentences per chunk; segmenter fixed and versioned before the run | all | new (Adaptive Chunking) |
| Text | Paragraph group | 2 paragraphs, 1 overlapping | all | v1 |
| Size | Dynamic token size | 128 to 512 (definition checked against its source before implementing) | all | v1 |
| Layout | Page | one page per chunk | all | v1 |
| Structure | Section + table-aware | one section per chunk; table row chunks; no overlap; section rule decided on 1-2 tuning PDFs | all | v1 |
| Hybrid | Docling HybridChunker | max 512 bge-m3 tokens; structure from the DoclingDocument | Docling only | new |
| Semantic | Embedding breakpoints (paper baseline) | LangChain SemanticChunker, gradient breakpoints (threshold from each document's own distances), its defaults; Qwen3-Embedding-0.6B (pinned revision) as in the paper, float32 standard attention (the paper's bfloat16 + flash-attention 2 need an Ampere GPU) | all | Adaptive Chunking |
| LLM | LLM-regex | Gemini 3.5 Flash-Lite (exact model id as listed by the API, recorded in every manifest); LLM sees a document sample, returns a split regex applied to the whole text; 2-3 runs to measure noise | all | new (Adaptive Chunking) |

All chunkers share the v1 post-processing (merge under 100, re-split over 1,024), the bge-m3 tokenizer and the
heading-prefix switch. Chunkers see only the parsed document, never questions.
A chunker whose cut points nearly duplicate a cheaper one is dropped (boundary similarity, P2-R08).
Random cut stays a scorer sanity test (floor), not a candidate.

## Quality and cost per document d and setup s
- Quality R(d, s) = Recall@1,250 (v1 main metric).
- Cost C(d, s) = model tokens = index tokens (all chunk tokens, overlap and prefix counted) + LLM input and
  output tokens used by the chunker. Reported alongside: chunking time, peak RAM, paid credits.

## Oracle with the trade-off
- R*(d) = max over s of R(d, s).
- Tied(d) = setups whose bootstrap interval overlaps that of the best setup (v1 tie rule).
- oracle(d) = the setup in Tied(d) with the lowest C(d, s).
- Best single setup s0 = highest mean R over documents; ties go to the lower mean C.

## Main numbers
- Gap = mean_d R(d, oracle(d)) - mean_d R(d, s0)
- Gap captured = (Agent - Best single) / (Oracle - Best single)
- Cost ratio = mean_d C(d, agent's choice) / mean_d C(d, s0)
- Pareto front of all setups on (mean R, mean C); gap also reported at a few cost limits.
No single quality-minus-cost score: a weight between recall and tokens would be a value judgement.