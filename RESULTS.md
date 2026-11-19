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
  matters (descriptive, not tested): Docling 0.827 against pdfplumber 0.798 on this sample.
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
  - langchain_default: +0.048 [0.002, 0.099], Holm p 0.176, not significant (recall showed a significant +0.10 to
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

## RQ3: fixed-k diagnostic

P3-FIXEDK-20261112-1 ✅, tuning, main questions; descriptive, no intervals or tests. The best chunk size depends
on the measure.

- Recall@5: fixed_token 1024 is best on both parsers (0.904).
- Recall@10: fixed_token 896 is best (Docling 0.964, pdfplumber 0.968).
- Hit@1 and MRR barely separate sizes (Docling Hit@1 range about 0.53–0.62). Best Hit@1: Docling method1_tree
  T384 0.622, pdfplumber recursive 1024 0.632. Best MRR: Docling method1_tree T1024 0.742, pdfplumber recursive
  1024 0.748.
- Recall@4,000 tokens: small chunks are best (Docling method1_tree T384 prefix 0.925, pdfplumber sentence 5 0.928;
  best sizes about 220–380 tokens).
- With a fixed number of chunks, larger chunks read more text, so fixed-k favours them. At an equal token budget
  the ranking reverses.
- Superseded `_v10` / `_v11` settings are left out, as in P4 (spec Errata 2026-11-14, fixed-k). With them, the
  three Docling winners were the `_prefix_v11` settings (Hit@1 0.624, MRR 0.743, Recall@4,000 0.932).

### Controls: budget sweep and random floor (P3-SWEEP-20261118-1 ✅ checked against the CSV)

Tuning only, 19 documents, main questions, hybrid retrieval, 28 settings per parser; diagnostic (spec note "RQ3
controls", amended; result note 2026-11-18). Source: `data/results/p3/budget_sweep_tuning_tests.csv` (24 tested rows)
and `budget_sweep_tuning_crossover.csv`.

| Measure (size 256 − size 1,024) | Range over 4 families × 2 parsers | Holm |
|---|---|---|
| Recall@1,250 | +0.113 to +0.203 | all 8 significant |
| Recall@5 | −0.088 to −0.137 | all 8 significant |
| Lift@5 (Recall@5 − random floor) | +0.106 to +0.150 | all 8 significant |

- All 24 tested comparisons are significant after Holm (largest Holm p 0.036; p = 0.000 means below 2/2000 before
  Holm).
- No crossover up to 4,000 tokens in any of the 8 family–parser pairs. Not tested: the recall difference shrinks with
  the budget, from +0.31 to +0.40 (mean +0.345) at 250 tokens to +0.02 to +0.05 at 4,000.
- At k = 5, size 1,024 reads 3.5 to 4.0 times the tokens of size 256. Its recall lead under fixed k reverses once the
  random floor is subtracted: large chunks win at fixed k because they read more text.

## 8. Supplementary tables

Source: spec note "Supplementary analyses for the paper (2026-11-14)". Read-only and descriptive; no decision changes.
Outputs and scripts: `data/results/supplementary-20261114/`. ⚠️ Sections 8.1–8.5 and 8.7 write no run record; their
inputs are the run ids named in each table. Section 8.6 has run records.

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

- The two CC BY-NC sources allow research use; files derived from them keep the attribution and non-commercial
  terms. One such file is tracked: data/results/aq/sample.csv holds one FinanceBench question and its reference.
  Several tracked files hold question, reference, answer or document text from other sources; NOTICE.md lists them by
  source, with the licence of each and "unknown" where none is stated (the OHR-Bench, Indian and MP-DocVQA documents
  themselves). data/results/aq/answers.jsonl (model answers) is checksummed but not distributed. The repository has
  no licence of its own. (Corrects the earlier "not in the repository"; spec Errata 2026-11-15, distributed data.)
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

### 8.6 Robustness: tuning results without the Indian documents

Source: `scripts/robust_no_indian.py` (spec notes "Robustness: tuning results without the Indian documents" and
"Robustness without the Indian documents, held-out"), hybrid, Recall@1,250, existing scores only.
- Tuning: P4-NOINDIAN-20261114-1 ✅ on P3-LOCAL-20261105-4. The three Indian documents are 3 of 19 tuning documents
  but 570 of 860 questions; results average documents first. The rows with all documents reproduce 8.2 exactly.
- Held-out: P4-FINAL-NOINDIAN-20261114-1 ✅ on P3-FINAL-20261106-1 (run by the author's request with `--final`),
  leaving out indian_d2_ccs_conduct_rules (171 of 530 questions). The rows with all documents reproduce
  P4-FINAL-20261106-1 exactly.

| Split, scope | All documents: best single, recall | Tied | Gap [95%] | Without Indian: best single, recall | Tied | Gap [95%] |
|---|---|---|---|---|---|---|
| Tuning, primary (26) | docling / langchain_recursive_256, 0.802 | 20 | −0.001 [−0.032, 0.030] | docling / langchain_recursive_512, 0.791 | 15 | −0.014 [−0.044, 0.014] |
| Tuning, full (100) | docling / langchain_recursive_256, 0.802 | 32 | −0.015 [−0.046, 0.016] | docling / langchain_recursive_512, 0.791 | 24 | −0.034 [−0.066, −0.003] |
| Tuning, original (44) | docling / langchain_recursive_512, 0.801 | 7 | −0.034 [−0.066, −0.003] | docling / langchain_recursive_512, 0.791 | 5 | −0.055 [−0.086, −0.025] |
| **Held-out, primary (26)** | pdfplumber / method1_tree_T384, 0.772 | 15 | −0.007 [−0.045, 0.023] | pdfplumber / method1_tree_T384, 0.758 | 17 | −0.007 [−0.047, 0.028] |
| Held-out, full (98) | pdfplumber / method1_tree_T256_prefix, 0.773 | 23 | −0.056 [−0.108, −0.010] | pdfplumber / method1_tree_T256_prefix, 0.761 | 26 | −0.070 [−0.127, −0.022] |
| Held-out, original (42) | docling / sentence_5, 0.756 | 17 | −0.042 [−0.084, 0.002] | docling / sentence_5, 0.749 | 12 | −0.050 [−0.094, −0.006] |

Documents and questions: tuning 19 / 860 with, 16 / 290 without; held-out 17 / 530 with, 16 / 359 without.

- RQ1: NO-GO in every scope, on both splits, with and without the Indian documents. On tuning,
  langchain_recursive_256 drops to 3rd and stays tied. On held-out, the best single is unchanged and the main gap is
  the same (−0.007); the tuning winner docling / langchain_recursive_256 stays rank 20 and tied. Without the Indian
  documents per-document choice looks worse, not better.
- RQ2 on held-out was not rerun: it needs the chunk files, and the RQ5(b) tuned size is chosen on tuning only.
- RQ2: the pooled size-recall correlation stays negative for both parsers at every budget (rho −0.92 to −0.97 with,
  −0.87 to −0.95 without); best sizes 215–404 vs 216–402 tokens. The RQ5(b) tuned size is the same in all 8
  family-parser pairs, so RQ5(b) is unaffected. The per-source rows for CUAD and OHR-Bench cannot change.

### 8.7 GOLDEN_200 question validity (tuning, batch 1 only)

Source: spec notes "GOLDEN_200 validity check (tuning only)" and "GOLDEN_200 validity check stopped after batch 1".
⚠️ No run record (reporting step, no LLM call). Labels by the author in `data/results/golden_check/labels.csv`
(unchanged); the report output is in `report.txt` there. Valid means the question is clear and the gold evidence
really answers it. 20 random questions per document (seed 42), about 600 characters of Docling context shown.

| Document | Labelled | Invalid | Invalid rate [Wilson 95%] | Unsure | Invalid or unsure [Wilson 95%] |
|---|---|---|---|---|---|
| indian_d1 | 20 | 3 | 0.150 [0.052, 0.360] | 8 | 0.550 [0.342, 0.742] |
| indian_d3_fundamental_rules | 20 | 9 | 0.450 [0.258, 0.658] | 0 | 0.450 [0.258, 0.658] |
| indian_d4_rti_act | 20 | 8 | 0.400 [0.219, 0.613] | 0 | 0.400 [0.219, 0.613] |
| **Overall** | 60 | **20** | **0.333 [0.227, 0.459]** | 8, 0.133 [0.069, 0.242] | 0.467 [0.346, 0.591] |

- **Deviation:** the author stopped the check after batch 1, having judged the questions poor on reading. The
  expansion rule fixed before labelling (due for all three documents, 3 or more invalid of 20) and the reason
  review added after batch 1 were not carried out.
- Limits: one rater; short context (the only note, on one invalid question, says the shown text was not enough), so
  the rate does not separate question defects from context length; held-out indian_d2 was not checked.
- Section 8.6 shows that the RQ1 and RQ2 conclusions hold without the Indian documents.

## 9. Extension: planned chunkers built after the main study

Source: spec note "Extension result (2026-11-19)". P4-EXT-20261119-2 on scores P3-EXT-KN01-20261118-2 plus
P3-LOCAL-20261105-4. **Tuning only**; the extension does not use the held-out set. Hybrid, Recall@1,250, seed 42,
2,000 resamples. The first run, P4-EXT-20261119-1, is kept as a test (`data/results/ext/tests/`).

**New setups against the tuning best single** (docling/langchain_recursive_256; Holm over the 6). ✅ Checked against
`data/results/ext/P4-EXT-20261119-2_versus_reference.csv`.

| Setup | Recall | New − best [95%] | Holm p | Without Indian: new − best [95%] | Holm p |
|---|---|---|---|---|---|
| Docling paragraph_group | 0.791 | −0.010 [−0.059, 0.044], tied | 0.710 | −0.003 [−0.061, 0.056], tied | 0.940 |
| Docling dynamic_token | 0.745 | −0.055 [−0.108, −0.003] | 0.082 | −0.044 [−0.106, 0.015], tied | 0.268 |
| pdfplumber dynamic_token | 0.717 | −0.086 [−0.170, −0.011] | 0.075 | −0.087 [−0.180, 0.004], tied | 0.174 |
| Docling docling_hybrid | 0.719 | −0.081 [−0.122, −0.039] | < 0.01 | −0.075 [−0.124, −0.028] | 0.008 |
| Docling section_table | 0.653 | −0.148 [−0.208, −0.078] | < 0.01 | −0.127 [−0.197, −0.051] | < 0.01 |
| pdfplumber section_table | 0.618 | −0.184 [−0.253, −0.119] | < 0.01 | −0.158 [−0.228, −0.092] | < 0.01 |

None beats the best. dynamic_token is lower, but not significant after Holm.

**RQ1 with 32 setups.** ✅ Checked against `data/results/ext/P4-EXT-20261119-2_rq1.csv`. The original primary result
(26 setups, 0.802, gap −0.001 [−0.032, 0.030]) was reproduced exactly first.

| Scope | Best single | Gap [95%] | Decision |
|---|---|---|---|
| 32 setups, all documents (19 documents, 860 questions) | docling/langchain_recursive_256, 0.802 (22 tied) | +0.001 [−0.039, 0.042] | **NO-GO** |
| 32 setups, without Indian (16 documents, 290 questions) | docling/langchain_recursive_512, 0.791 (16 tied) | −0.016 [−0.048, 0.014] | **NO-GO** |

**Table questions** (107 OHR-Bench questions, Docling, 9 documents; descriptive). ✅ Checked against
`P4-EXT-20261119-2_table_questions.csv` and `_table_pairs.csv`: method1_tree T512 0.860, T384 0.810, dynamic_token
0.779, section_table 0.716. Only section_table − T512 excludes 0: −0.145 [−0.280, −0.008].

**Diagnostics: no bugs.** ⚠️ No run record (read-only, as the supplementary analyses). ✅ Numbers checked against
`data/results/ext/diagnostics/`.
- paragraph_group, dynamic_token (both parsers) and pdfplumber section_table sit on the RQ2 size–recall curve, so
  their results follow from chunk size (`size_curve.csv`).
- Docling section_table sits below the curve: −0.095 at measured size, −0.086 at token-weighted size (post-hoc).
  It has 5,363 one-row chunks (5,171 under 100 tokens). Row chunks are 1,329 of the 2,538 chunks ranked above the
  gold chunk on its 211 far-below questions (post-hoc; `rules_summary.csv`, `posthoc_above_gold_summary.csv`).
- **docling_hybrid caveat:** what was scored is HybridChunker plus our span mapping. 1,383 of 3,400 HybridChunker
  chunks could not be located in the frozen extraction (1,246 of them tables serialised differently), and their text
  was joined to neighbouring chunks. The result reflects the mapping as much as the chunker; it is not a test of
  HybridChunker as used directly (`rules_summary.csv`, `posthoc_unlocated_summary.csv`).
- Post-hoc (added after the first results, `posthoc_*.csv`): token-weighted sizes, causes of unlocated HybridChunker
  chunks, and what ranks above the gold chunk.
- Known edge cases, reported, not fixed:
  - dynamic_token: 1 D5 cut by tokens, and 1 chunk under 128 tokens before a table.
  - section_table: no prefix cap. One 1,056-token header prefix takes 84% of one question's budget; the largest
    prefix share is 88%.
  - the \x9f limitation.

No frozen result or decision changes.

## Spec corrections

The spec's Errata (2026-11-12) corrects:
- "Holm p < 0.001" to "Holm p < 0.01" for RQ5(b) and AQ;
- the 2026-11-06 claim that rti_act_en duplicates tuning D4 (different file by SHA-256 and page count);
- the 2026-11-10 RQ5(a) scanned numbers, by pointing to the 2026-11-11 correction.

The spec's Errata (2026-11-14) corrects the RQ5(a) digital sample size "307–308 questions" to "306–308"
(docling_table_mode_switched has 306 shared questions; found by the reproduction check).

The spec's Errata (2026-11-18) corrects the AQ held-out langchain_default line from +0.047 [0.001, 0.099] to
+0.048 [0.002, 0.099]: data/results/aq/analysis_held_out_vs_best.csv holds 0.0475 [0.0015, 0.099], rounded half up
to 3 decimals, as in the paper table. Holm p 0.176 and the conclusion are unchanged.

Not yet corrected: spec v1.2 repeats the line "A document is picked at most once…" (lines 23–24 and 44–45).
