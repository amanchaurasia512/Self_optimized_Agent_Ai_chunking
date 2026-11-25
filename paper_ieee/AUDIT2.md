# Second full audit of paper_ieee (2026-11-25, at d2cae0f, report only)

Abbreviations: M, R, I, D, C, L, W, V = sections/method, results, intro, discussion, conclusion, limitations, related, availability (.tex);
S = spec/spec_v1.2.md; RES = RESULTS.md. Only this file was written; builds and generator ran in scratch copies.

**Verified clean:** generator re-run byte-identical to `generated/`; docs/paper_checksums_v1.3.txt verifies; isolated build from clean exits 0,
no `??` or `[?]`, no undefined references; all 39 bib entries are cited and all cites resolve; every table and figure is referenced; caption
placement passes; RQ1-RQ5 defined; no placeholders or empty sections; repository public, tag paper-v1.3.2 and a held-out 2 result file reachable.

## MUST

| ID | Location | Problem | Evidence | Fix |
|---|---|---|---|---|
| A01 | main.tex abstract; I (paragraph after RQ list); M:5-6, 14 | "Design, scorer and decision rule were fixed before held-out data were scored", "fixed the design before any held-out question, answer or score was seen": true for RQ1 only. RQ3 (12 Nov), RQ5(a) (8 Nov), RQ5(b), AQ, and the RQ2 rule were designed after held-out set 1 was scored, and set 2's gold rule changed after its gold counts; set 2 queries were filtered from metadata. | S:215, 250, 269, 325, 1427, 1487; M:105-109, 248-285 | Say "the RQ1 design, scorer and decision rule ... before held-out set 1 was scored". |
| A02 | I: "If an oracle ... cannot beat ... a chooser that does not see them is unlikely to" | Uses the gap as a bound, which Method and Limitations deny (both biases push the gap down). Same point: "much of that loss could a choice recover" (I, M:3-5). | M:227-231; L:14-16; scripts/p4_analyse.py:72-104 | Replace with "we test a chooser that selects on these few questions". |
| A03 | I contribution 2; C ("Small chunks tend to retrieve best at a fixed budget") ; D ("small chunks tend to win") | No limit to 750 and 1,250 tokens; at 2,000 it is not established on set 2 and is positive in two corpora. Abstract and Results have the limit. | R:69-70, 93-99 | Add "of 750 or 1,250 tokens" in I and C. |
| A04 | abstract last sentences; I RQ5 and contribution 3; C | RQ5(b) is post-hoc (second use of set 1), not said in any of them; "tuned ... beat library defaults" is wrong for three of four families (own 512 start). One library only. | M:268-274; R:201-214; S:250-258 | Flag post-hoc; "a library default (LangChain)". |
| A05 | R:111-112; tab:rq3err caption | "13 superseded settings are left out": 11 are superseded and 2 are sanity chunkers. | S:452-455 | "11 superseded and 2 sanity settings" as macros; caption likewise. |
| A06 | M:90-91 | "For held-out set 1 the evidence is the answer string given by each source": wrong for FinanceBench (evidence_text) and OHR-Bench (text and table evidence); Indian uses verbatim evidence. | S:185-190; RES §8.4 | "the evidence or answer span given by each source". |
| A07 | M:112-113 | "A parser that places more gold, as Docling does": on set 2's primary gold pdfplumber keeps more (248 vs 237), as the same section reports. | M:99-100 | "as Docling does on held-out set 1". |
| A08 | D, first paragraph | "With more setups ... the oracle does worse, not better": contradicted by the tuning extension (32 setups: +0.001 vs -0.001). "Adds more noise than it removes" was not tested; "differences between them are small" fails for set 1 (tied setups span 0.715 to 0.772). | R:237; RES §1, §9 | State as held-out set 1 observation; drop the noise claim. |
| A09 | whole | 16 pages in IEEEtran conference class; typical IEEE conference limits are 6-8 pages. Desk-reject risk unless the target is a journal or has no limit. | main.tex:1; pdfinfo | Move appendix to a supplement or switch class/venue. |

## SHOULD

