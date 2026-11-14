# Results

Main findings, with numbers copied from the result notes in `spec/spec_v1.2.md` (the spec is the authority; this
file is a summary). Each finding names the run it comes from.

**Traceability marks**
- ✅ **checked**: the run record exists in `runs/`, and the number matches its summary or its output file.
- ☑️ **run record**: the run record exists; the number was not re-checked against the output.
- ⚠️ **no run record**: the step that produced the number writes no run record (the inputs may be traceable).
  This applies to the gold placement, the scorer sanity tests, the held-out gold-drop and size-by-source reports,
  the AQ analysis and judge, and the document-level checks.

## 1. Main question: per-document choice versus one fixed setup (held-out)

Source: P4-FINAL-20261106-1 on scores P3-FINAL-20261106-1. Hybrid, Recall@1,250. ✅ Checked against the run record
summary and `data/results/p4/P4-FINAL-20261106-1_primary_setups.csv`.

| | Value |
|---|---|
| Primary choice set | 26 setups, 17 documents, 530 questions |
| Best single | pdfplumber / method1_tree_T384, **0.772** (15 of 26 setups statistically tied) |
| Same chunker on Docling | docling / method1_tree_T384, 0.752, statistically tied with the best (the agent's thorough-mode setup) |
| Split-half oracle | 0.765 |
| Gap (oracle − best single) | **−0.007 [−0.045, 0.023]**; raw maximum gap 0.058 (inflated by selection, reference only) |
| Decision (rule frozen before opening) | **NO-GO** for a per-document chooser; recommendation: one fixed setup |
| Tuning winner applied unchanged | docling / langchain_recursive_size256: 0.715, rank 20 of 26, tied with the best |
| Full grid (98 setups) | gap −0.056 [−0.108, −0.010] |
| Original grid | gap −0.042 [−0.084, 0.002] |

More choices make per-document choice worse, because the selection rests on few questions per document. Limits:
17 scorable documents, some with very few questions. Hindi (no gold), UniDoc (page-level gold only) and semantic
(out of memory on Kaggle) are not covered.

## 2. Chunk size

- On held-out, LangChain's library default against the tuned size (RQ5b, P5-LOCAL-20261110-2 ✅, checked against
  `data/results/rq5/P5-LOCAL-20261110-2_chunker.csv`):
  - Docling: 0.610 → 0.733, **+0.123 [0.057, 0.196]**.
  - pdfplumber: 0.648 → 0.748, **+0.100 [0.038, 0.186]**.
  - Both are significant after Holm over 8 comparisons: **Holm p < 0.01** (2,000 resamples; spec Errata
    2026-11-12).
- Own chunkers, starting size 512 against the tuned size (256 or 384): differences −0.015 to +0.047, none significant
  after Holm. The closest are method1_tree on pdfplumber, +0.047 [−0.000, 0.104], and fixed_token on pdfplumber,
  +0.035 [−0.001, 0.070]. (P5-LOCAL-20261110-2 ✅)
- Within each source (reporting). Tuning report P3-SIZESRC-20261112-1 ✅, the CSVs are byte-identical to the
  earlier output. The held-out report on P3-FINAL-20261106-1 is ⚠️ no run record (it needs `--final`).
  - Tuning: every source and parser has a negative size-recall correlation at every budget (rho −0.61 to −0.97;
    CUAD 6, Indian 3, OHR-Bench 10 documents). Best sizes are 209–439 tokens.
  - Held-out OHR-Bench (12 documents): rho −0.84 to −0.93, best sizes 216–318.
  - Held-out CUAD (3 documents): the correlation weakens as the budget grows.
  - Held-out Indian has 1 document. FinanceBench is not interpretable.
- Answers agree on the large-chunk penalty (section 5).

## 3. RQ5(a): parser settings

- **Digital** (5 PDFs, 306–308 questions; P3-RQ5D-20261110-1 ☑️, P5-LOCAL-20261110-1 ✅): no variant beats its
  default. Every difference is below 0.01, every interval reaches 0, and every Holm p ≥ 0.29. Parser choice still
  matters: Docling 0.827 against pdfplumber 0.798 on this sample.
