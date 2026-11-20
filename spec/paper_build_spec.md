# Paper 1 build spec (draft for approval, revised 2026-11-14)

> `paper/`: removed 2026-11-20; see tag paper-v1.2. Every `paper/` path below refers to that tag.

Paper 1 is the chunking study (RQ1–RQ5) in ACL LaTeX format. This spec fixes how `paper/` is built. Nothing outside
`paper/` changes, except this file.

## 0. Decisions so far (author, 2026-11-14)

1. The author adds the §8 inputs to `docs/paper_checksums.txt` and tags `paper-v1.1` after re-running reproduction on
   §8. Phase 2 waits for that tag. The generator then verifies against the extended checksum file.
2. Markdown-only numbers: recompute where possible (see §6). Only what can't be recomputed goes in
   `paper/data/manual_facts.csv`, with a source column.
3. Figures in pgfplots.
4. RQ3: option (a). The P4 rule (superseded `*_vNN` settings left out, `in_scope`) is applied **in
   make_artifacts.py**; `fixedk_tuning.csv` stays as it is. An erratum in spec_v1.2.md and a RESULTS.md §7 change
   are drafted for the author before anything is written.
5. ACL style files at d5adc82 with the file list in §1: approved. aclpubcheck in `paper/.venv-pubcheck`: approved
   for Phase 2.
6. Read access to `scanned_rq5` files: no choice made (the request carried the placeholder "[allow / don't
   allow]"). Not read; the §3 numbers stay in manual_facts.csv until the author allows it.

## 1. Layout

```
paper/
  acl/                    official ACL style files, unmodified, from github.com/acl-org/acl-style-files at commit
                          d5adc823ff0f80f98c80405ca0ab66c68e684409 (2026-06-29, master head on 2026-11-14):
                            acl.sty (11,615 B), acl_natbib.bst (45,442 B)            used by the build
                            acl_latex.tex (14,533 B), formatting.md (17,923 B), README.md (2,417 B)   reference only
                          not copied: acl_lualatex.tex, custom.bib, anthology.bib.txt, tests/, .github/
                          SOURCE.txt: repository URL, commit, the SHA-256 of each copied file. The repository has
                          no LICENSE file (the GitHub API reports none); recorded in SOURCE.txt.
  main.tex                \documentclass[11pt]{article}; acl in review or final mode (§4); \input of sections and
                          generated files only
  sections/
    abstract.tex  introduction.tex  related_work.tex  method.tex  results.tex
    discussion.tex        "Discussion and Conclusion" (the conclusion closes the main text)
    limitations.tex       "Limitations" (unnumbered; required)
    ethics.tex            "Ethical Considerations" (unnumbered)
    appendix.tex
  references.bib
  data/manual_facts.csv   the only typed numbers, each with a source (§6)
  scripts/make_artifacts.py
  generated/
    tables/               *.tex table bodies; numbers.tex (one \newcommand per inline number)
    figures/              *.tex pgfplots figures, coordinates written inline
    MANIFEST.txt          every generated file with its SHA-256 and the inputs it came from
  Makefile                targets in §4
  .gitignore              `!data/` first (the root .gitignore's `data/` also matches paper/data/; tested), then build
                          products (*.aux, *.log, *.pdf, ...) and .venv-pubcheck/
```

## 2. Generator rules (paper/scripts/make_artifacts.py)

- **Inputs:** only frozen result files listed in `docs/paper_checksums.txt` (extended at `paper-v1.1`; the tag the generator checks is `paper-v1.2`, §10), plus
  `paper/data/manual_facts.csv`, which the generator hashes into MANIFEST.txt. The input list sits in one constant
  in the script, so it can be reviewed.
- **Checksums:** before reading anything, every input is checked against `docs/paper_checksums.txt`. A missing
  entry or any mismatch makes it exit non-zero with the path and both hashes, and nothing is written.
