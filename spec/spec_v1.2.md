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