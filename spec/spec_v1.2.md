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

## Agent spec (2026-11-13)
The agent design is in spec/agent_v1.md.

## Question numbering (2026-11-13)

For the README and the paper, existing work is labelled RQ1-RQ4; RQ5 keeps its spec number. RQ1 = the main question
(P4); RQ2 = chunk size and chunker at a fixed budget, overall and per source (P3, size-by-source report); RQ3 = effect
of the metric on the best size (fixed-k diagnostic); RQ4 = answer quality (AQ). These are labels for work already
designed and run, not new questions; no analysis changes.