- **Scanned** (10 MP-DocVQA PDFs):
  - Recall: Tesseract against the Docling default on 8 PDFs / 34 shared questions gives 0.786 vs 0.765, **+0.02
    [−0.05, 0.08], Holm p 0.50**, no difference. Runs P3-RQ5S-20261111-1 ☑️, P5-LOCAL-20261111-1 ✅, and the
    rerun P5-LOCAL-20261112-1 ✅ (identical).
  - Gold placement after the 2026-11-11 fix: Docling default 49 exact / 47 certain, Tesseract 41 / 43,
    pdfplumber 0. ⚠️ no run record; `p1_gold_match` writes none.
  - `ocr_rapidocr` and `ocr_scale_double` gave text byte-identical to the default on all 10 documents, so they are
    not separate settings. The extractions are P1-RQ5-KN01-20261109-* ☑️; the identity check is ⚠️ no run record.
  - Conclusion: on scans the defaults are fine. The decisive parser choice is scan detection (pdfplumber reads
    nothing), not the OCR settings.
  - **Withdrawn** (2026-11-11, answer-list bug): "Docling default 0 of 112 located exactly, Tesseract 65 / 18
    certain". The RQ5(a) result note of 2026-11-10 still contains these numbers; the correction note supersedes it.

## 4. Scorer sanity (before freezing scorer_v1)

- **Floor test:** P3-LOCAL-20261105-1 ☑️. Random cuts scored 0.14–0.17 lower everywhere.
  - Rule written before the run (non-overlapping separate intervals): FAIL in all 6 parser × retriever cases.
  - Amended paired rule: PASS in all 6 cases (upper ends −0.079 to −0.111; random cuts lower in 16–18 of 19
    documents). Both results are reported. ⚠️ The paired re-analysis has no run record of its own (log:
    `runs/tests/test_p3_sanity_floor_damage.txt`).
- **Damage test:** PASS. Splitting every table lowered Recall@1,250 by 0.08–0.10 on 112 table questions
  (11 Docling documents), and changed other questions by at most 0.01. ⚠️ The spec names no run id; log as above.

## 5. Answer quality (AQ)

Answers come from P6-LOCAL-20261110-1…3 ☑️ (gemini-3.5-flash-lite). ⚠️ The analysis (`aq_run --stage analyse`)
and the Qwen3-8B judge (run on Kaggle) have no run records. The numbers come from the files in `data/results/aq/`,
committed in a6278ca.

- **Held-out** (114 questions, 17 documents). Primary measure: token F1, best setup method1_tree T256 with F1
  0.393. Against it:
  - fixed_token 1024: **+0.123 [0.050, 0.210], Holm p < 0.01** (2,000 resamples, Holm over 6 comparisons; spec
    Errata 2026-11-12).
  - method1_tree T384: +0.065 [0.010, 0.137], Holm p 0.025. This runs opposite to the recall tie; it is reported,
    not claimed.
  - langchain_default: +0.047 [0.001, 0.099], Holm p 0.176, not significant (recall showed a significant +0.10 to
    +0.12).
- **Tuning:** no significant differences.
- **Spearman, F1 against Recall@1,250 across setups:** tuning 0.75, held-out 0.43. The judge (secondary measure)
  gives 0.75 and 0.64. Answers confirm the large-chunk penalty but do not separate the small-chunk setups.
- **Scanned** (25 questions, 10 documents): the best setup (Docling default, recursive 256) scores above all five
  Tesseract setups; one difference is significant after Holm (+0.243, Holm p 0.036); weak evidence (25 questions).
- **Judge check** (40 cases): the first pass gave 70% agreement, kappa 0.48 (FAIL). A second, non-blind pass on the
  12 disagreements gave 95%, kappa 0.86. The judge is therefore a **secondary** measure only. ⚠️ no run record.
- p = 0.000 in an output table means no bootstrap resample crossed zero: a two-sided p below 2/2000 = 0.001, before
  Holm.

## 6. Coverage of the gold (reporting)

Gold-drop report: tuning P3-GOLDDROP-20261112-1 ✅, the CSVs are byte-identical to the earlier output. The
held-out counts are ⚠️ no run record (they need `--final`). Main questions, with QASPER and UniDoc excluded:

- **Questions lost:**

| Split | Docling | pdfplumber |
|---|---|---|
| Tuning | 84/970 (8.7%) | 92/970 (9.5%) |
| Held-out | 121/742 (16.3%) | 205/742 (27.6%) |

- **Where the held-out gap comes from:** mostly Indian (2% vs 14%) and OHR-Bench held_out_c (22% vs 37%). Recall
  comparisons on shared questions therefore don't show Docling's coverage advantage on held-out.