- **Outputs:** it writes only to `paper/generated/`. It writes to a temporary folder first and then replaces, so a
  failed run leaves the old outputs.
- **Determinism:** two runs give byte-identical output.
  - No timestamps, no absolute paths and no random state.
  - Rows are sorted explicitly, with a fixed float format (3 decimals unless a table says otherwise) and `\n` line
    endings.
- **No hand-typed numbers:** every result number comes from a generated file. Inline numbers are macros in
  `generated/tables/numbers.tex` (for example `\RQoneGap`, `\RQoneGapCI`). Numbers from `manual_facts.csv` become
  macros as well, and their source is written as a comment next to each macro.
- **Reuse:** the generator reuses the study's functions where a number is derived (`holm`, `wilson`, the Spearman of
  F1 and recall over setups). It doesn't re-run any analysis, and it reads no document file, only result files and
  records.
- It runs as `python -m paper.scripts.make_artifacts` from the repo root (`paper/__init__.py` and
  `paper/scripts/__init__.py` are empty).

## 3. Planned outputs and their sources

### Main text

| Output | Content | Source file(s) |
|---|---|---|
| Table 1, RQ1 | Held-out primary: best single, ties, oracle, gap [95%], decision; full and original grid gaps; the tuning winner's held-out rank | `runs/P4-FINAL-20261106-1.json` (stack.summary), `data/results/p4/P4-FINAL-20261106-1_primary_setups.csv` |
| Figure 1, RQ2 | Recall@B against measured chunk size, one panel per parser, lines per source; B = 750 / 1,250 / 2,000; tuning, with held-out OHR-Bench as a second row if it fits | `data/results/p3/size_by_source_P3-LOCAL-20261105-4.csv`, `size_by_source_P3-FINAL-20261106-1.csv` (+ the summary CSVs for rho and best size) |
| Figure 2, RQ3 | Metric flip: best size per measure (Recall@5 / @10, Hit@1, MRR at fixed k; Recall@4,000 tokens) | `data/results/p3/fixedk_tuning.csv`, filtered in make_artifacts.py with `scripts.p4_analyse.in_scope` (50 of 63 settings; §7) |
| Figure 3, RQ5 | (b) tuned size against default per family × parser, held-out difference with 95% interval and Holm marker; (a) digital variants against default | `data/results/rq5/P5-LOCAL-20261110-2_chunker.csv`, `P5-LOCAL-20261110-1_digital.csv`; scanned from `P5-LOCAL-20261111-1_scanned.csv` |
| Table 2, RQ4 (AQ) | Held-out F1 best setup and differences with intervals and Holm p; tuning summary; Spearman F1 against recall (tuning, held-out; judge secondary) | `data/results/aq/analysis_held_out.csv`, `analysis_held_out_vs_best.csv`, `analysis_tuning*.csv`, `analysis_scanned*.csv` |
| Inline numbers | Sanity tests, gold coverage, document accounting | `runs/P3-LOCAL-20261105-1.json`, `runs/tests/test_p3_sanity_floor_damage.txt` (text log, parsed); `data/results/p3/gold_drop_*.csv`; accounting as in §6 |

### Appendix (RESULTS.md §8; inputs checksummed at `paper-v1.1`)