| ID | Location | Problem | Evidence | Fix |
|---|---|---|---|---|
| B01 | Title | "Size, Budget, and Parser" matter: parser settings show no effect; parser choice is untested except scan detection. | R:188-199; RES §3 | Retitle or soften. |
| B02 | abstract, I, C | RQ3 reversal is tuning-only; its ranking part is descriptive and its causal reading rests on a tuning control. Not said. | M:181-186; R:126 | Add "on tuning data". |
| B03 | I: "the main result is replicated" | Set 2 replicates the NO-GO decision; its interval is wider and the gold rule changed. | R:29-33 | "the NO-GO decision is repeated". |
| B04 | D, Answers paragraph | "Agrees with retrieval" although M1-256 vs M1-384 disagrees with recall; Results say "consistent with". | R:144-154 | Align. |
| B05 | M:27 vs M:39 | Set 2 "scored once" vs "once per gold variant" (three score runs). | S:1654-1656 | "once per gold variant". |
| B06 | M:34-40 | A second held-out run without the Indian documents (P4-FINAL-NOINDIAN-20261114-2, identical output, uncommitted_changes true) is in no note; not listed. Gold-drop/size reports were re-run on 14 Nov too. | runs/P4-FINAL-NOINDIAN-20261114-2.json; RES §8.3 | Mention; add a spec note. |
| B07 | L | Missing limits: set 2 excludes charts, images, pages without a text layer and documents over 200 pages; box gold is read from the PDF text layer, the source pdfplumber uses; the two gold sources in the pooled gap; judge has one rater. | S:1342-1344, 1403-1406, 1470 | Add two sentences. |
| B08 | L:33-34 | "Positive there for two of three corpora" holds for the drop-rule primary gold; under certain-only, Docling is negative in both. | P4-H2-20261124-7_rq2.csv | "under the primary gold". |
| B09 | M:248-258; tab:rq2h2 | RQ2 uses each parser's own question set (pdfplumber 53 documents, certain-only 33 / 49), not RQ1's 52 / 29; documents are not given. | P4-H2-20261124-7_rq2.csv | Add document counts. |
| B10 | tab:rq1, tab:retrievers, tab:noindian | "Tied" includes the best setup; captions do not say so. | P4-FINAL primary_setups (15 True, best included) | Add to captions. |
| B11 | R:181 | "Recall finds no difference between the two OCR settings" from 8 documents, 34 questions. | R:194-198 | "detects". |
| B12 | R:218 | "Tuning pays off when a library's default is far from the optimum" generalises from one library. | R:204-213 | "For LangChain". |
| B13 | W:58-60 | "Does not contradict studies that use other data": unverifiable; Adaptive Chunking reports gains. | abstract of 2603.25333 | "is not directly comparable with". |
| B14 | references.bib | Peer-reviewed versions exist for now-cited arXiv entries: santos2026pdf (Applied Sciences 16(10), 5069; also "Lopes-Cardoso"), elbachyr2026empirical (ICSE-SEIP '26, 728-739), ouyang2024omnidocbench (CVPR 2025, 24838-24848), orbach2025hpo (AAAI 2026 workshop, arXiv comment). | doi.org Crossref; CVF; arXiv 2505.03452 | Replace. |
| B15 | references.bib | Acronyms lose capitals in the list ("From pdf to rag-ready"); malformed `doi={https://doi.org/...}` in two entries; UTF-8 names in old entries. | main.bbl | Brace acronyms; bare DOIs. |
| B16 | references | UNVERIFIED / no citation: Qwen3-Embedding in the semantic chunker, Stanza sentence segmenter, RapidOCR, scipy/pandas are not cited; spearman last page; lu2025, sun2026, shaukat2026, smigielski2026, bhat2025, amiri2025, lin2026, singh2026(both) are arXiv only, peer-reviewed versions not found or not checked. | docs/environment.md:34-39 | Cite the first two. |
| B17 | paper_conf/ vs paper_ieee/ | Method and Results share up to ~190 identical words with paper_conf; two submissions would be duplicate publication. | 14-word shingles | Decide one venue; cite or differ. |
| B18 | V:3-8; NOTICE.md:32 | Tag paper-v1.3.2 predates the set 2 files, reference and text fixes; NOTICE says "no licence file of its own" though LICENSE is MIT. | git log; LICENSE | New tag; update V and NOTICE. |
| B19 | a3_timeline, a1 | "Held-out extraction / gold / scoring / plan" rows do not say set 1; "--" for post-14 Nov pushes leaves set 2 without push evidence. | a3_timeline.tex | Label; export activity. |
| B20 | Fig. 1 | Colour (red/blue) carries the source; weak in grey print. | figures/rq2.tex | B/W styles. |
| B21 | D practical advice | "Use one small-chunk setup", "detect scanned pages before parsing" recommend beyond tested cases (English, two parsers, 1,250 tokens). | L | Add the scope. |
| B22 | acknowledgment | Statement that the author "reviewed ... all code" and "ran the experiments" is the author's to confirm: 53 commits carry a Claude trailer (29 Oct to 23 Nov; later commits are marked in their messages); the Fable/Opus models and the drafting of specs, if any, are not mentioned. | git log trailers | Confirm before submission. |

## NIT

| ID | Location | Problem | Fix |
|---|---|---|---|
| N01 | rq2 figure | Overfull hbox 1.92 pt (check_paper check 2 FAIL). | Reduce width. |
| N02 | abstract | "box-level questions", "locked results" unexplained; three references to NO-GO need a gloss. | Explain. |
| N03 | M:50-51 | "Choices of settings were made on this set, apart from the exposure" is unclear. | Reword. |
| N04 | M, L, R sources | Over-long lines and missing blank lines (readability of source only). | Reflow. |
| N05 | deviations.tex last RQ2 row | 27 + 17 words identical to its spec note (one passage over 25). | Shorten. |
| N06 | docling_settings | Table omits table mode although RQ5(a) varies it. | Add row. |
| N07 | M:298 | Gemini is cited at first use, not where it answers. | Optional. |
| N08 | a2/a6 captions | IEEE style: captions are long; move notes below. | Optional. |

## A-J
A pass (no typed result numbers; A05 is a wrong word). B A01-A04, A08, B01-B04, B12-B13, B21. C A01, A04, B05, B06. D A02, B09, B10 (methods applied as
described; signs and intervals agree with CSVs). E A07, B05, B10, B19. F pass, except A05, B10, B20. G B14-B16; Related Work statements
match the abstracts of the cited papers (checked in round 4a; re-read, only B13 objected). H pass, B18. I B17, B22; no passage over 25 words from RESULTS,
README or spec except N05; none over 6 words from cited abstracts. J isolated build PASS, 16 pages, 1 overfull, check_paper FAIL on check 2 only.

## K. Round-1 items
OPEN: M05 (A01: the claim is still too wide in M:5-6), M09 (A02), M12 (A03), M16 (B04), M19 (A04), S10 (B11), S11 (B06), S18 (B19), S23 (B20), S30 (B10).
CLOSED: M01, M02, M03, M04 (caption states push times only to 14 Nov), M06, M07, M08, M10, M11, M13, M14, M15, M17, M18, M20, M21, M22, M23, M24, M25;
S01, S02, S03, S04, S05, S06, S07, S08, S09, S12, S13, S14, S15, S16, S17, S19, S20, S21, S22, S24, S25, S26 (listed software), S27, S28, S29, S31, S32.
