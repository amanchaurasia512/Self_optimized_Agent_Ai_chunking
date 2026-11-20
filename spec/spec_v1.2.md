# Spec v1.2: held-out sets (amends v1.1)

Written on 2026-11-03, before any new document is opened. Everything in v1.1 stays in force.

## H1. P1 held-out (split P1-R02 and Set B)
- Unchanged; `pdfs/split.csv` stays locked.
- Deviation note: 12 of its 13 documents (all except indian_d2_ccs_conduct_rules) were viewed in the
  structure-only survey (runs/tests/test_tree_survey_v3_docling.txt, v4) while designing own method 1 (rules R17-R22).
  Only their tree structure was seen; no questions, answers or scores.
- Results on H1 are reported with this note.

## H2. Set C: unseen documents of known types (9)
- One per document type: CUAD; QASPER; OHR academic, administration, finance, law, manual; UniDoc finance, healthcare.
- Rule, per type:
  1. the same eligibility filter P1 used for that source;
  2. drop every document already in the catalog;
  3. take the largest by a length measure in the dataset metadata (CUAD: contract text length; QASPER: paper
     text length; OHR: page count; UniDoc: number of page images);
  4. a tie goes to the first in dataset order.
- No PDF is opened before it is picked.
- A document is picked at most once, by its source id across all domains (UniDoc lists some documents under more
  than one domain); if a type's largest is already taken, the next largest is picked.
- A document is picked at most once, by its source id across all domains (UniDoc lists some documents under more
  than one domain); if a type's largest is already taken, the next largest is picked.

## H3. Out-of-domain: kinds and sources never seen (9)
- UniDoc's six unused domains (commerce_manufacturing, construction, crm, education, energy, legal): one each,
  by the H2 rule (UniDoc measure).
- OHR's two unused domains (news, textbook): one each, by the H2 rule (OHR measure).
- FinanceBench (never used in this project): candidates = documents in the top 10% by number of questions;
  only the candidates are downloaded; the largest by page count, read from the PDF file only (no content viewed);
  a tie goes to the first in dataset order.
-Candidates that cannot be downloaded are skipped and listed: johnson_johnson_2022_10k and
  johnson_johnson_2023_8k_dated_2023_08_30 (host not found), pepsico_2022_10k (HTTP 403), run of 2026-11-03.

## H4. Rules for all held-out sets
- Extraction: the pinned Docling setup on GPU (as P1-KN06); gold: the P1 certain-only rules.
- Sealed until the final evaluation; every method runs on them once.
- All scripts skip held-out documents by reading `pdfs/split.csv`, never a hand-typed list.
- Set C and H3 rows are added to `pdfs/split.csv` once, as `held_out_c` and `held_out_ood`, and never redrawn.



- A document is picked at most once, by its source id across all domains (UniDoc lists some documents under more
  than one domain); if a type's largest is already taken, the next largest is picked.

## Backup dataset (not part of any held-out set)
- Patram-Bench (patrambench.github.io; CC BY-SA 4.0): Indian document images, 23 languages, VQA annotations.
  Checked 2026-11-03: paper "coming soon", HuggingFace and GitHub pages not reachable.
- Possible uses once public: an Indian-language parser test (P1 question), or an extra Indian held-out test if it
  contains multi-page documents with answers locatable in the text. Any use needs its own spec entry first.


## Own method 1: the structure-tree cutter (A1-A11), written 2026-11-04 before any method-1 result
- A1 Input: the tree (src/chunk/tree.py v4, rules R1-R22), the parser blocks, a budget T in {512, 1024}.
- A2 Output: spans of the original text, passed through the shared base (post_process, Layer 1, chunk.json, run
  record) like every baseline. No LLM; cost = index tokens (span + prefix).
- A3 A node whose subtree fits T is one piece.
- A4 A node that does not fit is opened into its own text (before its first child) and its children, in order.
- A5 Consecutive pieces under the same parent are packed in order while the total fits T. Pieces of different
  parents are never packed together; an opened (too large) child is never packed with its neighbours.
- A6 A region without children that does not fit is packed from whole parser blocks in order (as R22).
- A7 A single block larger than T: text is cut between sentences, a sentence still larger by token count (the base's
  split_long); a table is cut between rows, with its header row repeated in each piece's prefix.
- A8 Two variants: noprefix (text only, as the baselines) and prefix (text plus its path).
- A9 Prefix = labels and short titles of the ancestors; the farthest are dropped first if it exceeds 10% of T
  (a fixed design setting). Stored in the chunk prefix field; prefix tokens count in the index cost.
- A10 A tree with no usable nodes (only the root) reduces to paragraph packing (A6); no threshold decides this.
- A11 Cross-references (spec v1.1 step 6) are not in this version; they are a later, separate variant.
- Settings: method1_tree_T512_noprefix, method1_tree_T512_prefix, method1_tree_T1024_noprefix, method1_tree_T1024_prefix.
- A5b (2026-11-04, from the D4 test run, before any result) A piece under the shared minimum (100 tokens) that comes
  right before an opened child is joined to that child's first piece when the result fits T: a heading or opening line
  goes with what follows it, not with the previous chunk.
- A12 (2026-11-04, from the D4 test run, before any result) The prefix leaves out ancestors spanning more than half of
  the document text: they are shared by most chunks and do not tell chunks apart (cover titles, dates).

- S5b (2026-11-04) bge-m3 dense vectors in float32 (the rule used for the semantic baseline), normalised; texts are
  unique chunk texts (prefix + text) and certain span-level questions, keyed by SHA-256. Before the full embedding, a
  2% code check runs on the first, middle and last thirds of the texts into a separate test cache.

- A13 (2026-11-04, after the first dev scores; reason written before the change) When a parser gives no blocks
  (pdfplumber), the text's non-empty lines are the blocks (label "text"). Reason: the scorer sanity checks showed that
  method 1 never built a tree on pdfplumber (0 blocks, 0 nodes, no prefixes), so it fell back to sentence packing and
  its pdfplumber rows did not test the method at all; the change is not made because of its score. Method 1 version
  1.0 is kept and reported next to version 1.1 under the setting names method1_tree_*_v10. Parsers that give blocks
  (Docling) produce identical chunks under 1.0 and 1.1.

- S14 floor, result and amendment (2026-11-05): by the rule written before the run (non-overlapping separate 95%
  intervals) the floor test FAILED in all 6 parser x retriever cases (run P3-LOCAL-20261105-1), although random cut was
  lower by 0.14-0.17 everywhere. Reason: separate intervals over 19 documents mainly measure how much documents differ,
  not how much setups differ, and ignore that both setups are scored on the same documents. Amended rule: the paired
  per-document difference (random cut - best setting) has a 95% clustered-bootstrap interval entirely below 0. Result
  under the amended rule: PASS in all 6 cases (upper ends -0.079 to -0.111; random lower in 16-18 of 19 documents).
  Both results are reported.
- S10 amendment (2026-11-05, before any P4 result): for the same reason, ties are judged on paired differences: two
  setups tie on a set of documents when the 95% clustered-bootstrap interval of their per-document difference contains
  0 (same resamples for every setup). oracle(d) and the tie rule (a tie goes to the cheaper setup) otherwise unchanged.
- S14 damage (2026-11-05): PASS. On 112 table questions (11 Docling documents) splitting every table lowered
  Recall@1,250 by 0.08-0.10 for every retriever; other questions changed by at most 0.01.

## Research question added 2026-11-05 (scope and method decided after P3 is complete)
- RQ5. Does tuning improve retrieval: (a) tuning the parser's settings, and (b) tuning the chunker's settings,
  compared with their defaults?
  Notes for the later discussion: (b) can reuse the existing chunker variants (size, overlap, T, prefix) chosen on the
  tuning documents and tested once on the held-out documents; (a) needs new Docling extractions with other settings
  (e.g. OCR off, forced full-page OCR, table modes). RQ5 compares one global tuned setting with the default; the main
  question compares choosing per document (oracle, agent).

## scorer_v1 frozen (2026-11-05)
- All checks passed: gold alignment; 20 hand-checked cases (S13); 15 checks against code mistakes; sanity tests
  floor (paired rule, see S14 amendment), damage, ceiling, stability (identical chunks and scores across Kaggle and
  laptop) and budget. From here the scorer is not changed; any change means a new scorer version and a full re-run,
  reported openly. Runs before this point (scorer_v1-dev) are development runs, not results.

## Grid extension after the first official run (2026-11-05)
- Reason: run P3-LOCAL-20261105-2 showed size as the strongest factor, but the curve between 512 and 1,024 and below
  512 was measured for only one method (fixed 256). Decided after seeing tuning results; this is allowed tuning-set
  work (RQ5b) and is reported as such.
- Size grid 256, 384, 512, 640, 768, 896, 1,024 (overlap 0) for recursive, langchain_recursive, fixed_token and
  method1_tree (no prefix); method1_tree with prefix at the same new sizes; sentence chunking at 3 and 8 sentences;
  recursive overlap 64 at 256 and 1,024. 28 new settings per parser, both parsers.
- Same frozen scorer_v1. Sizes 768 and 896 are left out at budget 750 by Option C, like 1,024.
- P4 reports the original 22 settings and the full grid side by side, since more settings can only raise the oracle.


## Method 1 v1.2: A9 cap on the whole prefix (2026-11-05)
- Found by: method1_tree_T256_prefix (Docling) left out at budget 750 (Option C) although T = 256. A read-only check
  showed the 10%-of-T cap leaked twice in make_prefix: the table header was added outside the cap (D1's table of
  contents is one table whose first row is 1,062 tokens), and the nearest heading was always kept even when longer
  than the cap. Over-cap prefixes: e.g. 782 of 3,486 chunks (Docling, T256); all 14 prefix settings affected.
- Not affected: every no-prefix setting (0 over-cap prefixes) and every other chunker (no prefix). Chunk cuts are
  unchanged; only the prefix text changes.
- Fix (A9 as written): the whole prefix, path and table header together, must fit within 10% of T; drop farthest
  ancestors first, then the table header, then the nearest heading.
- Old prefix outputs kept as *_prefix_v11; the 14 prefix settings are re-made on Kaggle and re-scored with the same
  frozen scorer_v1. P4 leaves out superseded *_vNN folders.

## P4 analysis rules, amended after the first dev run (2026-11-05)
- Dev run P4-LOCAL-20261105-1 (kept in runs/tests/) showed two flaws in "tie goes to the cheaper setup":
  (a) index tokens are nearly equal for all no-overlap settings (same text), so the cheapest tied setup was chosen by
  differences of 0.1 token per document (best single became pdfplumber sentence-8, 0.748, while the top was 0.802);
  (b) per-document tie tests have no power on documents with few questions (98 of 100 setups tied at 4 questions),
  so the "cheapest tied" oracle was below the best single on 8 documents.
- Amended rules:
  1. Best single: setups clearly worse than the top (paired document bootstrap, S10) are ejected; among the survivors
     the top by mean recall is the best single; the survivors are reported as statistically tied. Cost does not
     break quality ties.
  2. Oracle per document: split-half cross-fitting, 200 random splits: choose the best setup on half the document's
     questions, measure it on the other half. Gap = mean over documents of (oracle - best single), with a 95%
     document bootstrap interval. The raw maximum is reported for reference only (inflated by selection).
  3. Cost on two Pareto fronts: index tokens, and chunk count (vectors stored and searched). LLM tokens of LLM
     chunkers are to be added; until then their cost is a lower bound.
  4. Questions and documents left out (not scored by every setup) are listed with the parser that lacks them.
  
## Held-out evaluation plan, frozen before opening (2026-11-05)
- Sets: H1 (13), H2 / Set C (9), H3 / OOD (9): 31 documents, read only with --final. Scored once with the frozen
  scorer_v1 and analysed with P4 v2 (scripts/p4_analyse.py as committed today). No change to chunkers, scorer or
  analysis after opening; any change means a new version, reported openly, with the earlier held-out results kept.
- Gold for H2 and H3 is built with the P1 rules before scoring; questions that cannot be located are left out and
  counted, as on tuning.
- Run: every benchmark setting of the tuning grid (method 1 v1.2) on both parsers; all three retrievers and budgets.
- Primary analysis (the headline): hybrid, Recall@1,250. Choice set: recursive, langchain_recursive, fixed_token and
  method1_tree (no prefix) at 256, 384 and 512 (overlap 0), and sentence 5: 13 settings x 2 parsers = 26 setups.
  Reported: (a) the setup chosen on tuning, applied unchanged: docling/langchain_recursive_size256_overlap0_noprefix
  (top by mean on tuning); (b) the best single on held-out with its tied set; (c) the split-half oracle and the gap,
  with a 95% document bootstrap interval.
- Go / no-go (decided now): go for a per-document chooser over the primary choice set if the lower end of the 95%
  interval of the primary gap is above 0; otherwise no-go, and the fixed setup is the recommendation.
- Secondary: the full grid (all benchmark setups), and budgets 750 and 2,000. Reference only: langchain_default and
  page on both parsers (what an out-of-the-box setup loses).
- Reasons for the primary choice set (from tuning): sizes above 512 were worse for every method; the prefix gave no
  measurable gain after the A9 fix; overlap gave no gain at 512; semantic and llm_regex ranked lowest.

- Correction (2026-11-06): H1 = held_out (11) + held_out_hindi (2). The Hindi pair has no gold yet; it is chunked and
  embedded with the rest, and scored only once gold exists (its own spec entry). pdfplumber extractions for H2 and H3
  were made on 2026-11-06 with the unchanged P1 script (P1-R03).
- P4-KN01 (2026-11-06): 49 of 50 settings complete on all 31 held-out documents, both parsers. semantic failed with
  CUDA out of memory on the largest held-out documents (Docling 21 of 31, pdfplumber 0). Decision: semantic is left
  out of the held-out evaluation (not in the primary choice set; secondary grid without it). The incomplete folder is
  kept and is not scored (the scorer only scores complete settings).
- The P3-KD01 gold on Kaggle held tuning questions only, so the 292 H1 questions (and 21 chunk texts) were embedded on
  the laptop CPU (P3-LOCAL-20261106-1) with the same model, revision and fp32.