| Output | Source file(s) |
|---|---|
| A1 Index cost at T384 (§8.1) | `data/results/p4/P4-LOCAL-20261105-1_full_setups.csv` (written by the p4_v2 record in `runs/`, which overwrote the dev run's files), `P4-FINAL-20261106-1_full_setups.csv` |
| A2 BM25-only / dense-only (§8.2) | `data/results/supplementary-20261114/retriever_summary.csv` |
| A3 Pre-registration timeline (§8.3) | `supplementary-20261114/github_activity_page{1,2}.json` (push times); commit times by `git show -s --format=%cI <hash>` for the listed hashes (content-addressed, so verified by the hash itself); run times from the listed records |
| A4 Datasets and licences (§8.4) | prose, not results; each licence cited in `references.bib` with its page |
| A5 Compute (§8.5) | `supplementary-20261114/compute_summary.csv` |
| A6 Without the Indian documents (§8.6) | `p4/P4-NOINDIAN-20261114-1_*.csv`, `P4-FINAL-NOINDIAN-20261114-1_*.csv` and records |
| A7 GOLDEN_200 validity (§8.7) | `data/results/golden_check/labels.csv`, `sample.csv` (Wilson via `scripts.golden_check.wilson`) |
| A8 Full setup tables (optional) | `P4-FINAL-20261106-1_{full,original,primary}_setups.csv` |
| A9 Deviations and errata | prose from the spec's Errata notes and deviation notes; numbers through macros |

## 4. Format rules (ACLPUB formatting guidelines, updated January 2025)

Source: acl-org.github.io/ACLPUB/formatting.html, read 2026-11-14. The page carries no date. The ARR author
checklist dates the update to January 2025 and names its points: font size in figures and tables, placement of
Limitations and Ethical Considerations, and two-column appendices.

- **Review / final switch:** `make pdf` builds the review version (`\usepackage[review]{acl}`: anonymous, line
  numbers, page numbers). `make pdf MODE=final` builds the camera-ready version (`\usepackage{acl}`). The Makefile
  passes the mode to LaTeX through `latexmk -usepretex`, which defines `\PaperModeFinal`. main.tex holds the only
  `\ifdefined` switch. The acknowledgements are included only in final mode. Output: `paper/build/main-review.pdf`
  and `main-final.pdf`.
- **Page limits:** long paper, 8 pages of content in review, 9 in final. Limitations, Ethical Considerations,
  references and the appendix are outside the limit. All main-text figures and tables count.
- **Order after the main text:** Discussion and Conclusion → Limitations → Ethical Considerations → (Acknowledgments,
  final only) → References → Appendix. There are no page breaks before Limitations and Ethical Considerations.
- **Limitations:** a section titled exactly "Limitations". It holds no new results, figures, tables or analyses.
  Every number in it is a macro that already appears in the main text or the appendix, and `make check` verifies
  this. Content: 17 scorable held-out documents; coverage loss (§6); Hindi and UniDoc out of scope; LLM-generated
  Indian gold with the A7 result; one LLM judge as a secondary measure; one rater for the GOLDEN_200 check.
- **Ethical Considerations:** an unnumbered section with no new experiments, figures or analyses. Content: dataset
  licences (two CC BY-NC sources, research use, derived files not redistributed); public documents only, no
  personal data; LLM use in the study (answering model, judge, chunkers); AI assistance in code and writing (ACL
  policy on AI writing assistance).
- **Appendix:** two-column, like the main text. It has no `\onecolumn`; wide tables use `table*`. The appendices are
  lettered (A, B, ...) and come after the references.
- **Figure and table fonts:** "whenever possible, please use the font size of the document text" (11 pt), and text
  must be readable on A4.
  - pgfplots default style: `font=\normalsize` for tick labels, axis labels and legends.
  - A figure may use `\small` (10 pt, the caption size) only where 11 pt can't fit. Each such case is listed in a
    comment in the figure file with the reason; nothing goes below `\small`.
  - Tables use `\normalsize`. `\small` is allowed only for the wide appendix tables, and never smaller.
  - `make check` greps for `\footnotesize`, `\scriptsize`, `\tiny`, `\resizebox` and `\scalebox` in sections and
    generated files, and fails on any hit.
- **Grayscale:** lines differ by mark and dash pattern as well as colour. Captions go below, at 10 pt (the template
  default).

## 5. Build and checks

- **Tools:** `latexmk -pdf` with pdflatex and bibtex (natbib, `acl_natbib.bst`). Not installed. Ubuntu 26.04
  command, not run: `sudo apt install latexmk texlive-latex-extra texlive-fonts-recommended texlive-bibtex-extra`.
  This also pulls in texlive-pictures (pgfplots). The optional `inconsolata` is in texlive-fonts-extra (about
  1.8 GB).
- **aclpubcheck:** github.com/acl-org/aclpubcheck (MIT, Python ≥ 3.10; head fb584f3 on 2026-11-04). Installed into
  `paper/.venv-pubcheck/` (gitignored), pinned to a commit, so the study's `.venv` stays unchanged. Installing it
  is a download, asked for in Phase 2.
- **Makefile targets:**
  - `make artifacts`: runs the generator.
  - `make pdf [MODE=review|final]`: builds the PDF.
  - `make check` runs, in order:
    1. the generator twice into temporary folders, comparing the outputs byte for byte;
    2. the checksum verification (the generator's own);
    3. the no-typed-numbers grep on `sections/*.tex`, with an allowlist for "Recall@1,250"-style metric names,
       years and section numbers;
    4. the Limitations number check;
    5. the font grep (§4);
    6. `aclpubcheck --paper_type long` on the review PDF and the final PDF. Any reported error fails the check;
       warnings are printed.

## 6. Markdown-only numbers: recomputed or manual

| Number (RESULTS.md) | Result | Source used |
|---|---|---|
| §6 held-out documents 31 → 17; removals 2 / 9 / 3; left 8 / 6 / 3 | **Recomputed.** Exactly as RESULTS.md and the spec state. | `pdfs/split.csv` (31 held-out by split and source_dataset); `P4-FINAL-20261106-1_primary_documents.csv` (17 documents; split × source); `runs/P4-FINAL-20261106-1.json` (`documents_left_out: []`); `runs/P3-FINAL-20261106-1.json` (`page_level_gold_left_out` 76 / 76). `pdfs/split.csv` needs to be in the extended checksum file. |
| §5 judge check, first pass: 70% agreement, kappa 0.48, 12 disagreements, 11 of them human 0.5 / judge 1 | **Can't be recomputed.** `judge_check.csv` has one version in git (a6278ca), identical to the working copy and already the second pass (human 1.0 × 31, 0.0 × 8, 0.5 × 1). The labels were edited in place (a LibreOffice lock file from 11-13 sits next to the file). No other copy exists in `data/`, and the spec doesn't say which cases changed. | → manual_facts.csv; source: spec_v1.2.md note "AQ judge check (2026-11-12)", first committed in a6278ca. The second pass (95%, kappa 0.86) is recomputed from `judge_check.csv` and `judgements.jsonl`. Deduction gives kappa 0.451 or 0.465, not the recorded 0.48 (spec_v1.2.md note "AQ judge check: first-pass labels overwritten in place"). |
| §3 scanned gold placement: Docling 49 exact / 47 certain, Tesseract 41 / 43, pdfplumber 0 | **Not attempted.** Recomputing needs the gold and extraction files of `scanned_rq5` documents, which CLAUDE.md doesn't allow me to read without your permission in the session. | → manual_facts.csv; source: "Correction to RQ5(a) scanned results" (2026-11-11), commit 3d5407e |
| §3 `ocr_rapidocr` / `ocr_scale_double` byte-identical to the default | **Not attempted**, for the same reason. | → manual_facts.csv; source: RQ5(a) result note (2026-11-10), commit 7733597 |
| §8.3 timeline | Generated (§3 A3). | — |
| §8.4 licences | Prose with citations, no numbers. | — |

`paper/data/manual_facts.csv` (created 2026-11-14) columns: `key, value, unit, section, source_file, source_commit, note`. It holds 10 rows:
- the judge's first pass: agreement, kappa, disagreements, and the 11 of 12;
- the scanned placement: Docling exact and certain, Tesseract exact and certain, pdfplumber 0;
- the OCR identity.

## 7. RQ3 figure: what the errata say (decided: option a)

- **The errata say nothing about fixed-k.** Neither the 2026-11-12 nor the 2026-11-14 errata mention fixed-k, RQ3,
  `_prefix_v11` or superseded settings (they cover Holm p, rti_act_en, the RQ5(a) scanned numbers and the 306–308
  sample size).
- **The relevant rule** is in "Method 1 v1.2: A9 cap on the whole prefix (2026-11-05)": old prefix outputs are kept
  as `*_prefix_v11`, re-made and re-scored, and "P4 leaves out superseded *_vNN folders" (`in_scope` in
  p4_analyse). The fixed-k run didn't apply it: `fixedk_tuning.csv` has 63 settings, including 4 `_v10` and 7
  `_prefix_v11`, plus 2 sanity chunkers that `in_scope` also drops (13 out, 50 in).
- **Effect** (computed read-only; document means then setting means, as p3_fixedk does):
  - pdfplumber: unchanged.
  - Docling Recall@5 and @10: unchanged (fixed_token 1024 0.904; 896 0.964).
  - Docling Hit@1: T512_prefix_v11 0.624 becomes method1_tree T384 0.622.
  - Docling MRR: T1024_prefix_v11 0.743 becomes method1_tree T1024 0.742.
  - Docling Recall@4,000: T384_prefix_v11 0.932 becomes T384_prefix 0.925.
  - The metric flip itself is unchanged: large chunks win at fixed k, small ones at an equal token budget.
- **Options:**
  - (a) apply the P4 rule, in scope only (50 settings), and add an erratum noting that the §7 Docling Hit@1 / MRR /
    Recall@4,000 winners are superseded settings. The erratum is the author's to write.
  - (b) keep all 63 as RESULTS.md reports them, with the `_v11` points marked.

## 8. Phase 2 state (2026-11-14), skeleton built; no real results read

- Built: `paper/acl/` (d5adc82; each file's git blob hash checked against the commit's tree; SOURCE.txt),
  `main.tex`, `sections/` (headings and float slots only), an empty `references.bib`, `data/manual_facts.csv`,
  `scripts/make_artifacts.py`, `scripts/check_sources.py`, `tests/test_make_artifacts.py`, `Makefile`,
  `.gitignore`, and `.venv-pubcheck/` (aclpubcheck at fb584f3, gitignored).
- Generator guard: `make_artifacts` refuses to run unless the tag `paper-v1.1` exists and `docs/paper_checksums.txt`
  equals its tagged version. Then every input is verified by checksum. The guard and verification are tested in a
  temporary git repository; on the real repository it refuses ("not frozen yet") and reads nothing.
- Builders (tested on fake data):
  - Table 1 (RQ1), Figure 1 (RQ2), Figure 2 (RQ3, `in_scope` filter), Table 2 (RQ4) and Figure 3 (RQ5);
  - coverage and the held-out accounting (§6);
  - A1, A2, A5, A6, A7;
  - the manual facts as macros, each with its source.
- Not built yet: A3 (timeline), A4 (prose), A8 (optional), A9 (prose), and the inline sanity-test numbers (parsing
  `runs/tests/test_p3_sanity_floor_damage.txt`). These are planned; their inputs are in the checksum list.
- **RQ4 Spearman:** `aq_run --stage analyse` computes it on the answers that have a Recall score. No function returns
  it, and `analysis_*.csv` averages over all answers, so the generator repeats those steps. This is why it reads
  `answers_f1.csv`, `judgements.jsonl` and the two P3 score files (all checksummed).
  `test_real_numbers_match_results_md` compares 22 numbers with RESULTS.md after the tag; it is skipped before.
- **aclpubcheck always exits 0.** `make check` therefore fails on its summary line ("We detected N error(s)", N ≥ 1)
  or on any parsing error, and keeps the report in `build/pubcheck-<mode>.txt`.
- **No-typed-numbers allowlist** in `check_sources.py`:
  - the arguments of `\label`, `\ref`, `\input`, `\generated` and `\cite`;
  - Recall@…, Hit@…, R@…, RQ1–RQ5, BM25, F1 and 95\% (the interval level only).
  Section text was reworded where a heading carried a number ("Index Cost at Equal Chunk Size"; "the first batch").
- Not done: the PDF compile. latexmk and TeX Live are not installed (§5). The empty `references.bib` may make
  bibtex fail on the first compile; that is to be checked then.

## 9. Layout fixes after the first real build (2026-11-14, approved by the author)

- **One short-name scheme** (`short`, `short_family`, `short_variant`, `short_document` in make_artifacts.py), used in
  every table and figure: parser letter / setting code. Examples: `P/M1-384`, `D/LC-256`, `P/M1-256+p` (heading
  prefix), `D/Rec-256o64` (overlap), `D/LC` (a family), `D/ocr off` (a parser setting), `D3` (a GOLDEN_200 document).
  The generator refuses a short name that would stand for two full names. A generated appendix key
  (`tables/key.tex`, Appendix "Key to Short Names") lists every short name used, once each, grouped by kind. Inline
  macros in numbers.tex keep the full readable names.
- **Tables:** shorter headers. RQ1 drops the Docs and Q. columns, because they are the same in every choice set; the
  generator checks this and the caption gives them through \RQoneDocuments and \RQoneQuestions. A6 groups its rows
  under Tuning and Held-out subheadings that carry documents / questions. A7 is a `table*` and keeps its
  invalid-or-unsure column. Nothing uses \small; the rule is enforced by check_sources (`% small: <reason>` required on
  the same line).
- **Figures** at \columnwidth (scale only axis):
  - RQ2 and RQ5 have their panels stacked;
  - RQ3 has angled tick labels;
  - RQ5 uses fixed-point ticks.
- **make check** builds both PDFs and runs aclpubcheck on the final PDF only. The review PDF's line and page numbers are
  review features that pubcheck counts as margin errors.
- **Skeleton artifact:** while the sections hold only headings, about 25 headings in a row form one unbreakable block.
  This gives an over-tall column (LaTeX "Overfull \vbox") and one pubcheck bottom-margin error on page 2. Checked in a
  scratch copy: with one sentence after each heading the same build has 0 overfull boxes and pubcheck reports
  "All Clear!". The error goes away once the sections have text.

## 10. paper-v1.2 (prepared 2026-11-15; not tagged)

- The generator checks the tag `paper-v1.2` (`TAG` in make_artifacts.py; the tests, Makefile and main.tex name no tag
  or follow `TAG`). Sections 0 and 8 keep `paper-v1.1` as the record of that step.
- Until the author tags `paper-v1.2`, `make artifacts` (and so `make pdf`) refuses to run: the tag is missing, and
  `docs/paper_checksums.txt` no longer equals its `paper-v1.1` version (header note on answers.jsonl).
- What the tag adds: 27 of the 28 checksummed result files that were git-ignored at `paper-v1.1` are un-ignored in the
  root .gitignore (only their parent directories under data/results/ are re-included; data/ holds nested git
  repositories). `data/results/aq/answers.jsonl` stays checksummed but not distributed. NOTICE.md lists each source's
  licence and the tracked files that contain its text.
- The generator reads spec_v1.2.md as tagged, so the 2026-11-15 notes reach the deviations table only after the tag.
- What the tag freezes (2026-11-15): the result files (through the checksum file), docs/paper_checksums.txt, spec_v1.2.md
  (read as tagged), the study code under src/ and scripts/p4_analyse.py and scripts/aq_run.py (the generator imports
  constants from both): `CODE_AT_TAG`, compared with `git diff` against the tag; an untracked, not ignored file under
  these paths also stops the generator. Paper code is not compared, so it can change without a re-tag. Before this,
  five files were compared: three under src/ plus the two scripts.
- A3 (timeline) reads the paper-v1.2 event from git: the tag's commit and its commit time
  (`git show -s --format=%cI paper-v1.2^{commit}`). RESULTS.md section 8.3 gets no typed row for it.