- **Scanned (scanned_rq5):** pdfplumber loses 110/110, Docling default 64/110 (58%), Tesseract 67/110 (61%).
- **Held-out documents:** 31 → 17 in the main evaluation. Removed: 2 with no gold source (Hindi pair), 9 with
  page-level gold only (UniDoc), 3 with QASPER questions only. This matches P3-FINAL-20261106-1 ✅ and
  P4-FINAL-20261106-1 ✅ (`documents_left_out: []`). ⚠️ The accounting itself has no run record.

## 7. Scope

- No Hindi or multilingual claim: the held_out_hindi track has no question source. The Hindi OCR check was drafted
  but not run.
- **Fixed-k diagnostic** (P3-FIXEDK-20261112-1 ✅, tuning, main questions; descriptive, no intervals or tests): the
  best chunk size depends on the measure.
  - Recall@5: fixed_token 1024 is best on both parsers (0.904).
  - Recall@10: fixed_token 896 is best (Docling 0.964, pdfplumber 0.968).
  - Hit@1 and MRR barely separate sizes (Docling Hit@1 range about 0.53–0.62). Best Hit@1: Docling method1_tree
    T512 0.624, pdfplumber recursive 1024 0.632. Best MRR: Docling method1_tree T1024 0.743, pdfplumber recursive
    1024 0.748.
  - Recall@4,000 tokens: small chunks are best (Docling method1_tree T384 0.932, pdfplumber sentence 5 0.928; best
    sizes about 220–380 tokens).
  - With a fixed number of chunks, larger chunks read more text, so fixed-k favours them. At an equal token budget
    the ranking reverses.
  - The three Docling method1_tree winners named above are the superseded `_prefix_v11` settings.

## 8. Supplementary tables

Source: spec note "Supplementary analyses for the paper (2026-11-14)". Read-only and descriptive; no decision changes.
Outputs and scripts: `data/results/supplementary-20261114/`. ⚠️ These analyses write no run record; their inputs are
the run ids named in each table.

### 8.1 Index cost at 384 tokens (mean per document)

From P4-LOCAL-20261105-1 (tuning, 19 documents) and P4-FINAL-20261106-1 (held-out, 17 documents), full-grid setup
tables. Recall is hybrid Recall@1,250.

| Split | Parser | Setting | Chunks | Index tokens | Tokens / chunk | Recall |
|---|---|---|---|---|---|---|
| Tuning | Docling | method1_tree T384 | 121.2 | 35,789 | 295 | 0.789 |
| | | recursive 384 | 109.2 | 35,794 | 328 | 0.768 |
| | | langchain_recursive 384 | 117.1 | 35,792 | 306 | 0.797 |
| | pdfplumber | method1_tree T384 | 100.5 | 31,855 | 317 | 0.783 |
| | | recursive 384 | 93.8 | 31,855 | 339 | 0.785 |
| | | langchain_recursive 384 | 101.5 | 31,855 | 314 | 0.767 |
| Held-out | Docling | method1_tree T384 | 214.7 | 63,545 | 296 | 0.752 |
| | | recursive 384 | 194.1 | 63,552 | 327 | 0.701 |
| | | langchain_recursive 384 | 204.8 | 63,549 | 310 | 0.710 |
| | pdfplumber | method1_tree T384 | 173.1 | 56,179 | 325 | 0.772 |
| | | recursive 384 | 162.9 | 56,179 | 345 | 0.736 |
| | | langchain_recursive 384 | 180.6 | 56,179 | 311 | 0.749 |

Index tokens are the same for all three chunkers (no overlap, no prefix). **method1_tree does not reduce chunk
count**: it makes 6–11% more chunks than recursive. Its gain is recall, not storage. Per-document values were not
saved by P4.

### 8.2 Retriever: BM25-only and dense-only (primary 26 setups, Recall@1,250)

p4_analyse's own functions on P3-LOCAL-20261105-4 (tuning) and P3-FINAL-20261106-1 (held-out); the hybrid rows
reproduce P4-LOCAL-20261105-1 and P4-FINAL-20261106-1 exactly. The tuning primary scope is computed here for the
first time.