## Held-out gold (2026-11-06), made before any held-out scoring
- Same P1 code and rules (P1-R06, src/gold/matching.py, the frozen drop rule): CUAD answers kept only if they occur
  once in the contract (p1_cuad_select.gold_spans, occurrences == 1); OHR-Bench text and table evidence only
  (p1_ohr_select.USABLE_SOURCES); QASPER union of annotators, text evidence; UniDoc page-level (not scored, D3).
- FinanceBench (new source, OOD): evidence_text of each evidence item as the gold; searched in the whole document
  (no page guide, like CUAD and QASPER, so no assumption about its page numbering); certain by the same P1 rule.
- Tuning gold must be byte-identical after the re-run (checked); held-out rows are appended after the tuning rows.
- Left out of held-out scoring: the Hindi pair (rti_act_en duplicates tuning D4; rti_act_hi has no question source)
  and, by D3, the 8 UniDoc documents (page-level gold only). Kept for later tests.

- Held-out scored once: P3-FINAL-20261106-1 (scorer_v1, --final; H1, Set C and OOD; Hindi pair left out).
  After scoring, p4_analyse got a --settings option that only names the pre-registered primary choice set (scope
  "primary"); the analysis functions (ties, best single, split-half oracle, gap, Pareto) are unchanged.
## Held-out result (2026-11-06), P4-FINAL-20261106-1 on P3-FINAL-20261106-1
- Primary (26 setups, 17 documents, 530 questions; hybrid, Recall@1,250): best single pdfplumber/method1_tree_T384
  0.772 (15 of 26 tied); split-half oracle 0.765; gap -0.007 [-0.045, 0.023]; raw gap 0.058.
- Decision by the frozen rule: NO-GO for a per-document chooser over the primary choice set (lower end of the
  interval below 0). Recommendation: one fixed setup.
- Tuning winner applied unchanged (docling/langchain_recursive_size256): 0.715, rank 20 of 26, tied with the best.
- Secondary: full grid (98 setups) gap -0.056 [-0.108, -0.010]; original grid -0.042 [-0.084, 0.002]. More choices
  make per-document choice worse (selection on few questions per document).
- Limits: 17 scorable documents, some with very few questions; Hindi (no gold), UniDoc (page-level) and semantic
  (out of memory) not covered.

## RQ5(a) scanned sample, rule frozen before selection (2026-11-07)
- Source: MP-DocVQA (Tito et al., original licence MIT), validation split, read from the Hugging Face copy
  lmms-lab/MP-DocVQA (the official repo holds only a card). Test split not used (answers not public).
- Rule: documents whose page list is identical across all their questions; at least 10 pages; the 10 with the most
  questions; ties by doc_id. One PDF per document, built losslessly from its page images in page-list order.
- Role: a separate scanned set for screening parser settings (RQ5a); not part of the sealed held-out set.
  pdfplumber is expected to read nothing (no text layer); the test is Docling's OCR settings.
## RQ5(a) parser settings test, design frozen before running (2026-11-08)
- Question: does tuning a parser's settings beat its defaults? Each parser variant is its own "parser" (own
  extraction folder, gold file and scores); the default variant must reproduce the frozen extraction exactly (checked
  on one tuning PDF before any variant is run).
- Samples: digital = per source, the tuning PDF with the most certain span questions on both parsers (CUAD, Indian,
  OHR finance, OHR administration or manual, OHR academic; QASPER and UniDoc left out), 5 PDFs; scanned = the 10
  MP-DocVQA val documents (scanned_rq5).
- Variants, digital: Docling default, OCR off, table mode ACCURATE, heading hierarchy on, replace broken text layer;
  pdfplumber default, layout=True, wider tolerance (x_tolerance 3 -> 5). Scanned: Docling default, OCR engine
  Tesseract, OCR engine RapidOCR, higher image resolution (scale 2x the default); pdfplumber default only.
- Chunkers: method1_tree T256 and T384 (no prefix), recursive 256, langchain_recursive 256, fixed_token 256.
- Scanned gold: of the accepted answers, the longest; searched on its answer page with the P1 matching and certain
  rules (short answers found more than once are uncertain and dropped).
- Scoring and decision: scorer_v1, hybrid, Recall@1,250. A variant beats its default if the paired document
  bootstrap interval of (variant - default), averaged over the 5 chunkers, lies above 0; Holm correction over the
  variants of each parser and sample.
- Stage 2, only for a winning variant: run it on all tuning PDFs, then compare with the default once on the held-out
  set (a pre-registered second use of the held-out set, reported as such).

- Correction before running (2026-11-08): the table-mode variant switches Docling's default table mode to the other
  mode (FAST if the default is ACCURATE, and the reverse), because the default may already be ACCURATE; the mode used
  is recorded in each variant extraction.

## RQ5(a) result (2026-11-10)
- Docling default reproduced the frozen extraction exactly on Kaggle (text, pages, elements, parser info).
- replace_broken_text not run: OcrAutoOptions (the default OCR engine) has no replace_broken_text_layer option in
  Docling 2.143.0; stopped by the option check, left out.
- Digital sample (5 PDFs, 307-308 questions; P3-RQ5D-20261110-1, P5-LOCAL-20261110-1): no variant beats its default
  (all differences below 0.01; every interval reaches 0; Holm p >= 0.29). No stage 2. Parser choice still matters
  (Docling 0.827 vs pdfplumber 0.798 on this sample).
- Scanned sample (10 MP-DocVQA PDFs): ocr_rapidocr and ocr_scale_double gave text identical to the default (the Auto
  engine apparently uses RapidOCR; scale has no effect with it), so they are not distinct variants. Tesseract: 65
  exact and 18 certain answer placements vs 26 and 0 for the default; pdfplumber reads no text. The planned recall
  comparison cannot be computed (no certain gold with the default OCR), because gold is placed in each parser's own
  text; a parser-independent gold (e.g. MP-DocVQA word boxes) is future work. Reported descriptively.
## RQ5(b) design, written before the analysis (2026-11-10)
- Question: does tuning a chunker's size beat its default? Specified after the held-out scores existed (disclosed);
  the rule is mechanical so that no choice depends on held-out results.
- Tuned: per chunker family (langchain_recursive, recursive, fixed_token, method1_tree; overlap 0, no prefix) and
  parser, the size with the highest mean document recall on the tuning run P3-LOCAL-20261105-4 (hybrid,
  Recall@1,250, main questions).
- Default: LangChain = its library default (langchain_default); the other families have no outside default, so the
  spec v1 starting size 512 is used.
- Test on the held-out run P3-FINAL-20261106-1: paired document bootstrap of (tuned - default) on the questions both
  have; Holm over all 8 comparisons. Tuned beats default if the interval lies above 0 and Holm p < 0.05.
## RQ5(b) result (2026-11-10), P5-LOCAL-20261110-2
- LangChain library default vs tuned size (chosen on tuning), held-out: Docling 0.610 -> 0.733 (+0.123 [0.057,
  0.196]); pdfplumber 0.648 -> 0.748 (+0.100 [0.038, 0.186]); both significant after Holm (p < 0.001, bootstrap
  resolution 1/2000).
- Own chunkers, spec v1 start 512 vs tuned (256 or 384): differences -0.015 to +0.047; none significant after Holm
  (closest: method1_tree pdfplumber +0.047 [-0.000, 0.104]; fixed_token pdfplumber +0.035 [-0.001, 0.070]).
- RQ5 answer: tuning gains much where the default is far off (LangChain default chunks); little beyond a sensible
  size; parser settings give no gain on digital PDFs (RQ5a).

## Answer-quality check (AQ), design frozen before running (2026-11-10)
- Question: does answer quality from the retrieved chunks rank setups the way Recall@1,250 does? (Recall measures
  whether the gold text is read, not whether an LLM can answer from it.) Uses the held-out set a third time, for this
  new question only; disclosed.
- Sample: 20% of each PDF's questions (rounded up, at least 1), seed 42; tuning and held-out: the main certain span
  questions shared by both parsers; scanned: all 112 MP-DocVQA questions (no located gold needed).
- Setups, digital (Docling): method1_tree T256 and T384, langchain_recursive 256 and 512, recursive 512,
  fixed_token 1024, langchain_default (no prefix, overlap 0). Scanned: the 5 RQ5 settings on docling (default OCR)
  and docling_ocr_tesseract.
- Context: hybrid retrieval, chunks read in rank order up to 1,250 tokens, exactly as the scorer reads them.
- Answer: gemini-3.5-flash-lite (src/chunk/llm.py), temperature 0, one fixed prompt: answer only from the context,
  or reply "not found".
- Reference: each source's own answer (CUAD gold span text, QASPER answers, OHR-Bench answers, Indian answers,
  FinanceBench answer, MP-DocVQA accepted answers).
- Judge: the same model, temperature 0, a fixed guide: correct (all key facts of the reference) = 1, partly = 0.5,
  wrong or not found = 0. Checked first on 20 cases labelled by hand without seeing the judge's label; used only if
  agreement is at least 80%; otherwise the guide is revised once and re-checked on 20 new cases.
- Analysis: mean answer score per setup (document means first), paired document bootstrap against the best setup,
  and the rank correlation (Spearman) between setups' answer scores and their Recall@1,250.

## Correction to RQ5(a) scanned results (2026-11-11)
- Bug: rq5_scanned_build stored each MP-DocVQA answer list as its text form split into characters, so the scanned
  gold (longest accepted answer) was a single character. Found through the answer-quality check (F1 near 0 while
  the answers were visibly right). Fixed (answer_list), selected_questions.json rebuilt (110 questions, not 112 as
  written earlier), gold re-matched; all non-scanned gold rows byte-identical.
- Withdrawn: "Docling default 0 of 112 located exactly, Tesseract 65 / 18 certain".
- Corrected: Docling default (Auto OCR) 49 exact / 47 certain; Tesseract 41 / 43; pdfplumber 0. Answer F1 on the 25
  sampled scanned questions: Docling default 0.45-0.55, Tesseract 0.30-0.41. Docling's default OCR is kept for scans.
- The planned recall comparison (variant vs default) is now computable on the scanned sample; result recorded below.
- Scanned recall comparison (P3-RQ5S-20261111-1, P5-LOCAL-20261111-1): Tesseract vs Docling default on 8 PDFs / 34
  shared questions: 0.786 vs 0.765, +0.02 [-0.05, 0.08], Holm p 0.50, no difference. RQ5(a) conclusion for scans:
  defaults fine; the decisive parser choice is scan detection (pdfplumber reads nothing), not OCR settings.

- AQ judge amendment (2026-11-11): the judge is an open-weight model run on Kaggle (Qwen3-8B, 4-bit, greedy, thinking
  off; exact weights revision recorded in the run output), not gemini-3.5-flash-lite. Reasons: the free-tier daily cap
  (500 calls) would take 5 days, and a judge different from the answering model avoids self-grading. Same judge prompt,
  same 40-case human check with the 80% pass mark and kappa.

- AQ judge check (2026-11-12): Qwen3-8B judge vs human on 40 cases. First pass 70% agreement, kappa 0.48 (FAIL);
  11 of 12 disagreements were long-but-correct answers the human scored 0.5 and the judge 1, as the guide prescribes.
  The human re-read those 12 against the guide (not blind: the first confusion table had been seen) and the second
  pass gave 95%, kappa 0.86. Because the frozen rule asked for 40 new cases, the judge is used as a SECONDARY measure
  only; the primary answer-quality measures are token F1 and 'gold contained'.

## AQ result (2026-11-12)
- Primary measure token F1 (document means; paired document bootstrap of the best setup against every other setup,
  Holm-corrected per set). Held-out (114 q, 17 docs): method1_tree T256 best (F1 0.393); vs fixed_token 1024 +0.123
  [0.050, 0.210], Holm p < 0.001; vs method1_tree T384 +0.065 [0.010, 0.137], Holm p 0.025 (opposite to the recall tie;
  reported, not claimed); vs langchain_default +0.047 [0.001, 0.099], Holm p 0.176 (not significant; recall showed
  +0.10 to +0.12, significant); all other small-chunk setups Holm p 1.0. Tuning: no significant differences.
- Spearman (F1 vs Recall@1,250 across setups): tuning 0.75, held-out 0.43; judge (secondary) 0.75 / 0.64. Answers
  confirm the large-chunk penalty; they do not separate the small-chunk setups.
- Scanned (25 q, 10 docs): Docling default OCR beats Tesseract in all 5 pairings, significant after Holm in one
  (+0.243, Holm p 0.036). Consistent with the corrected RQ5(a): Docling default kept for scans.
- p = 0.000 means no bootstrap resample crossed zero (p < 1/2000).

## P3 fixed-k re-scoring (diagnostic), design written before running (2026-11-12)
- Question: does the best chunk size depend on the measure? Recall@1,250 fixes the tokens read; fixed-k measures fix
  the number of chunks read, which favours large chunks by construction. Diagnostic only; no decision is changed.
- Data: the tuning run's settings (P3-LOCAL-20261105-4), Docling and pdfplumber, tuning documents only, certain
  span-level main questions (QASPER excluded), same gold, chunks and bge-m3 cache. scorer_v1 unchanged.
- Ranking: hybrid only (scorer_v1 BM25 + dense, reciprocal rank fusion).
- Measures: Recall@k, k = 5 and 10 (gold characters inside the top-k chunks over all gold characters, no token budget,
  overlapping text counted once via read_ranking); Hit@1 (top chunk holds gold); MRR; Recall@4,000 tokens (read_ranking).
- Analysis: document means then setting means; one table per parser sorted by measured chunk size (mean tokens per
  chunk, prefix included); the best setting under each measure overall and within each size-swept family.
- Script: scripts/p3_fixedk.py; output data/results/p3/fixedk_tuning.csv.

## Gold drop rate (reporting, added 2026-11-12)

