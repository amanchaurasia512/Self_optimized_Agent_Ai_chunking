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