| Split | Retriever | Best single | Recall | Tied | pdfplumber method1_tree T384 | Gap [95%] | Rule |
|---|---|---|---|---|---|---|---|
| Held-out | hybrid | pdfplumber / method1_tree_T384 | 0.772 | 15 | best | −0.007 [−0.045, 0.023] | NO-GO |
| Held-out | BM25 | pdfplumber / langchain_recursive_256 | 0.779 | 15 | 0.756, tied | −0.029 [−0.079, 0.013] | NO-GO |
| Held-out | dense | pdfplumber / method1_tree_T384 | 0.775 | 14 | best | −0.003 [−0.074, 0.055] | NO-GO |
| Tuning | hybrid | docling / langchain_recursive_256 | 0.802 | 20 | 0.783, tied | −0.001 [−0.032, 0.030] | NO-GO |
| Tuning | BM25 | docling / langchain_recursive_256 | 0.804 | 15 | 0.756, tied | −0.005 [−0.037, 0.033] | NO-GO |
| Tuning | dense | pdfplumber / langchain_recursive_256 | 0.783 | 9 | 0.775, tied | −0.015 [−0.048, 0.016] | NO-GO |

The RQ1 conclusion does not depend on the retriever. The best single changes only under BM25. The hybrid winner of
each split stays tied with the best under every retriever. On the full and original grids no gap interval is above 0.

### 8.3 Pre-registration timeline (IST)

Commit times from git; push times from GitHub's activity API (only pushes and the branch creation on main; no force
push, so the published history was never rewritten). Run times from the run records' `created_at`.

| Event | Commit / run | Committed | First pushed |
|---|---|---|---|
| Spec v1 | 607d29c | 10-26 21:57:51 | 10-26 21:58:16 |
| Spec v1.1 (chunker pool, oracle, gap) | de4aff3 | 11-01 18:49:27 | 18:49:30 |
| v1.1: method 1 defined before any retrieval result | a4c30f7 | 11-02 17:03:35 | 17:03:38 |
| Spec v1.2: method 1 rules A1–A11 | 4584c8f | 11-04 12:05:37 | 12:05:40 |
| Rules A5b, A12 | 5503874 | 11-04 12:34:40 | 12:34:43 |
| Amendment A13 (line blocks) | f92ba8c | 11-04 23:30:30 | 23:30:33 |
| Amendment: S14 floor, S10 tie rule | a89b9ff | 11-05 11:03:12 | 11:03:14 |
| RQ5 added (after P3) | e59c69c | 11-05 11:15:51 | 11:15:54 |
| **scorer_v1 frozen** | 448173c | 11-05 11:21:57 | 11:22:00 |
| Grid extension after the first official run | 6032033 | 11-05 12:09:04 | 12:09:07 |
| Method 1 v1.2 (A9 on the whole prefix) | 93d7e16 | 11-05 17:12:21 | 17:12:24 |
| P4 v2 (tuning) | a781ff7 | 11-05 23:19:35 | 23:19:38 |
| **Held-out plan frozen** | 305da55 | 11-05 23:44:12 | **23:44:15** |
| Held-out extraction / chunking | P1-LOCAL-20261106-1 / P2-P4-KN01-* | runs 11-06 00:30 / from 00:44 | — |
| Held-out gold | a2c87c6 | 11-06 14:13:08 | 14:13:11 |
| **`--final` scoring** | P3-FINAL-20261106-1 | run 11-06 14:27:20 | — |
| Held-out analysis | P4-FINAL-20261106-1 | run 11-06 15:29:07 | — |
| Held-out result | 0d42cd0 | 11-06 15:37:49 | 15:37:52 |
| RQ5(a) design frozen | 8116310 | 11-08 10:36:05 | 10:36:09 |
| AQ design frozen | 479a55c | 11-10 12:11:12 | 12:11:15 |
| AQ code (answers on 11-10, see 8.5) | e5a924a | 11-10 12:17:35 | 12:17:37 |
| Correction (MP-DocVQA answers) | 3d5407e | 11-11 23:11:20 | 23:11:23 |
| AQ result | a6278ca | 11-12 15:57:42 | 15:58:06 |
| Held-out gold-drop and size-by-source reports (`--final`, no run record) | 5a6b52d | 11-12 18:02:31 | 18:02:35 |
| Errata | 3b9ecd6 / 56bd9ae | 11-12 22:55:13 / 11-14 14:41:01 | 22:55:16 / 14:41:05 |
| `--final` reproduction runs (by the author) | P3-SIZESRC-20261114-2 / P3-GOLDDROP-20261114-2 | runs 11-14 13:36 / 13:41 | — |