For every gold file (each parser and RQ5 variant), each question is classed as: kept (scored by
p3_score.gold_questions), page_level (page gold, left out by design), placed_not_certain (placed but not
certain), or not_placed (gold text not found). Drop rate = (placed_not_certain + not_placed) / (total - page_level),
reported per gold file, split and source, plus documents left with no kept question. Comparisons already use only
questions kept by every compared parser (P4 question_matrix, RQ5 paired dropna), so this table reports coverage;
it does not change any result. By default, documents in any split starting with held_out (held_out, held_out_c,
held_out_ood, held_out_hindi) are excluded; --final adds them (counts only, after the final evaluation).
Limitation: a question with no placement row at all is not in the gold file and is not counted.

Result (main questions, QASPER and UniDoc excluded): tuning, Docling 84/970 lost (8.7%), pdfplumber 92/970 (9.5%);
held-out, Docling 121/742 (16.3%), pdfplumber 205/742 (27.6%), the gap mostly from Indian (2% vs 14%) and
OHR-Bench held_out_c (22% vs 37%). Recall comparisons on shared questions therefore do not show Docling's coverage
advantage on held-out. FinanceBench keeps 1 of 7 questions on either parser; held_out_hindi has no gold rows.
Scanned (scanned_rq5): pdfplumber loses 110/110, Docling default 64/110 (58%), Tesseract 67/110 (61%).
Tuning has 25 documents, 20 with a kept question (19 without QASPER), matching the P3 tuning and fixed-k runs.
Files: data/results/p3/gold_drop_{tuning,final}.csv and gold_drop_empty_docs_{tuning,final}.csv.

## Size curve by source (reporting, added 2026-11-12)

Checks whether the pooled result (smaller chunks best at a token budget) holds within each source. Scores from an
existing P3 run: hybrid retriever, main questions (QASPER excluded), in-scope settings (p4_analyse.in_scope),
questions scored by every setting of a parser (p4_analyse.question_matrix), per parser and budget. Recall is the
mean over a source's documents of each document's question mean. Chunk size is measured: mean over documents of
index tokens / chunk count (prefix included; p4_analyse.index_cost). Reported per source: best setting, its size,
and the Spearman correlation between size and recall across settings, with the number of documents. Descriptive
only, no tests (few documents per source). A run holding held-out documents needs --final.

Result: tuning (P3-LOCAL-20261105-4), every source and parser has a negative size-recall correlation at every budget
(rho -0.61 to -0.97; CUAD 6, Indian 3, OHR-Bench 10 documents), best sizes 209-439 tokens. Held-out
(P3-FINAL-20261106-1): OHR-Bench (12 documents) rho -0.84 to -0.93, best sizes 216-318; CUAD (3 documents) weakens
with budget (Docling -0.74/-0.65/-0.52, pdfplumber -0.59/-0.51/-0.26, best sizes up to 699 at 2,000 on pdfplumber);
Indian has 1 document; FinanceBench (1 document, 1 question) is not interpretable (recall 0 for every setting at 750
and 1,250, so rho is undefined and the best setting arbitrary). Files: data/results/p3/size_by_source_{run}.csv and
size_by_source_summary_{run}.csv

## RQ5(a) scanned variants: two variants are copies of the default (correction, 2026-11-12)
- Check: on all 10 scanned_rq5 documents, the extracted text of ocr_rapidocr and ocr_scale_double is byte-identical
  to the Docling default (character difference 0). The extractions record different settings (default OcrAutoOptions;
  RapidOcrOptions, scale 3.0; OcrAutoOptions, scale 6.0) but the settings changed nothing. Install: Docling 2.143.0,
  run on Kaggle (Python 3.13.16; recorded in the P1-RQ5-KN01 run records and each extraction file); Docling is not
  installed in the local venv.
- Consequence: they are not separate settings and are removed from the scanned comparison family. The family frozen
  on 2026-11-08 (Tesseract, RapidOCR, scale 2x) shrinks to Tesseract alone.
- Result unchanged: the scored run P3-RQ5S-20261111-1 already held only docling and docling_ocr_tesseract, so the
  earlier comparison (P5-LOCAL-20261111-1) was already Holm over one variant. Rerun without them
  (P5-LOCAL-20261112-1): identical, Tesseract vs default +0.02 [-0.05, 0.08], p 0.504, Holm p 0.504, 8 documents,
  34 questions.
- Not checked: whether Docling's Auto OCR already selects RapidOCR on that install (which would explain the identity).

## Held-out document accounting (reporting, added 2026-11-12)

31 held-out documents (held_out 11, held_out_c 9, held_out_ood 9, held_out_hindi 2) -> 17 in the main evaluation:
no gold source -2 (rti_act_en, rti_act_hi; held_out_hindi); page-level gold only -9 (UniDoc: held_out 1,
held_out_c 2, held_out_ood 6); QASPER only -3 (held_out 2, held_out_c 1; scored separately, outside main questions).
No document lost its last kept question on either parser, and none is missing from the scores for another reason.
Left: held_out 8, held_out_c 6, held_out_ood 3 (FinanceBench 1 with 1 kept question, OHR-Bench 2), matching
P3-FINAL-20261106-1 main questions and P4-FINAL-20261106-1 (documents_left_out: []). rti_act_en differs from tuning
indian_d4_rti_act (SHA-256 and page count: 25 vs 78 pages); it may share text with it as an amended version of the
same Act, but it was never scored.
## RQ5 Hindi OCR check (parser-only, added 2026-11-12, after the final evaluation)

Character error rate (CER) of OCR settings on the 51 page images in data/external/sarvam_ocr/hindi_small
(IndicOCR-Bench test sample labelled Hindi; some pages may be other languages in Devanagari script). No chunking or
retrieval, no question gold; not part of the held-out evaluation. Settings: Docling default (Auto OCR), Docling +
Tesseract (lang hin, full-page OCR), Docling + EasyOCR (lang hi, full-page OCR), and plain Tesseract (hin) as a
reference outside Docling. CER = Levenshtein distance / ground-truth length, both NFC-normalised with whitespace
collapsed (can exceed 1). Docling 2.143.0 on Kaggle, as in RQ5(a). Reported: mean and median CER per setting, with a
page-clustered bootstrap interval computed locally afterwards.

## Scope: Hindi (decision, 2026-11-12)

The held_out_hindi track has no question source and is not evaluated; no Hindi or multilingual claim is made in this
study. Hindi PDFs need a recognised question set with answer spans, which we did not find; a multilingual evaluation is
left to a separate study designed from the start. The Hindi OCR check (hindi_small) was drafted but not run.


Result (P3-FIXEDK-20261112-1, tuning, main questions, no intervals): the best size depends on the measure. Recall@5:
fixed_token 1024 best on both parsers (0.904); Recall@10: fixed_token 896 (Docling 0.964, pdfplumber 0.968). Hit@1 and
MRR barely separate sizes (Docling Hit@1 range about 0.53-0.62; best Hit@1 Docling method1_tree T512 0.624, pdfplumber
recursive 1024 0.632; best MRR Docling method1_tree T1024 0.743, pdfplumber recursive 1024 0.748). Recall@4,000 tokens:
small chunks best (Docling method1_tree T384 0.932, pdfplumber sentence 5 0.928; best sizes about 220-380 tokens).
Under a fixed number of chunks, larger chunks read more text (5 x 1024 vs 5 x 256 tokens), so fixed-k favours them;
at an equal token budget the ranking reverses. This matches the disagreement on chunk size in related work. Descriptive
only: no intervals or tests.

## Errata (2026-11-12)

Corrections to earlier notes; the earlier notes are left as written.
- RQ5(b) result (2026-11-10): "both significant after Holm (p < 0.001, bootstrap resolution 1/2000)" should read
  "Holm p < 0.01". With 2,000 resamples a two-sided bootstrap p of 0 only means p < 2/2000 = 0.001, and Holm over
  the 8 comparisons multiplies that bound by 8 (< 0.008).
- AQ result (2026-11-12): "Holm p < 0.001" (held-out, method1_tree T256 vs fixed_token 1024) should read
  "Holm p < 0.01" (2,000 resamples, Holm over 6 comparisons: < 0.006). Its closing line "p = 0.000 means ... (p <
  1/2000)" should read p < 2/2000 = 0.001 for a two-sided p, before Holm.
- Held-out gold (2026-11-06): "rti_act_en duplicates tuning D4" is wrong. rti_act_en and indian_d4_rti_act are
  different files (SHA-256 8956eaba... vs 7eed541c..., 25 vs 78 pages); rti_act_en may share text as an amended
  version of the same Act. It was never scored (see "Held-out document accounting", 2026-11-12).
- RQ5(a) result (2026-11-10), scanned sample: the placement counts and "the planned recall comparison cannot be
  computed" are superseded by "Correction to RQ5(a) scanned results" (2026-11-11): Docling default 49 exact / 47
  certain, Tesseract 41 / 43; recall comparison computed (+0.02 [-0.05, 0.08], Holm p 0.50).

## Errata (2026-11-14)

Found by the reproduction check (2026-11-14); the earlier note is left as written.
- RQ5(a) result (2026-11-10), digital sample: "307-308 questions" should read "306-308 questions". The output
  P5-LOCAL-20261110-1_digital.csv gives docling_table_mode_switched 306 shared questions (docling_headings and
  docling_ocr_off 307, pdfplumber_layout 307, pdfplumber_tolerance_wide 308). A transcription error in the note
  only; the analysis and its conclusion are unchanged (the reproduced output is byte-identical to the original).

## Errata (2026-11-14, fixed-k)

Found while planning the paper; the earlier note is left as written.
- Fixed-k result (P3-FIXEDK-20261112-1, 2026-11-12): the run scored all 63 settings of P3-LOCAL-20261105-4,
  including 11 superseded method1_tree folders (*_v10 x 4: T512 and T1024, with and without prefix; *_prefix_v11
  x 7: T256-T1024), which P4 leaves out ("Method 1 v1.2", 2026-11-05), and the 2 sanity chunkers. Three Docling
  winners in the note are superseded settings. With P4's rule (in_scope: 50 of 63 settings, without the 11
  superseded and the 2 sanity settings) they read: best Hit@1 method1_tree T384 0.622 (not T512 prefix_v11
  0.624); best MRR method1_tree T1024 0.742 (not T1024 prefix_v11 0.743); best Recall@4,000 tokens method1_tree
  T384 prefix 0.925 (not T384 prefix_v11 0.932).
- Unchanged: every pdfplumber winner; Docling Recall@5 and Recall@10; the Docling Hit@1 range (about 0.53-0.62);
  the best sizes at 4,000 tokens (about 220-380 tokens); the conclusion (fixed k favours large chunks, an equal
  token budget reverses the ranking).
- data/results/p3/fixedk_tuning.csv is left as written; the paper applies the filter in
  paper/scripts/make_artifacts.py (removed 2026-11-20; see tag paper-v1.2).
## Agent spec (2026-11-13)
The agent design is in spec/agent_v1.md.

## Question numbering (2026-11-13)

For the README and the paper, existing work is labelled RQ1-RQ4; RQ5 keeps its spec number. RQ1 = the main question
(P4); RQ2 = chunk size and chunker at a fixed budget, overall and per source (P3, size-by-source report); RQ3 = effect
of the metric on the best size (fixed-k diagnostic); RQ4 = answer quality (AQ). These are labels for work already
designed and run, not new questions; no analysis changes.
## Reproduction check (2026-11-14)

Before the paper, every analysis whose numbers appear in RESULTS.md was re-run from the saved inputs, with no change
to code, spec or existing files: no `--final` run by Claude, no LLM call, no re-extraction on Kaggle.
- **How:** the committed code (ae7f506) was exported with `git archive` into an isolated copy outside the repo. In the
  copy, the result inputs were copied in and the large inputs (chunks, embeddings, extracted text, gold, pdfs) were
  linked read-only. Output folders started empty, so every output is new and no original could be overwritten.
  `p3_score` and `p4_analyse` ran with `--run-source REPRO`. The run records are in `runs/tests/repro-20261114/`; the
  outputs, logs, the comparison tables and the comparison scripts are in `data/results/repro-20261114/`. The run
  records give `commit: null` (the copy has no `.git`) and output paths relative to the copy; the code is ae7f506
  (`comparison/commit.txt`) and the files sit under `data/results/repro-20261114/`.
- **Re-run, with their originals:**

| Re-run | Original | Result |
|---|---|---|
| p3_score, tuning (the 59 + 62 settings of the original) P3-REPRO-20261114-1 | P3-LOCAL-20261105-4 | identical (962,568 rows, decompressed CSV) |
| p4_analyse, tuning P4-REPRO-20261114-1 | P4-LOCAL-20261105-1 | 6 files byte-identical |
| p4_analyse on P3-FINAL (26 primary setups) P4-REPRO-20261114-2 | P4-FINAL-20261106-1 | 9 files byte-identical; run-record summary identical |
| rq5_parser_compare digital P5-LOCAL-20261114-1 | P5-LOCAL-20261110-1 | byte-identical |
| rq5_parser_compare scanned P5-LOCAL-20261114-2 | P5-LOCAL-20261111-1 and -20261112-1 | byte-identical to both |
| rq5_chunker_compare P5-LOCAL-20261114-3 | P5-LOCAL-20261110-2 | byte-identical |
| aq_run --stage analyse (no run record) | data/results/aq/analysis_*.csv | 6 files byte-identical; Spearman lines as recorded |
| aq_run --stage judge-check-score (no run record) | AQ judge check, second pass | 95% agreement, kappa 0.86 |
| p3_fixedk P3-FIXEDK-20261114-1 | P3-FIXEDK-20261112-1 | byte-identical |
| p3_gold_drop, tuning P3-GOLDDROP-20261114-1 | P3-GOLDDROP-20261112-1 | 2 files byte-identical |
| p3_size_by_source, tuning P3-SIZESRC-20261114-1 | P3-SIZESRC-20261112-1 | 2 files byte-identical |
| p3_gold_drop --final P3-GOLDDROP-20261114-2 (run by the author) | gold_drop_*_final.csv (no run record) | 2 files byte-identical |
| p3_size_by_source --run P3-FINAL-20261106-1 --final P3-SIZESRC-20261114-2 (run by the author) | size_by_source_*_P3-FINAL-20261106-1.csv (no run record) | 2 files byte-identical |

- **Numbers:** 71 numbers in RESULTS.md compared with the new outputs, each formatted as RESULTS.md shows it; all 71
  match after one correction: the RQ5(a) digital sample size, "307-308 questions" for 306-308 (a transcription error in
  the 2026-11-10 note; see Errata 2026-11-14). The table is `data/results/repro-20261114/comparison/results_table.csv`.
- **Held-out reads:** p4_analyse on P3-FINAL reads the held-out chunk files, for the index token and chunk counts
  only, exactly as the original P4-FINAL did; the held-out score file was read as an input. The two `--final` runs
  were run by the author, in the isolated copy.
- **Side effect on a shared input:** loading the embedding cache (src/eval/embed.check_embedder, used by p3_score and
  p3_fixedk) rewrites `data/embeddings/bge-m3/embedder.json` after checking it names the same embedder. Its content is
  unchanged (SHA-256 dd0cb044..., identical to the untouched Kaggle copies); only its timestamp moved. Every other
  input file kept its path, size and timestamp.
- **Not re-run, and why:**
  - AQ judge check, first pass (70% agreement, kappa 0.48): `judge_check.csv` now holds only the second-pass labels,
    so the first pass cannot be recomputed.
  - RQ5(a) scanned gold placement (49 exact / 47 certain, Tesseract 41 / 43): `p1_gold_match` rewrites the gold
    files, so it was not run.
  - RQ5(a) OCR variants byte-identical to the default, and the held-out document accounting (31 -> 17): no script.
  - Scorer sanity (P3-LOCAL-20261105-1, floor and damage tests): left out by decision; it predates the frozen scorer
    and the damage test has no run id.
  - Extraction, embedding and answering runs (Kaggle, Gemini) and the Qwen3-8B judge: not repeated by design. Their
    saved outputs are the inputs above.
- **Checksums:** `docs/paper_checksums.txt` holds the SHA-256 of the 64 original result files and run records the
  paper uses (check with `sha256sum -c docs/paper_checksums.txt`).


## Supplementary analyses for the paper (2026-11-14), read-only, descriptive
- Purpose: five reporting tables for the paper. No decision, rule or frozen part changes; nothing here alters RQ1-RQ5.
  No `--final` run, no LLM call, no chunk file read. Outputs, scripts and the GitHub activity pages are in
  `data/results/supplementary-20261114/` (`tools/retrievers.py`, `tools/tables.py`). These analyses write no run
  record. The design was set by the author's request on 2026-11-14. Item (2) was computed before this note was
  written; it is descriptive and has no decision attached.
- **(1) Index cost at 384 tokens** (from the saved P4 setup tables: tuning P4-LOCAL-20261105-1, 19 documents;
  held-out P4-FINAL-20261106-1, 17 documents; means per document; per-document values were never saved and would need
  the chunk files):
  - Index tokens are equal within 0.03% for method1_tree T384, recursive 384 and langchain_recursive 384 on each
    parser and split (no overlap, no prefix: every chunker indexes the whole text once).
  - **method1_tree does not reduce chunk count.** It makes 6-11% more chunks than the own recursive chunker (tuning
    Docling 121.2 vs 109.2, pdfplumber 100.5 vs 93.8; held-out Docling 214.7 vs 194.1, pdfplumber 173.1 vs 162.9),
    and about as many as langchain_recursive (+3% to +5% Docling, -1% to -4% pdfplumber). Its chunks are shorter on average
    (295-325 vs 327-345 tokens), because it cuts at structure nodes. Its advantage is recall, not storage.
- **(2) BM25-only and dense-only** (Recall@1,250, main questions, scores P3-LOCAL-20261105-4 and P3-FINAL-20261106-1,
  original grid from P3-LOCAL-20261105-2): p4_analyse's own functions (question_matrix, analyse, resampled_means;
  seed 42, the same scope order full, original, primary), with the retriever filter changed. Index cost is not used
  by ties, best single, oracle or gap, so zero tables stand in. Check: the hybrid rows reproduce every value of the
  P4-LOCAL-20261105-1 and P4-FINAL-20261106-1 summaries exactly. The tuning primary scope is new (P4-LOCAL had none).
  - Held-out primary: hybrid best pdfplumber/method1_tree_T384 0.772, gap -0.007 [-0.045, 0.023]; BM25 best
    pdfplumber/langchain_recursive_256 0.779 (method1_tree_T384 0.756, tied), gap -0.029 [-0.079, 0.013]; dense best
    pdfplumber/method1_tree_T384 0.775, gap -0.003 [-0.074, 0.055].
  - Tuning primary: hybrid best docling/langchain_recursive_256 0.802, gap -0.001 [-0.032, 0.030]; BM25 same best
    0.804, gap -0.005 [-0.037, 0.033]; dense best pdfplumber/langchain_recursive_256 0.783, gap -0.015 [-0.048, 0.016].
  - The frozen go/no-go rule gives NO-GO for every retriever on both splits, so the RQ1 conclusion does not depend on
    the retriever. The best single changes only under BM25, and the hybrid winner stays in the tied set for every
    retriever. On the full and original grids no interval is above 0 (closest: held-out dense original +0.026
    [-0.036, 0.100]). Docling method1_tree T384 falls to 0.679 with dense alone on held-out (still in the tied set).
- **(3) Pre-registration timeline:** git commits, with the first push of each commit read from GitHub's activity API
  (read-only; 132 events from repository creation on 2026-10-26; only `push` and `branch_creation` on main, no
  force push or branch deletion, so the published history was never rewritten). Every spec freeze and amendment
  reached GitHub 2-25 s after it was committed (most within 4 s). The held-out plan (305da55) was pushed 2026-11-05 23:44:15 IST.
  Held-out extraction (P1-LOCAL-20261106-1, 00:30 IST), chunking (P2-P4-KN01-*, from 00:44 IST) and the `--final`
  scoring (P3-FINAL-20261106-1, 2026-11-06 14:27 IST) all came after that push. The table is in RESULTS.md section 8.
- **(4) Datasets and licences** (licences checked on each dataset's official page on 2026-11-14; table in RESULTS.md
  section 8):
  - **Non-commercial licences:** UniDoc-Bench and the FinanceBench annotations are CC BY-NC 4.0. Research use is
    covered. Any shared file derived from them (questions, gold spans, answers) must keep attribution and the
    non-commercial term; the repository's own licence does not cover them. They are not in the repository (data/
    is git-ignored). The agent and app ship no benchmark data.
  - MP-DocVQA is MIT at its source (rubentito/mp-docvqa); the lmms-lab copy we read states no licence of its own.
  - **Indian GOLDEN_200 provenance gaps** (read: the benchmark's README and LICENSE, its single commit 654c512 of
    2026-10-15, the GitHub page and the arXiv abstract 2609.31660; only the tuning question files D1, D3 and D4 were
    opened): the repository is Apache-2.0 and the questions were LLM-generated against verbatim evidence, with a 10%
    manual spot-check, deduplication and no inter-annotator agreement. Not found anywhere: (a) which LLM, the prompt
    and the generation date; (b) who did the spot-check, which questions were checked and what was found or removed
    (the JSON has no field for it); (c) the corpus manifest with source URLs, retrieval dates and PDF hashes that the
    README describes (absent, like requirements.txt and master_results.csv); (d) any licence for the four PDFs
    (Government of India documents); (e) a release tag or DOI. The Indian questions should be treated as
    LLM-generated, lightly checked gold.
- **(5) Compute** (650 run records; hours are wall-clock time of recorded stages, not core-hours or measured GPU use):
  study runs 19.5 GPU hours on Kaggle T4 (P3 embedding 13.4, P1 extraction 3.1, P2 chunking 3.1) and 10.8 CPU hours
  (Kaggle CPU 5.3, laptop 5.5); test runs 0.35 GPU and 0.64 CPU hours. LLM calls in run records: 360 Gemini calls by
  LLM chunkers (4.0 M input tokens), 640 AQ answer calls, 86 agent answer calls; LlamaParse 1,711 credits
  (P1-LOCAL-20261028-*). Not in any run record: the Qwen3-8B judge (2,301 judgements on Kaggle, GPU time unknown)
  and the 1,661 AQ answers below.
- **AQ answers without a run record:**
  - `data/results/aq/answers.jsonl` holds 2,301 unique answers; the run records P6-LOCAL-20261110-1…3 account for
    269 + 72 + 299 = 640 of them (the last 640 lines). The file is append-only, so lines 1-1,661 were written before
    P6-1 started (about 16:31 IST on 2026-11-10). The file has no per-line timestamps. No crash log survives (the
    session ran in a claude.ai web session, whose output is not stored locally).
  - The 1,661 earlier answers come from the unpaced code at e5a924a (4 concurrent requests, no pacing, record written
    only after every job finished). Its runs stopped on rate-limit errors before writing a record: the most likely
    cause, since no log survives. Every answer was flushed to the file as it arrived, so the answers were kept.
  - The P6 runs record `uncommitted_changes: true`: pacing was added (one request every 60/14 s, committed later in
    3d5407e together with a clean stop at the daily limit).
  - Same answer setup across both code versions (e5a924a against 3d5407e and the P6 run records): identical answer
    prompt, model gemini-3.5-flash-lite, temperature 0 (src/chunk/llm.py unchanged), budget 1,250, hybrid retrieval,
    the same setups and the same context building (`contexts`, `question_vector`, `encoder` and job building are
    unchanged). Same sample file (SHA-256 3abd903…, kept as data/backup_test/aq_sample_before.csv; the 2026-11-11
    rebuild changed only the 25 scanned references). The only differences are pacing (4 concurrent vs one start every
    4.29 s), the daily-limit stop, and the run-record field `concurrency` vs `seconds_between_requests`. The exact
    uncommitted P6 code is not kept; this comparison rests on 3d5407e and the P6 records.
  - Daily cap: the free-tier limit of 500 calls a day applies per API key. On 2026-11-10, after keys hit the daily
    limit, the author switched to further free-tier keys (author's statement; key identities are not recorded). All
    answers came from gemini-3.5-flash-lite. The 2026-11-11 judge amendment's "would take 5 days" assumed one key.
  - No retroactive run record was made.

## GOLDEN_200 validity check (tuning only), design written before any label (2026-11-14)
- Question: how many of the Indian benchmark's LLM-generated questions are invalid? The benchmark reports only a 10%
  manual spot-check with no results (see "Supplementary analyses", item 4). Descriptive; no study result or frozen part
  changes.
- Documents: tuning only, indian_d1, indian_d3_fundamental_rules and indian_d4_rti_act. indian_d2_ccs_conduct_rules is
  held-out and is never read (the script refuses any document that is not tuning in pdfs/split.csv).
- Sample: for each document, the 200 question ids from its GOLDEN_200 file in a random order (numpy
  default_rng(42).permutation, one generator per document); the first 20 are batch 1. All 200 questions are eligible,
  not only those the study's gold rules kept; the study's `certain` flag (Docling gold) is stored for a breakdown.
- Labels, by the author in a terminal labeller (scripts/golden_check.py --stage label): valid (y) / invalid (n) /
  unsure (s), with an optional note. **Valid** means the question is clear and the gold evidence really answers it.
  The labeller shows the question, the gold answer and evidence strings, and about 600 characters of the Docling
  extraction around the evidence as the study placed it (data/gold/spans_docling.jsonl; evidence marked >>> <<<). If
  the study could not place the evidence, the cited page's text is shown and this is said on screen. Saved after
  every label to data/results/golden_check/labels.csv; batches of 20; resumable.
- Report (--stage report): invalid rate per document and overall = invalid / labelled, with Wilson 95% intervals
  (z = 1.96). Unsure labels are counted in the denominator and reported separately; a sensitivity line counts unsure
  as invalid. Breakdown by the study's `certain` flag. The overall rate pools the labelled questions (equal sample per
  document).
- Expansion rule, fixed now: a document gets one more batch of 20 (the next 20 ids of the same permutation) if its
  batch-1 invalid count is 3 or more of 20 (Wilson lower bound above 5%). At most one expansion per document; the
  rule is checked by --stage expand, which refuses otherwise. Unsure labels do not trigger it.
- No LLM call, no run record (reporting step, like the AQ judge check). Interpretation is left to the result note.

## GOLDEN_200 reason review, added after batch 1 (2026-11-14)
- Added after seeing all 60 batch-1 labels (20 invalid, 8 unsure); not part of the design written before labelling,
  and reported as a later addition. Reason: the only note ("the retrieve chunk is not enough", D1-Q153) suggests that
  some invalid or unsure labels reflect the length of the shown context (about 600 characters) rather than a defect
  of the question.
- The original labels (labels.csv) are kept unchanged and the original invalid rate is still reported. The review
  adds a reason to each question labelled invalid or unsure; questions labelled valid are not re-checked, so the
  review can only lower the rate (disclosed).
- Review (scripts/golden_check.py --stage review): the same screen again plus about 2,000 characters of the Docling
  extraction around the same placement; the author gives one reason: 1 question unclear, 2 evidence does not answer
  the question, 3 gold answer wrong, 4 shown context too short (not a defect), 5 other (a note is required). Saved
  after every reason to data/results/golden_check/reasons.csv; resumable.
- Defect rate = questions with reason 1, 2 or 3 / labelled, per document and overall, with Wilson 95% intervals,
  reported next to the original invalid rate. Reason 4 is not a defect. Reason 5 is listed with its notes and is not
  counted; a sensitivity line counts it as a defect. While questions are still unreviewed, their number is shown.
- Expansion: the rule fixed before labelling is followed on the original labels. All three documents have 3 or more
  invalid in batch 1 (D1 3, D3 9, D4 8), so each gets batch 2 (the next 20 ids of the same permutation); the review
  does not change this. In the label stage a key m shows about 2,000 characters of context before the label is given
  (the label keys are unchanged); batch-2 labels can use it, batch-1 labels could not, so the report also shows the
  rates by batch. Batch-2 questions labelled invalid or unsure also go to the review.
- No LLM call, no run record.