### 8.4 Datasets

Licences checked on each dataset's official page (2026-11-14).

| Dataset | Source | Licence | How the questions were made |
|---|---|---|---|
| CUAD v1 | The Atticus Project (HF theatticusproject/cuad) | CC BY 4.0 | Contracts labelled by hand for 41 clause types |
| QASPER | AllenAI (HF allenai/qasper) | CC BY 4.0 | NLP practitioners wrote questions from title and abstract; others answered with evidence |
| OHR-Bench v2 | opendatalab/OHR-Bench | CC BY 4.0 (questions); PDFs under their own licences | GPT-4o generated from page ground truth; rule, LLM and manual filtering (arXiv 2412.02592) |
| UniDoc-Bench | Salesforce/UniDoc-Bench | **CC BY-NC 4.0** | GPT-4.1 generated, Gemini-2.5-Pro grounding check, 3 human annotators with expert adjudication (arXiv 2510.03663) |
| FinanceBench | PatronusAI/financebench | **CC BY-NC 4.0** (annotations); PDFs are public SEC filings | Written by financial-analyst annotators (arXiv 2311.11944) |
| MP-DocVQA | rubentito/mp-docvqa (read from lmms-lab/MP-DocVQA) | MIT at the source; the lmms-lab copy states none | Reused from SP-DocVQA |
| Indian regulatory (GOLDEN_200) | github.com/shubham-61291/pre_generation_rag_retrieval_benchmark (commit 654c512); arXiv 2609.31660 | Apache-2.0 (repository); PDFs are Government of India documents, no licence stated | LLM-generated against verbatim evidence, 10% manual spot-check, deduplicated, no inter-annotator agreement |

- The two CC BY-NC sources allow research use. Files derived from them keep the non-commercial term; they are not
  in the repository (`data/` is git-ignored).
- **GOLDEN_200 provenance gaps:** the generating LLM, prompt and date; who spot-checked which questions and with what
  result; the corpus manifest (source URLs, retrieval dates, PDF hashes) the README describes; any licence for the four
  PDFs; any release tag or DOI. The Indian questions are LLM-generated, lightly checked gold.

### 8.5 Compute

From 650 run records. Hours are wall-clock time of recorded stages, not core-hours or measured GPU use.

| | Study runs | Test runs |
|---|---|---|
| GPU hours (Kaggle T4) | **19.5** (P3 embedding 13.4, P1 extraction 3.1, P2 chunking 3.1) | 0.35 |
| CPU hours | **10.8** (Kaggle CPU 5.3, laptop 5.5) | 0.64 |
| Gemini calls, LLM chunkers | 360 (4.0 M input tokens) | 0 |
| Gemini calls, AQ answers | 640 in run records (P6-LOCAL-20261110-1…3), 2,301 answers in total | 0 |
| Gemini calls, agent answers | 86 | 0 |
| LlamaParse | 1,711 credits (P1-LOCAL-20261028-*) | 0 |

- ⚠️ Not in any run record:
  - The Qwen3-8B judge: 2,301 judgements on Kaggle, GPU time unknown.
  - 1,661 AQ answers. They were made on 2026-11-10 before P6-1 started, by the unpaced code at e5a924a. Its runs
    most likely stopped on rate-limit errors before writing a record; no log survives.
- The P6 runs record `uncommitted_changes: true` (pacing added). Prompt, model (gemini-3.5-flash-lite), temperature 0,
  budget, setups and context building are identical across both code versions.
- The 500-call daily limit applies per API key. On 11-10 the author switched to further free-tier keys after keys hit
  the limit.

## Spec corrections

The spec's Errata (2026-11-12) corrects:
- "Holm p < 0.001" to "Holm p < 0.01" for RQ5(b) and AQ;
- the 2026-11-06 claim that rti_act_en duplicates tuning D4 (different file by SHA-256 and page count);
- the 2026-11-10 RQ5(a) scanned numbers, by pointing to the 2026-11-11 correction.

The spec's Errata (2026-11-14) corrects the RQ5(a) digital sample size "307–308 questions" to "306–308"
(docling_table_mode_switched has 306 shared questions; found by the reproduction check).

Not yet corrected: spec v1.2 repeats the line "A document is picked at most once…" (lines 23–24 and 44–45).