## Robustness: tuning results without the Indian documents (2026-11-14), read-only, descriptive
- Question: do the tuning RQ1 and RQ2 results depend on the three Indian documents? They are 3 of 19 tuning
  documents but 570 of 860 main questions (results average documents first, so they weigh 3/19).
- scripts/robust_no_indian.py, on the tuning scores P3-LOCAL-20261105-4 only (hybrid, main questions, QASPER
  excluded), each analysis with all documents and without source Indian, using the study's own functions: P4
  (p4_analyse: full, original and primary scopes in that order, seed 42; the primary settings are the names in
  P4-FINAL-20261106-1_primary_setups.csv; zero cost tables, since cost does not enter ties, best single, oracle or
  gap); pooled size curve per parser and budget (Spearman of measured size and recall across settings); the RQ5(b)
  tuned size per family (rq5_chunker_compare.tuned_setting). The per-source size rows for CUAD and OHR-Bench cannot
  change. Writes a run record. No held-out document file is read, no frozen part or decision changes.
- Result (P4-NOINDIAN-20261114-1): NO-GO in every scope with and without the Indian documents. Primary: best single
  docling/langchain_recursive_size256 0.802, gap -0.001 [-0.032, 0.030] (19 documents) vs
  docling/langchain_recursive_size512 0.791, gap -0.014 [-0.044, 0.014] (16 documents, 290 questions; size 256 ranks
  3rd and stays tied). Without them the full-grid gap is below 0 (-0.034 [-0.066, -0.003]). Pooled size-recall rho
  -0.92 to -0.97 vs -0.87 to -0.95; best sizes 215-404 vs 216-402 tokens; the RQ5(b) tuned size is the same in all 8
  family-parser pairs, so RQ5(b) is unaffected.

## GOLDEN_200 validity check stopped after batch 1 (2026-11-14), deviation
- The author stopped the check after batch 1 by their own decision: on reading, they judged the questions poor. The
  expansion rule (fixed before labelling; due for all three documents) and the reason review (added after batch 1)
  were not carried out. This is a deviation from the design notes above and is reported as such.
- Result, batch 1 only, labels unchanged (data/results/golden_check/labels.csv; report output in report.txt there):
  20 of 60 invalid, 0.333 [0.227, 0.459] (Wilson 95%), and 8 of 60 unsure, 0.133 [0.069, 0.242]; invalid or unsure
  28 of 60, 0.467 [0.346, 0.591]. Per document invalid: indian_d1 3 of 20, 0.150 [0.052, 0.360] (8 unsure);
  indian_d3_fundamental_rules 9 of 20, 0.450 [0.258, 0.658]; indian_d4_rti_act 8 of 20, 0.400 [0.219, 0.613].
- Limits: one rater, no second rater; about 600 characters of context per question (the only note says the context
  was not enough for one question); the rate is not separated into question defects and context length. Held-out
  indian_d2 was not checked.

## Robustness without the Indian documents, held-out (2026-11-14)
- The author asked for the same P4 analysis on the held-out scores P3-FINAL-20261106-1 without
  indian_d2_ccs_conduct_rules (the only held-out Indian document), reading existing scores only, as P4-FINAL did:
  scripts/robust_no_indian.py --split held_out --final. Same rule as on tuning (source Indian left out), same scopes,
  rng order, primary settings and original run (P3-LOCAL-20261105-2). Only the P4 part runs: the size curve needs
  chunk files and the RQ5(b) tuned size is a tuning-only choice. The rows with all documents must reproduce
  P4-FINAL-20261106-1. New run record; no decision changes.
- Result (P4-FINAL-NOINDIAN-20261114-1): the rows with all documents reproduce P4-FINAL-20261106-1 exactly. Without
  indian_d2 (16 documents, 359 of 530 questions): primary best single pdfplumber/method1_tree_T384 0.758 (unchanged
  winner), 17 of 26 tied, gap -0.007 [-0.047, 0.028]; full grid -0.070 [-0.127, -0.022]; original -0.050 [-0.094,
  -0.006]. NO-GO in every scope; the tuning winner docling/langchain_recursive_size256 stays rank 20 and tied.

## AQ judge check: first-pass labels overwritten in place (reporting, added 2026-11-14)
- The first-pass human labels of the 40-case judge check were overwritten in place by the second pass in
  data/results/aq/judge_check.csv (a LibreOffice lock file dated 2026-11-13 remains next to it). Git holds one
  version of the file (a6278ca), identical to the working copy, with second-pass labels only (human 1.0 x 31,
  0.0 x 8, 0.5 x 1); no other copy exists in data/.
- The second pass (95%, kappa 0.86) is recomputable and was reproduced (data/results/repro-20261114/comparison/
  aq_judge_check.log). The first pass (70%, kappa 0.48; 12 disagreements, 11 of them human 0.5 / judge 1) rests on
  the note "AQ judge check (2026-11-12)" only.
- A deduction from the second-pass file, assuming the 28 agreeing cases and the judge scores were unchanged, gives
  70% and kappa 0.451 or 0.465 (depending on the first-pass label of the one judge-0.5 case), not the recorded 0.48.
  The files cannot show the cause. The recorded values are kept as written and flagged; the paper takes them from
  paper/data/manual_facts.csv (removed 2026-11-20; see tag paper-v1.2) with this note as source. No conclusion changes: the judge was a secondary measure
  because the first pass failed the 80% mark, which holds for every reconstruction.

## AQ judge check: size changed from 20 to 40 cases; judge amendment committed with the result (reporting, added 2026-11-15)
- The AQ design frozen at 479a55c (2026-11-10 12:11 IST) fixed the judge check as: 20 cases labelled by hand without
  seeing the judge's label; the judge is used only if agreement is at least 80%; otherwise the guide is revised once
  and re-checked on 20 new cases. The judge was the answering model (gemini-3.5-flash-lite).
- 3d5407e (2026-11-11 23:11 IST) added the judge-check stages to scripts/aq_run.py: CHECK_CASES = 40, one draw of
  40 tuning cases (seed 42) for blind labelling, and the fail message "revise the guide once (spec) and re-check on
  40 new cases". The code names no judge model; it judges through src/chunk/llm.py, which is gemini-3.5-flash-lite.
  No spec note in this commit records the change from 20 to 40 or gives a reason.
- Re-draw (2026-11-15, read-only, no LLM call): the 3d5407e logic (answered(), then the tuning rows, then
  .sample(40, random_state=42)) on the checksummed sample.csv and answers.jsonl reproduces judge_check_keys.csv and
  the question, reference and answer columns of judge_check.csv exactly, in the same order (pandas 3.1.0, the
  study's .venv). The 40 cases are one draw, not 20 + 20. Script: scripts/redraw_judge_check.py (reuses
  aq_run.answered and the seed and size constants, unchanged since 3d5407e); output:
  data/results/repro-20261115/redraw_judge_check.log. The script needs data/results/aq/answers.jsonl, which is
  checksummed (docs/paper_checksums.txt) but not distributed, so it can be re-run only where that file exists.
- The "AQ judge amendment (2026-11-11)" (Qwen3-8B on Kaggle; "the same 40-case human check") was first committed in
  a6278ca (2026-11-12 15:57 IST), together with the check's result (the note "AQ judge check (2026-11-12)"),
  judge_check.csv, judge_check_keys.csv and judgements.jsonl. No earlier commit holds the case files or a Qwen3-8B
  judge.
- What git can't show: when the 40 cases were drawn, labelled and judged (the check has no run record), and
  therefore whether the Qwen3-8B choice, dated 2026-11-11 in its heading, came before the check. What git does show:
  the 40-case size was in committed code before the result was committed.
- The result note's "the frozen rule asked for 40 new cases" follows the code at 3d5407e, not the frozen design,
  which says 20 new cases. Neither the revision nor a re-check was done. Instead, the 12 disagreements among the same
  40 cases got a second, non-blind pass (95%, kappa 0.86).
- Nothing is changed. The judge stays a secondary measure, because the first pass on the 40 cases failed the 80%
  mark (recorded 70%; every reconstruction in the note of 2026-11-14 is also below it). The paper states this in
  Method (Answer quality) and in the deviations table.

## Errata (2026-11-15, distributed data)
- "Supplementary analyses for the paper (2026-11-14)", (4), says that files derived from the CC BY-NC sources "are
  not in the repository (data/ is git-ignored)" and that "the repository's own licence does not cover them". Both
  are wrong:
  - data/results/aq/sample.csv (tracked since 3d5407e, 2026-11-11) holds one FinanceBench question and its reference
    (CC BY-NC 4.0). No UniDoc-Bench text is tracked.
  - data/ has been git-ignored since 5f4e103 (2026-10-26), but 35 files under it were force-added, among them
    sample.csv, judge_check.csv and data/external/mpdocvqa/selected_questions.json, which hold question, reference
    and answer text (NOTICE.md lists them by source).
  - The repository has no licence file of its own.
- Also tracked with source text: runs/tests/test_p3_hand_check_20_cases.txt (6a823b7, 2026-11-04): questions, gold
  spans and document excerpts from CUAD, OHR-Bench and Indian documents.
- Also tracked: runs/tests/agent/A-LOCAL-20261113-{102,169,236,315}.json, each holding one CUAD question
  (stack.question.text).
- Correction: NOTICE.md (2026-11-15) states, per source, the licence and the tracked files that contain its text, and
  marks unknown licences. For paper-v1.2, 27 result files are un-ignored (numbers, identifiers and setup names only),
  and data/results/aq/answers.jsonl (model answers) stays checksummed but not distributed. No result changes.

## Errata (2026-11-18)
- Duplicated line: "A document is picked at most once, by its source id across all domains (UniDoc lists some
  documents under more than one domain); if a type's largest is already taken, the next largest is picked." appears
  first in H2 and is repeated twice after it (once directly below, once after H4). It is one rule, stated once; the
  old lines stay as written.
- AQ rounding: the held-out AQ comparison against langchain_default is reported above as +0.047 [0.001, 0.099].
  data/results/aq/analysis_held_out_vs_best.csv holds difference 0.0475, interval [0.0015, 0.099]; rounded to 3
  decimals (half up) that is +0.048 [0.002, 0.099], as in the paper table. RESULTS.md now matches the CSV. Holm p
  0.176 and the conclusion (not significant) are unchanged; no result changes.

## RQ3 controls: budget sweep and random floor, design written before running (2026-11-18)
- Question: why does the best chunk size depend on the measure (RQ3)? Test whether large chunks win under fixed k
  only because they read more text. Diagnostic; no earlier result or decision changes.
- Data: tuning documents only (scripts read pdfs/split.csv; no --final), certain span-level main questions (QASPER
  excluded), Docling and pdfplumber, the existing chunks, gold and bge-m3 cache of P3-LOCAL-20261105-4. scorer_v1
  unchanged; hybrid retrieval only (BM25 + bge-m3, RRF k = 60). The embedder is not changed (one factor at a time).
- Settings: the four size-swept families with overlap 0 and no prefix (fixed_token, recursive, langchain_recursive,
  method1_tree) at 256, 384, 512, 640, 768, 896 and 1,024: 28 settings per parser. Superseded *_vNN and sanity
  settings are left out (p4_analyse.in_scope).
- Measures per question:
  1. Recall@B for B in {250, 500, 750, 1,250, 2,000, 4,000} (read_ranking; the last chunk is cut at B). All settings
     are scored at every B; rows where the setting's mean chunk size exceeds B are flagged, not dropped.
  2. Recall@k for k in {1, 3, 5, 10} (top-k chunks, no budget, overlap counted once), as in p3_fixedk, plus the tokens
     read by those k chunks.
  3. Random floor: the same two measures for a random chunk order, averaged over 20 random permutations per question
     (numpy default_rng(42), one generator, settings and documents processed in sorted order).
  4. Lift = measure - its random floor.
- Analysis: document means, then setting means, per parser.
  - Curves: recall against tokens read, one line per size within each family.
  - Test (fixed now): per family and parser, the paired document bootstrap (2,000 resamples, seed 42) of
    (size 256 - size 1,024) at each B and each k, for both recall and lift; Holm over all these comparisons. Reported:
    the difference, its 95% interval and the Holm p.
  - Reported, not tested: per family and parser, the smallest B at which size 1,024 is no longer below size 256
    (the crossover), if any.
- Expected (written before running, not a decision rule): at equal B, 256 is above 1,024 for every B up to 2,000; at
  fixed k, 1,024 is above 256 in recall, and the gap shrinks or reverses in lift.
- Script: scripts/p3_budget_sweep.py; output data/results/p3/budget_sweep_tuning.csv; run record P3-SWEEP-<date>-<n>.
- Amendment before running (2026-11-18): the Holm family is narrowed to the comparisons that test the question:
  per family and parser, (size 256 - size 1,024) in Recall@1,250, Recall@5 and Lift@5 (24 comparisons). All other
  budgets, k values and lifts are reported with their 95% intervals as descriptive, without Holm.

## Licence (2026-11-18)
- An MIT licence was added for the project's own code (LICENSE). It does not cover dataset-derived files, which keep
  their sources' licences (NOTICE.md). This updates "Errata (2026-11-15, distributed data)": "The repository has no
  licence file of its own" is no longer true.

## AQ caveat (2026-11-18), reporting
- The Spearman correlations between answer F1 and Recall@1,250 (tuning 0.75, held-out 0.43; judge 0.75 / 0.64) are
  computed over 7 digital setups only; with 7 points they are weak evidence and are reported without a test.
- method1_tree T256 answers 0.065 token-F1 above T384 on held-out (Holm p 0.025), opposite to the recall tie. The
  question of which of the two is better for answers stays open; the agent's T384 default rests on recall only.

## Scope: planned chunkers not in the final grid (2026-11-18), reporting
- Paragraph group (spec v1.1, 2 paragraphs, 1 overlapping) → not built, never run → not built; no written reason.
  Method 1's A6/A10 fallback packs whole parser blocks but is not this chunker.
- Dynamic token size (spec v1.1, 128 to 512) → not built, never run → not built; no written reason.
- Section + table-aware (spec v1.1, one section per chunk, table-row chunks, no overlap) → not built as a chunker,
  never run; parts of the idea are in method 1 (sections from the tree; tables cut between rows with the header
  repeated, A7) → not built; no written reason.
- Docling HybridChunker (spec v1.1, max 512 bge-m3 tokens, Docling only) → not built, never run → not built; no
  written reason.
- Method 1 cross-references (spec v1.1 "Cross-references") → not built → deferred in rule A11 (this spec, "Own
  method 1", 2026-11-04, before any method-1 result: "not in this version; they are a later, separate variant").
  Cross-references are left to a later method 1 v2, to be tested on tuning documents only against overlap
  (recursive, overlap 0/8/32/64, per extra index token), as spec v1.1 designed. Paper 1 reports one own method.
- The boundary-similarity rule (spec v1.1, "P2-R08") was never applied, as none of these chunkers was built; the id
  P2-R08 was later reused for a locate fix (86ef639).
- Consequence for RQ1: the choice set is narrower than spec v1.1 planned. The NO-GO result holds for the setups
  tested; it says nothing about these four.
- No result or decision changes.

## Extension: the five planned items, built after the main study (2026-11-18), design before any code
- Why: spec v1.1 planned them; they were never built (see the scope note above). Built now as an extension,
  labelled "added after the main study". The frozen RQ1-RQ5 results are not changed or replaced.
- Items, with the settings spec v1.1 planned (kept as written, not re-tuned):
  1. paragraph_group: 2 paragraphs per chunk, 1 overlapping; paragraphs = parser blocks (Docling) or non-empty-line
     groups (pdfplumber, as method 1 rule A13).
  2. dynamic_token: sizes 128 to 512. Its definition is written in a dated note before coding, from the source spec
     v1.1 refers to; if no source is found, our own definition is stated as such.
  3. section_table: one section per chunk from the frozen tree (src/chunk/tree.py v4, top-level sections), table
     rows as their own chunks with the header repeated, no overlap.
  4. docling_hybrid: Docling HybridChunker, max 512 bge-m3 tokens, Docling only (pinned Docling 2.143.0).
  5. method1_tree cross-references (method 1 v2): as spec v1.1 "Cross-references" (labels found in the document's
     own tree, no word lists; the referenced node's label and title attached; counted like the prefix), at T = 384
     and T = 512.
  All share the frozen post-processing (merge under 100 tokens, re-split over 1,024), the bge-m3 tokenizer, no
  heading prefix except where stated.
- Data: tuning documents only (pdfs/split.csv; no --final). Same frozen extractions, gold, scorer_v1, bge-m3
  (new chunk texts embedded with the same model and revision; GPU runs on Kaggle as before).
- Scoring: hybrid Recall@B at 750 / 1,250 / 2,000 (main 1,250), main questions, QASPER excluded.
- Analysis (fixed now):
  (a) each new setup against the tuning best single of P4 (primary scope), paired document bootstrap, S10 tie rule;
  (b) RQ1 extension: p4_analyse on the primary choice set plus the new setups (tuning only), gap and go/no-go
      reported next to the original, not replacing it;
  (c) cross-references: method1_tree v2 against v1 at the same T, and against recursive overlap 8/32/64, as recall
      gain per extra index token (spec v1.1).
  Holm over the comparisons in (a) and (c).
- Held-out: not used. A held-out check is allowed only if a new setup is clearly better on tuning, and only after
  its own design note, as a disclosed further use of the held-out set.
- Amendment before any code (2026-11-18):
  (1) The overlap comparison in (c) is made at T = 512 only, against recursive_size512_overlap8/32/64 (the only
      matching sizes). At T = 384, method 1 v2 is compared with v1 only.
  (2) Method 1 v2 builds on method1_tree_T*_noprefix: chunk text plus the cross-reference text only, no heading
      prefix. Cross-reference tokens count in index cost and budgets like a prefix.
  (3) dynamic_token has no published source (spec v1 gives none). Its definition is our own; it is written in its
      own dated note before coding and stated as our own in the paper.

## RQ3 controls result (2026-11-18), P3-SWEEP-20261118-1
- Design: "RQ3 controls: budget sweep and random floor" with its amendment (Holm over 24 comparisons). Tuning only,
  19 documents with main questions, hybrid retrieval, 28 settings per parser. Diagnostic; no earlier result or
  decision changes. Output data/results/p3/budget_sweep_tuning*.csv.
- Tested, size 256 - size 1,024, per family and parser (8 pairs each), paired document bootstrap:
  - Recall@1,250: +0.113 to +0.203 (256 better in all 8);
  - Recall@5: -0.088 to -0.137 (1,024 better in all 8);
  - Lift@5 (Recall@5 minus its random floor): +0.106 to +0.150 (256 better in all 8).
  All 24 are significant after Holm (largest Holm p 0.036; p shown as 0.000 means below 2/2000 before Holm).
- Reported, not tested: no crossover up to 4,000 tokens in any of the 8 family-parser pairs (size 1,024 stays below
  256 at every budget). The 256 - 1,024 recall difference shrinks with the budget: +0.31 to +0.40 (mean +0.345) at
  250 tokens, +0.11 to +0.20 at 1,250, +0.02 to +0.05 at 4,000.
- Reading: under fixed k, large chunks win in recall because they read more text (3.5 to 4.0 times the tokens at
  k = 5); once the random floor is subtracted the ranking reverses and small chunks are better. This matches the
  expectation written before running.


- Amendment before any score (2026-11-18), paragraph_group: defined for Docling only. pdfplumber gives no paragraph
  units: its extractions have no elements, and every blank line in the pdfplumber tuning texts is a page boundary
  (984 of 984). Under rule A13 (each non-empty line a block), a test on one tuning document
  (cuad_bizzingoinc_20120322_8_k_ex_10_17_7504499_ex_10_17_endorsement_agreement) turned 252 two-line windows into
  6 chunks of about 1,000 tokens, all merged, which is not a paragraph grouping. Decided from structure counts only,
  before any recall was computed. Docling test on the same document: 45 chunks, 106-470 tokens, overlap kept at all
  44 boundaries, 12 chunks changed by the shared merge step.

## dynamic_token: definition before any code (2026-11-18), extension item 2
Our own definition; spec v1 gives the range 128-512 and no source. Fixed before any code or result.
- D1 Units: the parser's blocks (Docling elements; pdfplumber non-empty lines, as method 1 rule A13), split at
  sentence ends (the base's sentence rule). Token counts with the bge-m3 tokenizer, as everywhere.
- D2 Window: from the current start, a cut may fall where the chunk is 128 to 512 tokens.
- D3 Break strength, strongest first: (1) page break or blank line; (2) table start or end, or block end (Docling);
  (3) sentence end; (4) line end. Cut at the strongest kind of break in the window; among breaks of that kind, the
  latest (the largest chunk).
- D4 Unbreakable units: a Docling table, or a block with no sentence end inside, is never cut while it fits in
  1,024 tokens. If the window would cut it, the chunk grows to hold the whole unit (up to 1,024).
- D5 Over 1,024: a table is cut between rows only, the header row repeated in each piece (as method 1 rule A7);
  any other unit at line ends, else by tokens (the base's split_long).
- D6 No break in the window and no unbreakable unit: cut at 512 tokens.
- D7 The last chunk of a document may be shorter than 128. No overlap, no prefix. The shared post-processing
  (merge under 100, re-split over 1,024) applies unchanged.
- D8 Parsers: both. pdfplumber gives no table labels, so D4 applies there only to blocks with no sentence end; this
  is reported, not patched with a table-detection rule of our own.
- D9 Reported with the result: chunk count; mean, median and maximum tokens; how many chunks grew past 512 under D4
  and how many were cut under D5.
- Analysis addition (extension, fixed now): besides the comparisons already planned, dynamic_token, section_table and
  method 1 (v1 and v2) are compared on table questions only (OHR-Bench table evidence, Docling), descriptive with
  95% intervals, no Holm.

- Clarifications before any score (2026-11-18), dynamic_token, from the smoke test (structure only, no recall):
  (1) D3: Docling separates every block with a blank line, so ranks 1 and 2 fall at the same places; on Docling,
      D3 in practice cuts at the latest block end in the window.
  (2) D1: sentence ends follow method 1's rule (method1.SENTENCE_END), the project's existing rule; it also counts
      list labels such as "b." as sentence ends.
  (3) D5: chunks are spans of the original text and dynamic_token has no prefix (D7), so a table header row is not
      repeated in later pieces (as in method1_tree_*_noprefix); pieces are still cut between rows only.
  (4) Cut points use token counts from the whole-text encoding; a chunk re-counted on its own may be 1-2 tokens over
      512 (or 1,024 before the shared re-split). The number of such chunks is reported with D9.
  Test runs reuse run ids inside runs/tests/ (new_run_id does not look there); their file names differ.
- Clarification before any code (2026-11-18), section_table: sections are the top-level nodes of the frozen tree
  (src/chunk/tree.py v4; pdfplumber through rule A13). Each table row is its own chunk; the table's header row goes in
  the chunk's prefix field (as method 1 rule A7), counted in budgets and index cost; no other prefix. Sections over
  1,024 and pieces under 100 tokens go through the shared post-processing unchanged. Both parsers; pdfplumber has no
  table labels, so on pdfplumber section_table is sections only (reported).
- Amendment before any code (2026-11-18), section_table: table-row chunks skip merge-under-100. A row chunk is never
  joined with a neighbour, in either direction; re-split over 1,024 still applies, and every other piece goes through
  the shared post-processing unchanged. Reason: in ohr_finance_jpmorgan_2023q2_10q (tuning, Docling) 97% of the 3,281
  table rows are under 100 tokens (median 35), so the shared merge would turn rows back into blocks of about 1,000
  tokens. Row chunks under 100 tokens are kept and counted (C3 flag), not hidden.

  (4) Span mapping: chunk texts are located in the frozen text in order, whitespace ignored, after removing the
      chunking serializer's list bullet ("- " at a line start). Spans are contiguous: each located chunk runs from
      the end of the previous chunk's span (the document start for the first) to its last matched non-space
      character; the last chunk runs to the document end. Text HybridChunker keeps out of chunk.text (section
      headings) therefore joins the following chunk. This is our mapping choice; coverage is 100%, as for every
      other chunker. On the CUAD tuning document 18 of 18 chunks are located.
  (5) A chunk that cannot be located (e.g. a table serialized as cell triplets) is not repaired: its text falls in the
      gap and joins the next located chunk's span. The number of unlocated chunks and their characters are counted
      per document and reported. No table-specific rule.

## method 1 v2 (cross-references): clarification before any code (2026-11-18), extension item 5
Builds on the Extension design note (item 5) and its amendment (2): method1_tree_T*_noprefix plus cross-reference
text only, no heading prefix; cross-reference tokens count in index cost and budgets like a prefix. Every rule
below uses only the document's own tree (src/chunk/tree.py v4) and text; no word lists, no document-specific rules.

- X1 Cuts: identical to method1_tree v1 noprefix at the same T (rules A1-A13 unchanged; only the prefix field is
  filled). Checked per document: chunk (start, end) lists of v2 and v1 must be equal; any difference stops the run.
- X2 Labels from the tree: each node's label is split into its style (tree.py) and its value with suffix
  ("(3)" -> paren digit 3; "13-A" -> 13-A; "6." -> dotted 6; "FR 9" -> word FR, 9; "CHAPTER II" -> word CHAPTER, II).
  A text match is a candidate reference when its style and value equal those of at least one node other than the
  root, and it is not the node's own label at that node's start.
- X3 Reference forms, all taken from the tree's styles:
  (a) bracketed labels as written: "(3)", "(b)", "(iv)";
  (b) word labels with the tree's own word, any case: "Chapter II", "FR 9";
  (c) compound labels written together are a path, outermost first: "9(6)(b)", "6(1)";
  (d) bare-number labels ("6." dotted, or the number of a word label whose word the text does not use): a number
      counts as a reference only after the document's referring word for that style. The referring word is learned
      from the text: the word that most often stands directly before numbers equal to that style's label values;
      kept only if it stands before at least 2 distinct label values (minimum evidence, not tuned on results); any
      case. Learned per document and parser, and reported (expected on D4: "section"; on D3: "Rule").
  Plural forms and list continuations ("sections 6 and 7", "Rules 6, 9(6)(b), 44") are not followed: only the
  number right after the referring word counts. Stated as a limitation, not patched.
- X4 Chains: two candidate references separated by at most one word, where the later one is of a higher tree level
  ("sub-section (1) of section 4"), are one path, resolved outer first, then inner among the outer node's
  descendants. No connecting word is named.
- X5 Resolution, nearest scope first: start at the deepest node containing the reference; look at that node's
  children, then (one step up) its siblings, then the parent's siblings, and so on to the root. The first level with
  any match decides: exactly one match -> resolved; more than one -> ambiguous, skipped and counted. No match at
  any level -> unresolved, counted. A path (X3c, X4) is resolved outer label first by this rule, inner labels inside
  it.
- X6 Exclusions, counted separately: (a) same chunk: the target node starts inside the referring chunk's span;
  (b) self: the target is the chunk's owner node or one of its ancestors (the chunk is already inside it).
- X7 Text attached: "[refers to: <label> - <title>]", with the node's label as in the tree (end "." dropped) and its
  tree title (at most 80 characters, as tree.py stores it); never the node's text. Several references in order of
  first appearance in the chunk; a target attached once per chunk. Joined with a single space.
- X8 Place and cap: stored in the chunk's prefix field, counted in budgets and index cost (amendment (2)). Cap as
  rule A9: 10% of T (38 tokens at T = 384, 51 at T = 512), bge-m3 tokens; whole references are dropped from the
  last until the prefix fits, and counted. Never cut inside a reference.
- X9 Parsers and settings: Docling and pdfplumber (pdfplumber through rule A13); T = 384 and 512. Names:
  method1_xref_T384_noprefix, method1_xref_T512_noprefix ("noprefix" = no heading path, as in v1; the prefix field
  holds references only). Version 2.0+tree-v4.
- X10 Design documents: rules X2-X8 are checked on D4 (indian_d4_rti_act, tuning) first, then D3
  (indian_d3_fundamental_rules, tuning, different numbering), then D1 (indian_d1, tuning) as the final check, as
  spec v1.1 planned. D2 (indian_d2_ccs_conduct_rules) is held-out and never used. Any rule change after D4 is
  written here, dated, before the D3 run; no change after any recall is computed. The scored run then covers all
  tuning documents, per the Extension design note.
- X11 Reported per document, parser and T: candidate references found; resolved; ambiguous (skipped); unresolved;
  same chunk (excluded); self (excluded); attached; dropped by the cap; learned referring words (X3d); chunks with
  any reference; extra index tokens against v1 (total and per chunk); the cut check of X1.
- X12 Precision check (no score): on D4, Docling, T = 512, 30 attached references drawn at random (seed fixed in
  the run record) are checked by hand against the text: correct target / wrong target / reference to another
  document (e.g. "section 4 of the Official Secrets Act"). The correct-target rate is reported with a Wilson 95%
  interval. References to other documents are a known false-positive source with no word-free rule to exclude
  them; reported, not patched.
- Amendment after the D4 smoke test, before D3 and before any recall (2026-11-18), method 1 v2 (allowed by X10):
  (X5') Resolution: at each ancestor of the referring position, nearest first, search all its descendants (not only
        children) for the label; the first ancestor with any match decides; among its matches the shallowest wins;
        a tie at that depth is ambiguous (skipped, counted). Reason: D4 holds the Act twice and an annex numbered
        again; children-only search left 255-262 of 349-385 references unresolved.
  (X2') A label at the start of a parser block or of a line is never a reference (list labels the tree did not
        adopt as nodes, e.g. D4 "(viii)"-"(xvii)").
  (X4') Chains allow up to two words between the two references ("clause (a) of sub-section (1)").
  The D4 smoke-test records before this amendment are kept in runs/tests/. The X12 hand check is done on the D4
  output after this amendment.


- Decision after the amended D4 smoke test (2026-11-18), method 1 v2: no further rule changes. Known limitations,
  reported not patched: on pdfplumber, repeated sections at the same depth (D4 holds the Act more than once) make many
  references ambiguous (101 of 385); on Docling, dotted references can resolve to schedule entries with the same
  number (at least 30 of 69 checked). Precision is measured by the X12 hand check.

- Decision before any recall (2026-11-18), method 1 v2 (cross-references): not included in the scored extension run.
  Reasons: (1) the notes add the referenced part's title to the referring chunk; for retrieval of gold spans this
  draws questions about the referenced part towards the referring chunk instead, so the method mainly serves answer
  understanding, which Recall@B does not measure; (2) in the X12 hand check the first labelled references were
  mostly wrong targets (schedule entries with the same number); the partial labels are kept as they are (n labelled
  of 30, reported). Code and all test records stay in the repository. A cross-reference variant aimed at answer
  quality, with a better resolver, is left to future work.

- Analysis addition before any score (2026-11-18), extension: every comparison is reported with and without the
  Indian documents (their questions are LLM-generated, 20 of 60 invalid in the GOLDEN_200 check), as in RESULTS.md
  8.6. Part (c) of the analysis (cross-references against overlap) is dropped with method 1 v2.

- Extension run imported (2026-11-19), EXT-KN01 at commit e26e916: 4 chunkers, 6 setups, 25 tuning documents, scores
  P3-EXT-KN01-20261118-2 (frozen scorer_v1). Docling re-conversion: 14 of 25 documents identical to the frozen text,
  11 differ (325 of 4.07M characters, at most 1.15% of one document); docling_hybrid spans are mapped onto the frozen
  extraction, so gold and scorer are unaffected. Known limitation, accepted with no new version: section_table on
  Docling, 1 of 25 files fails Layer 1 (coverage 0.999987; two zero-token chunks from a \x9f control character, three
  such characters uncovered).

- Clarification before any analysis (2026-11-19), extension analysis (scripts/ext_analyse.py): tuning scores
  P3-LOCAL-20261105-4 plus P3-EXT-KN01-20261118-2; hybrid, main questions, QASPER excluded; seed 42, 2,000 resamples.
  Primary choice set: the 26 setups in P4-FINAL-20261106-1_primary_setups.csv. Every part with all documents and
  without source Indian (Holm separately in each).
  (a) Reference: docling/langchain_recursive_size256_overlap0_noprefix (tuning primary best single), also without the
      Indian documents. Per new setup: per-document means on the questions both setups scored; the paired document
      bootstrap of (new - reference) gives the 95% interval and the two-sided bootstrap p (as rq5_parser_compare);
      tie by S10 (tied_with_best on the same resamples). Holm over the 6 setups at Recall@1,250. Recall@750 and @2,000
      descriptive (no Holm); at 750 only setups with fits_750 are reported. One seed-42 generator per variant and
      budget, setups in name order.
  (b) First full, original and primary are replayed on P3-LOCAL-20261105-4 in p4_analyse's order with one seed-42
      generator; the primary result must equal 0.802, gap -0.001 [-0.032, 0.030] (without Indian: P4-NOINDIAN-
      20261114-1, 0.791, gap -0.014 [-0.044, 0.014]). The extension scope (26 + 6 = 32 setups) is the next scope on the
      same generator. Zero cost tables, as robust_no_indian (cost does not enter ties, best single, oracle or gap).
      Go / no-go by the frozen rule (lower end of the gap interval above 0).
  (d) Table questions: p3_sanity.table_questions (Docling questions with at least half of their gold characters
      inside a Docling table element; the rule of the S14 damage test, 112 questions on tuning), restricted to source
      OHR-Bench (107). Docling dynamic_token_noprefix, section_table_prefix, method1_tree_T384_noprefix and
      method1_tree_T512_noprefix on the questions all four scored; Recall@1,250, mean of document means with a 95%
      document bootstrap interval, and the paired differences of each pair; descriptive, no Holm. The OHR-Bench filter
      already leaves out the Indian documents, so (d) is the same in both variants.

- Diagnostics before reading any diagnostic result (2026-11-19), extension, read-only (scripts/ext_diagnostics.py; no
  chunker, rule or score changes; tables in data/results/ext/diagnostics/, no run record, as the supplementary
  analyses). Tuning only; scores P3-EXT-KN01-20261118-2 and P3-LOCAL-20261105-4, hybrid, Recall@1,250, main questions,
  QASPER excluded. Definitions fixed now:
  (1) Rules: each setup's spans are rebuilt from the frozen extraction with the frozen chunker code (no drift in src/
      since e26e916) and must equal the saved chunks (spans, prefixes, token counts); then the rule checks per chunker
      (paragraph_group windows and overlap; dynamic_token D1-D9; section_table sections, row chunks and header
      prefix; docling_hybrid located/unlocated chunks and gap characters, i.e. non-space characters inside a span
      that are not part of its located HybridChunker text).
  (2) Size: tokens per chunk with prefix (mean, median); measured size as RQ2 (p3_size_by_source.measured_sizes).
      Curve per parser over the in-scope settings of P3-LOCAL-20261105-4 plus the new setup, on the questions all of
      them scored: least-squares line of recall on log(measured size) over the existing settings. The new setup is
      "on the curve" when its residual lies within 2 standard deviations of the existing settings' residuals and its
      size inside their size range; the 3 existing settings nearest in size are reported as a model-free check.
  (3) Prefix cost (section_table): prefix tokens per chunk, and per question the prefix tokens read within 1,250 and
      their share of the budget (scorer_v1 reading order).
  (4) Failures (Docling, docling_hybrid and section_table): questions where the setup's recall is at least 0.5 below
      docling/langchain_recursive_size256_overlap0_noprefix; 10 drawn with numpy default_rng(42) from the sorted
      question ids. Per question: the gold chunks (chunks holding gold characters), whether the gold is whole in one
      chunk, the size and hybrid rank of the chunk holding most gold, the same for the reference; recomputed recall
      must equal the stored score.
  (5) Suspicious: empty or zero-token chunks, duplicate spans or texts, chunks over 1,024 tokens (text, and text plus
      prefix), offsets outside the text or text not equal to its span, overlaps (allowed only for paragraph_group),
      and prefixes that are not the header row of the chunk's own table.

## Extension result (2026-11-19), P4-EXT-20261119-2 on P3-EXT-KN01-20261118-2 (tuning)

Analysis by the clarification of 2026-11-19 (scripts/ext_analyse.py, outputs data/results/ext/P4-EXT-20261119-2_*.csv;
the first run P4-EXT-20261119-1 is kept as a test, its CSVs in data/results/ext/tests/). Hybrid, Recall@1,250, main
questions, QASPER excluded; seed 42, 2,000 resamples. Holm p reported as < 0.01 where the bootstrap p is 0.

- (a) None of the 6 new setups beats the tuning best single, docling/langchain_recursive_size256_overlap0_noprefix
  (0.802 in the RQ1 scope; 0.800 on the 886 questions shared with each Docling setup, 0.802 on the 860 shared with
  each pdfplumber setup). Differences new - reference, 95% interval, Holm over the 6:
  | Setup | All documents | Holm p | Without Indian | Holm p |
  |---|---|---|---|---|
  | docling/paragraph_group | 0.791, -0.010 [-0.059, 0.044], tied | 0.710 | 0.772, -0.003 [-0.061, 0.056], tied | 0.940 |
  | docling/dynamic_token | 0.745, -0.055 [-0.108, -0.003] | 0.082 | 0.730, -0.044 [-0.106, 0.015], tied | 0.268 |
  | pdfplumber/dynamic_token | 0.717, -0.086 [-0.170, -0.011] | 0.075 | 0.690, -0.087 [-0.180, 0.004], tied | 0.174 |
  | docling/docling_hybrid | 0.719, -0.081 [-0.122, -0.039] | < 0.01 | 0.699, -0.075 [-0.124, -0.028] | 0.008 |
  | docling/section_table | 0.653, -0.148 [-0.208, -0.078] | < 0.01 | 0.648, -0.127 [-0.197, -0.051] | < 0.01 |
  | pdfplumber/section_table | 0.618, -0.184 [-0.253, -0.119] | < 0.01 | 0.618, -0.158 [-0.228, -0.092] | < 0.01 |
  paragraph_group is tied with the best. docling_hybrid and both section_table setups are significantly lower after
  Holm, with and without the Indian documents. dynamic_token is lower (with all documents its interval excludes 0,
  so it is not tied by S10) but not significant after Holm; without the Indian documents it is tied. Without
  Indian the reference stays the same setup (decided 2026-11-19); the reference recall there is 0.775 (Docling
  questions) and 0.777 (pdfplumber questions). Recall@750 and @2,000 are descriptive, in the same CSV.
- (b) RQ1 extension. The original primary result was reproduced exactly first (26 setups: 0.802, gap -0.001 [-0.032,
  0.030]; without Indian 0.791, gap -0.014 [-0.044, 0.014]). With the 6 new setups (32 setups, 19 documents, 860
  questions) the best single stays docling/langchain_recursive_size256 (0.802, 22 tied) and the gap is +0.001
  [-0.039, 0.042], NO-GO. Without Indian (16 documents, 290 questions): best docling/langchain_recursive_size512
  (0.791, 16 tied), gap -0.016 [-0.048, 0.014], NO-GO.
- (d) Table questions (107, OHR-Bench, Docling, 9 documents), descriptive: method1_tree T512 0.860, T384 0.810,
  dynamic_token 0.779, section_table 0.716. Of the 6 pairwise differences only section_table - T512 excludes 0
  (-0.145 [-0.280, -0.008]).
- Diagnostics (scripts/ext_diagnostics.py, data/results/ext/diagnostics/): no bugs. All 6 setups were rebuilt
  exactly from the frozen code; recomputed recall and tokens read equal the stored scores.
  - paragraph_group, dynamic_token (both parsers) and pdfplumber section_table sit on the RQ2 size-recall curve
    (residuals +0.008, +0.017, -0.014, -0.036; residual SD 0.028 Docling, 0.022 pdfplumber), so their results follow
    from their chunk size. docling_hybrid is also on the curve by the pre-written rule (-0.020).
  - Docling section_table sits below the curve: -0.095 at its measured size (383 tokens) and -0.086 at its
    token-weighted size (413, post-hoc). It has 5,363 one-row chunks (5,171 under 100 tokens) next to 1,270 section
    chunks (all 6,633 chunks: median 100 tokens, max 1,304). On its 211 questions far below the reference, the
    chunk holding most gold has median 1,000 tokens and rank 3 (reference: 234 tokens, rank 1); row chunks are 1,329
    of the 2,538 chunks ranked above it, and 66% of these questions have at least 1,250 tokens ranked above it
    (post-hoc).
  - docling_hybrid caveat: "What was scored is HybridChunker plus our span mapping: 1,383 of 3,400 HybridChunker
    chunks could not be located in the frozen extraction (1,246 of them tables serialised differently) and their
    text was joined to neighbouring chunks, so the result reflects the mapping as much as the chunker; it is not a
    test of HybridChunker as used directly." The other 137 differ by inserted list numbers (70), added markup (33),
    table-of-contents serialisation (20) and other (14); none is found earlier in the text (post-hoc). 844,816 of
    2,452,841 non-space characters (34%) lie in gaps; token-weighted size 610 with 30% of tokens in chunks of 900+
    (post-hoc).
  - Pre-written: rules, sizes, size curve, prefix cost, failures, suspicious checks. Post-hoc (added after the first
    results, tables posthoc_*): token-weighted sizes, causes of unlocated HybridChunker chunks, what ranks above the
    gold chunk.
- Known edge cases, reported not fixed: dynamic_token (Docling) has 1 D5 cut by tokens (a table over 1,024 tokens
  with no row end in the window) and 1 chunk under 128 tokens that is not last (before a table); section_table has
  no prefix cap, so one indian_d1 row carries a 1,056-token header prefix (1,304 tokens with its text, 84% of one
  question's budget; the largest prefix share of any question is 88%, on jpmorgan, 1,102 prefix tokens over 6 row chunks read; mean
  44.8 prefix tokens, 3.6% of the budget); the \x9f limitation (2 zero-token chunks, 3 uncovered characters).
- No frozen result or decision changes; the extension does not use the held-out set.

## LLM chunker cost (2026-11-19), reporting

Gemini tokens of the llm_regex chunking runs that produced the scored tuning chunks: P2-P2-KN03-20261103-13 (run1),
-14 (run2) and -15 (run3), 25 tuning documents x 2 parsers each, one call per document, all stages ok, paid credits
0. The chunk files of all 25 tuning documents name these runs. Not used: the earlier local runs P2-LOCAL-20261102-11,
-12, -13 (Indian documents only, superseded by the KN03 chunks) and the held-out runs P2-P4-KN01-20261105-47, -48, -49
(sealed). Per-document means are over the 19 scored documents (QASPER excluded), next to index tokens and hybrid
Recall@1,250 from P4-LOCAL-20261105-1 (full grid).

| Setting | Parser | Documents | Input tokens | Output tokens | LLM tokens / doc (19) | Index tokens / doc | LLM / index | Recall |
|---|---|---|---|---|---|---|---|---|
| llm_regex_run1 | Docling | 25 | 271,032 | 964 | 10,744 | 35,788 | 0.30 | 0.607 |
| llm_regex_run2 | Docling | 25 | 271,032 | 826 | 10,740 | 35,788 | 0.30 | 0.629 |
| llm_regex_run3 | Docling | 25 | 271,032 | 835 | 10,740 | 35,788 | 0.30 | 0.621 |
| llm_regex_run1 | pdfplumber | 25 | 274,997 | 1,104 | 10,891 | 31,855 | 0.34 | 0.656 |
| llm_regex_run2 | pdfplumber | 25 | 274,997 | 1,136 | 10,893 | 31,855 | 0.34 | 0.651 |
| llm_regex_run3 | pdfplumber | 25 | 274,997 | 1,043 | 10,893 | 31,855 | 0.34 | 0.648 |
| Total | Docling | 75 calls | 813,096 | 2,625 | | | | |
| Total | pdfplumber | 75 calls | 824,991 | 3,283 | | | | |

- Index tokens are equal across the no-overlap chunkers (same text; RESULTS 8.1): over the 37 no-overlap, no-prefix
  setups per parser in P4-LOCAL-20261105-1 (langchain_default left out: it uses LangChain's default overlap, 36,305
  and 32,089) they range 35,788-35,803 per document on Docling and 31,855 on pdfplumber. So the LLM tokens are the only cost difference: by the spec v1.1 cost formula (index
  tokens + LLM input and output tokens) llm_regex costs about 30% more per document on Docling (46,528-46,532) and
  34% more on pdfplumber (42,746-42,748), while its recall is among the lowest (0.607-0.656 against the tuning best
  0.802; the six runs are among the 22 lowest of the 100 full-grid setups).
- Input tokens are the same for all three runs (same prompt and document text); only the output differs.
- This completes the "at what cost" part of the main question for the setups tested: every other tested setup has
  no LLM tokens, so its cost is its index tokens. No result or decision changes.

## Robustness embedder: nomic-embed-text-v1.5, design before any code (2026-11-19)
- Why: spec v1 names nomic-embed-text-v1.5 as the robustness embedder; it was never run (every result rests on
  bge-m3). Question: do RQ1, RQ2 and RQ3 hold with a different dense embedder? Tuning documents only; no held-out use.
- Embedder: nomic-ai/nomic-embed-text-v1.5, revision pinned in the run record, float32, full 768 dimensions,
  normalised, trust_remote_code as the model card requires. Task prefixes as spec v1: "search_document: " before
  every chunk text (prefix + text, as indexed now), "search_query: " before every question. The task prefixes are
  for the embedder only and do not count in token budgets.
- Unchanged: the bge-m3 tokenizer stays the ruler for chunk sizes and budgets (spec v1: the tokenizer never
  switches); chunks, gold, BM25 and scorer_v1 are unchanged. Only the dense ranking changes; hybrid = BM25 + nomic,
  RRF k = 60.
- Setups: (1) the 26 primary setups (RQ1); (2) for RQ3, the four size-swept families (overlap 0, no prefix) at sizes
  256 and 1,024, both parsers: 16 setups, of which the 8 at size 256 are in (1) and the 8 at size 1,024 are new. In
  all 34 setups are embedded. Embeddings on Kaggle GPU (notebook rob-kn01).
- Analyses, fixed now, each repeated as for bge-m3:
  - RQ1: p4_analyse on the 26 primary setups, tuning, hybrid Recall@1,250: best single, tied, split-half oracle,
    gap, go/no-go; also dense-only.
  - RQ2: pooled Spearman of measured size against recall per parser and budget (750 / 1,250 / 2,000), over the 34
    embedded setups (17 per parser, sizes 256-1,024). The bge-m3 RQ2 used every in-scope setting (about 50 per
    parser); for a like-for-like comparison the bge-m3 Spearman is recomputed on the same 34 setups from
    P3-LOCAL-20261105-4 and reported next to it.
  - RQ3: per family and parser, (256 - 1,024) in Recall@1,250, Recall@5 and Lift@5 with the random floor, as the
    budget-sweep note; Holm over these 24.
- "Holds" means, fixed now: RQ1 gives NO-GO; RQ2 size-recall correlations are negative at every budget; RQ3 shows the
  same signs as with bge-m3 (Recall@1,250 > 0, Recall@5 < 0, Lift@5 > 0). Any result that does not hold is reported
  as such, next to the bge-m3 result; nothing replaces it.
- Reported with and without the Indian documents, as in RESULTS 8.6.
- Two corrections to the first draft, made before any code: group (2) adds 8 new setups (the draft said most were
  already in (1)); RQ2 runs on the 34 embedded setups with bge-m3 recomputed on the same set (the draft said the 26
  primary setups, which span sizes 256-512 only, and "exactly as for bge-m3", which used the full grid).
- Clarification before the Kaggle run (2026-11-19), robustness embedder: trust_remote_code is off; the model loads
  through transformers' built-in nomic_bert class, because Nomic's remote code fails on transformers 5.22.1.
  Parity checked on 50 tuning texts against the remote code (transformers 4.x, separate environment): minimum
  cosine 1.0 (50 of 50 vectors bit-identical), identical rankings for 5 questions. No other change to the design.

## ACL paper draft removed (2026-11-20)
The ACL paper draft (paper/) was removed from the repository on 2026-11-20; it is kept at the tags paper-v1.1
and paper-v1.2. The paper will be written in IEEE format, outside the repository, from the study files.

## Robustness embedder result (2026-11-20), P4-ROB-20261120-1 on P3-ROB-KN01-20261119-2
Analysis by the design note "Robustness embedder: nomic-embed-text-v1.5, design before any code (2026-11-19)"
(scripts/rob_analyse.py at 073ef99, outputs data/results/rob/P4-ROB-20261120-1_*.csv). Scores P3-ROB-KN01-20261119-2
(Kaggle, commit ce4f459; vectors P3-ROB-KN01-20261119-1, nomic revision e9b6763); bge-m3 from P3-LOCAL-20261105-4 on
the same setups, its RQ3 from budget_sweep_tuning.csv. Tuning only, main questions (QASPER excluded), seed 42.
- Verdicts: all 16 hold (RQ1 NO-GO hybrid and dense, RQ2 Spearman < 0 at every budget, RQ3 24 of 24 signs as
  expected; for nomic and bge-m3, with and without the Indian documents).
- RQ1 nomic (26 primary setups, Recall@1,250; 19 documents / 860 questions, without Indian 16 / 290):
  - hybrid: best docling/langchain_recursive_size384 0.809 (17 tied), oracle 0.808, gap -0.000 [-0.036, 0.034];
    without Indian 0.809 (10 tied), oracle 0.788, gap -0.020 [-0.056, 0.017]. NO-GO.
  - dense: best docling/recursive_size256 0.758 (11 tied), oracle 0.747, gap -0.012 [-0.056, 0.036]; without Indian
    0.745 (12 tied), oracle 0.723, gap -0.022 [-0.074, 0.035]. NO-GO.
  - bge-m3, recomputed: hybrid docling/langchain_recursive_size256 0.802 (21 tied), gap +0.002 [-0.030, 0.035];
    without Indian docling/langchain_recursive_size512 0.791 (15 tied), gap -0.016 [-0.048, 0.013]; dense
    pdfplumber/langchain_recursive_size256 0.783, gap -0.015 [-0.046, 0.015]; without Indian 0.763, gap -0.026
    [-0.063, 0.008]. All NO-GO.
- RQ2 (pooled Spearman, 34 embedded setups, budgets 750 / 1,250 / 2,000): nomic -0.951 to -0.804, without Indian
  -0.941 to -0.752; bge-m3 on the same 34 setups -0.946 to -0.738, without Indian -0.890 to -0.642. 6 of 6 negative
  in each case. Best sizes: nomic 215-305 tokens (216-304 without Indian), bge-m3 215-404 (216-402).
- RQ3 (256 - 1,024, four families x two parsers, Holm over the 24): nomic Recall@1,250 +0.101 to +0.268, Recall@5
  -0.099 to -0.062, Lift@5 +0.101 to +0.165; without Indian +0.092 to +0.258, -0.114 to -0.071, +0.111 to +0.179.
  bge-m3 +0.113 to +0.203, -0.137 to -0.088, +0.106 to +0.150; without Indian +0.095 to +0.186, -0.156 to -0.104,
  +0.117 to +0.159.
- The bge-m3 RQ1 row is recomputed in a fresh random stream (the primary scope run alone), so its oracle and gap
  differ slightly from P4-NOINDIAN-20261114-1 (same best single, same decision); the bge-m3 RQ3 tests reproduce the
  stored results exactly. (P4-NOINDIAN-20261114-1, primary: oracle 0.801, gap -0.001 [-0.032, 0.030], 20 tied;
  without Indian oracle 0.777, gap -0.014 [-0.044, 0.014], 15 tied.)
- Without the Indian documents some comparisons have Holm p above 0.05: bge-m3 5 of 8 Lift@5 comparisons
  (0.055-0.069); nomic 3 Docling comparisons (langchain_recursive Recall@5, method1_tree Recall@1,250 and Lift@5,
  0.066 each). All their 95% intervals exclude 0. The "holds" rule is about signs, as fixed in the design, so no
  verdict changes.
- Conclusion: RQ1, RQ2 and RQ3 hold with nomic as the dense embedder. Nothing replaces the bge-m3 results; no frozen
  result or decision changes.


## Agent test 4 (scaled): unseen documents with gold answers, design before running (2026-11-20)
- Purpose: test the released tool (spec/agent_v1.md) on documents the study never used. A test of the tool, not a
  research claim; the study's sealed held-out set is not used.
- Scanned: MP-DocVQA validation split, documents eligible by the rules of scripts/rq5_scanned_select.py (one page list
  across a document's questions, 10-20 pages, at least 3 questions), excluding every document in pdfs/split.csv,
  pdfs/scanned_picks.csv and pdfs/agent_test_picks.csv. 50 documents drawn with seed 42; 3 questions each (seed 42).
  PDFs built as rq5_scanned_build.py does.
- Digital: CUAD contracts not in pdfs/catalog.csv, 50 drawn with seed 42; 3 questions each from those with a gold span
  that occurs once (the P1 CUAD rule), seed 42.
- Run: batch mode, thorough (Docling), budget 1,250, the provider list in its order; laptop CPU, or Kaggle if the
  OCR time is too long.
- Reported: token F1 and "contained" against the gold answers (scripts/aq_run functions), "not found" count; time per
  page for scan check, parse/OCR, chunk and embed; answer time; peak memory; failures (documents that could not be
  processed, with the error). Digital and scanned reported separately.
- The drawn document lists are saved to pdfs/agent_test4_picks.csv and never enter split.csv or catalog.csv.

## Held-out set 2 (replication), design before any document is opened (2026-11-20)
- Purpose: replicate RQ1 and RQ2 on new documents, to narrow the RQ1 interval (limitation G4) and give per-source
  results where held-out 1 had 1-3 documents (G5). Held-out 1 (P4-FINAL-20261106-1) is kept and reported as is;
  held-out 2 is reported next to it, never replacing it.
- Sources (span-level gold only):
  - CUAD: 30 contracts, by the P1 eligibility filter and gold rule (answers kept only if they occur once), at least
    5 such questions per contract.
  - OHR-Bench: 20 documents from the domains used on tuning (academic, administration, finance, law, manual), text
    and table evidence only (p1_ohr_select.USABLE_SOURCES), at least 5 questions per document.
  - Excluded: every document in pdfs/split.csv, pdfs/catalog.csv, pdfs/scanned_picks.csv, pdfs/agent_test_picks.csv
    and pdfs/agent_test4_picks.csv (by source id and SHA-256).
  - Drawn from the eligible lists with seed 42 using dataset metadata only; no PDF is opened before it is picked.
- Split: rows added once to pdfs/split.csv as held_out_2; sealed. Scripts refuse it without --final; every step runs
  on it once.
- Pipeline, unchanged and frozen: pdfplumber extraction (P1 script) and Docling extraction (pinned 2.143.0, Kaggle
  GPU, as P1-KN06); gold by the P1 certain rules and the frozen drop rule; the 26 primary setups (spec v1.2 held-out
  plan); bge-m3 embedding; scorer_v1; p4_analyse as committed.
- Primary analysis, fixed now: RQ1 on held-out 2 alone, hybrid Recall@1,250, primary choice set: best single, tied
  set, split-half oracle (200 splits), gap with 95% document bootstrap interval; go/no-go by the frozen rule (GO only
  if the lower end of the gap interval is above 0). Also reported: the setup chosen on tuning
  (docling/langchain_recursive_256) and the held-out-1 best single (pdfplumber/method1_tree_T384), applied
  unchanged.
- Secondary, fixed now: (a) RQ1 pooled over held-out 1 and 2 (67 documents if all are scorable); (b) RQ2
  size-recall curve per source (CUAD, OHR-Bench) on held-out 2; (c) with and without nothing else (no Indian
  documents in held-out 2).
- Reported: documents and questions kept and dropped (gold-drop rate per parser), as for held-out 1.