# Full audit of paper_ieee (2026-11-25, report only)

Abbreviations: M = sections/method.tex, R = sections/results.tex, A = sections/appendix.tex, S = spec/spec_v1.2.md,
RES = RESULTS.md, G = scripts/make_artifacts.py. Nothing was edited except this file. Build and generator ran in scratch copies.
No document of a held-out split was opened; only result files, specs and run outputs.

**Verified clean:** the generator re-run gives byte-identical `generated/` (all input checksums accepted); H1, H2, RQ2-RQ5 and
robustness values agree with RES; deviation/correction counts (21 / 5) equal the rows; 13+11+29 = 53; 18 of 18 rho negative, 5 of 6
intervals at 2,000 include 0; all Holm families in the text agree with the CSVs; table captions are above, figure captions below.
`docs/paper_checksums.txt` reports only pdfs/split.csv as changed; that is expected (S:1727, read from the tag).

## MUST

| ID | Location | Problem | Evidence | Fix |
|---|---|---|---|---|
| M01 | main.tex:17-19, 21-23, 30, 32, 40-44 | Abstract, Introduction, Related Work, Discussion, Limitations, Conclusion are empty; affiliation, city, email are placeholders, author name is in brackets. RQ1-RQ5 are never stated. | main.tex | Write them; define RQ1-RQ5 in the Introduction. |
| M02 | M:113, 115, 130, 136, 162 | Five undefined citations print [?]: bm25, rrf, nomic, bootstrap, holm. | main.log; references.bib has no such keys | Add the five entries. |
| M03 | A:6-7, M:25-26, generated/deviations.tex | "Every deviation, correction and disclosure recorded in the specification" is false: rows stop at 14 Nov (spec read at tag paper-v1.2) plus one hand-added row. Missing: distributed-data erratum, AQ rounding/duplicate erratum (18 Nov), four planned chunkers never built, RQ3-control amendment, extension amendments, nomic design changes and trust_remote_code change, held-out 2 replaced twice (CUAD/OHR, then PeerQA), pdfplumber run with uncommitted gate, page losses found after Docling import, gold-rule change, RQ2 reading changed. | S:734, 752, 762-791, 804, 823-857, 1163-1195, 1252-1344, 1363-1386, 1487-1515, 1649-1651 | Extend the table to 25 Nov, or restrict the claim and counts to "up to 15 Nov". |
| M04 | M:24-25, generated/a3_timeline.tex, G:959 | "Commit and first-push times for each step" follows the held-out 2 text, but the table ends 15 Nov: no held-out 2 selection, gold rule, amendment, analysis note or scoring row. | git 99bb88c, 639eb33, 1588e9a, ada367e, b54b92c, 3a87493, 38bac40, f85f5d2, dea2882 | Add held-out 2 rows (and RQ5(b), fixed-k, RQ2 descriptive, RQ3 controls). |
| M05 | M:5-7, M:35 | "Fixed the design before looking at held-out data" and "all design choices were made on [tuning]" contradict the paper's own first deviation: the tree structure of 12 of 13 H1 documents was viewed while designing M1, which is the H1 winner. | S:7-10; deviations.tex row 2026-11-03 | Say "before any held-out question, answer or score was seen" and state the tree-survey exposure in Method. |
| M06 | M:72-74, M:22 | Gold-rule change is presented as made before scores only. It was made **after seeing held-out 2 gold counts**, and the gold implementation note had fixed certain-only, replacing the drop rule of the first ViDoRe note. | S:1410-1414, 1487-1512 | State the sequence and "after gold counts, before any score". |
| M07 | M:182-206, R:114-118 | Post-hoc primary measure shown as pre-designed. The design frozen 10 Nov has the judge score as its only measure; no F1 or containment. Token F1 entered on 11 Nov (after the answers existed) and became primary after the judge failed its check (12 Nov). Method also omits the failure (70%, kappa 0.48), and containment is never reported although named primary. | S:283-287, 313-315; git 3d5407e adds token F1; data/results/aq/analysis_held_out.csv | Disclose in Method and as a deviations row; report containment and the judge check. |
| M08 | R:28-31 | "With three times as many documents, the upper end ... is much closer to zero, so the replication sets the tighter bound". Held-out 2's interval is **wider** (0.098 vs 0.068); its upper end is lower because its point estimate is lower. Attributing it to sample size is wrong. | RES §1, §11; S:1669-1670 | State the widths and drop the "tighter bound" causal claim. |
| M09 | M:155-162, R:11-17, 57-58 | The gap is not a bound on possible gain. It is biased downward: the best single is chosen on the same held-out questions (in-sample), while the oracle is cross-fitted on half of few questions; the bootstrap does not redo either selection. The text then concludes choice "does not improve" retrieval. | scripts/p4_analyse.py:72-83, 92-104 | Describe the asymmetry; write "no evidence of a gain from a chooser selecting on this many questions". |
| M10 | M:157-159 | Undisclosed rule: a one-question document gets the winner's value, so its gap is 0 by construction (1 of 17 on H1, 6 of 52 on H2). H2 has a median of 3 questions per document and 17 with exactly 2, so selection is often on one question. | p4_analyse.py:99-100; P4-FINAL / P4-H2-20261124-1 _primary_documents.csv | State the rule and the counts; note the weak H2 selection. |
| M11 | R:65-80 | RQ2 omits pre-registered descriptive results that cut against it: on H2 at 2,000, HR and Industrial rho are **positive** on both parsers (D +0.30, +0.11; P +0.24, +0.46), pdfplumber Industrial is positive already at 1,250; H1 CUAD weakens (pdfplumber -0.59/-0.51/-0.26, best size to 699 at 2,000); H1 FinanceBench is 1 document with 1 question, uninterpretable. | S:1676-1677, 367-371; P4-H2-20261124-7_rq2.csv | Add these caveats to R and limit the headline to 750 and 1,250. |
| M12 | R:65, 74-76, 102-103 | "At a fixed token budget, smaller chunks retrieve more", "confirms", "for every budget up to 2,000" overclaim: at 2,000 on held-out 2 the drop-rule rhos are -0.148 / -0.231 with intervals -0.65 to +0.53; also at 1,250 three of six intervals (all pdfplumber) include 0. | rq2_h2.tex | Say the sign rule held; the effect is not established at 2,000; give the 1,250 and 750 counts (1 of 6 at 750). |
| M13 | R:96-98, 105-108 | MRR presented as favouring/rewarding size. The locked note says Hit@1 and MRR "barely separate sizes"; no test. MRR does not "put more text in front of the reader" as Recall@k does. | S:416-417, RES "RQ3" | "Nominally highest, barely separated; not tested"; restrict the mechanism to Recall@k. |
| M14 | R:81-108 | RQ3's mechanism is asserted without its evidence: the budget sweep and random-floor Lift@5 (24 of 24 Holm-significant; no crossover to 4,000) are absent. | RES "Controls: budget sweep and random floor" | Report them (tuning, diagnostic) with macros. |
| M15 | Fig. 2 caption (G:1232) | "Recall@4,000, a pre-registered RQ3 measure": the fixed-k design is dated 12 Nov, a tuning diagnostic with no test, written after the tuning and held-out results. | S:325-339 | "a measure named in the diagnostic's design". |
| M16 | R:116-126, 136-140 | "Answers confirm the large-chunk penalty" rests on one 1,024 setup that also changes the chunker; "answer F1 follows recall" rests on n = 7 setups, rho 0.43 on H1, no test. The spec calls it weak evidence. | S:798-800 | "Consistent with"; state n = 7, untested. |
| M17 | R:142-148 | "This agrees with keeping Docling's default OCR": the only significant pair compares recursive 256 with Tesseract **fixed-token** 256 (parser and chunker confounded), 25 questions; recall found no difference. | analysis_scanned_vs_best.csv; RES §5 "weak evidence" | Say weak evidence, confounded. |
| M18 | M:126-128 | "We checked that [the scorer] responds to chunk quality" hides that the floor test FAILED under its pre-written rule in all 6 cases and passed only under an amended rule. Only the table shows it. | S:88; numbers.tex SanityFloorFailedOriginal = 6 | State the failure and the amendment in Method. |
| M19 | R:168-185; Method has no RQ5 part | RQ5's design is absent from Method. RQ5(b) was specified after the held-out scores existed (second use of held-out set 1), and RQ5(a) digital is 5 tuning PDFs; neither is said in text. "Default" for three families is our own 512 start, not a library default. | S:250-258, 215-222 | Add an RQ5 Method subsection with these statements. |
| M20 | R:212-218, 166 | Tool description is wrong. The default mode uses Docling for **every** PDF and scan detection selects nothing. Detection routes only in `--fast` mode, where the parser is pdfplumber, which is not the tuned setup. README still names M1-384 as default. | src/agent/pipeline.py:19, 37-43; README.md:43-46 | Describe both modes; update README. |
| M21 | main.tex acknowledgment | Says Claude only corrected grammar outside Method and Results. The appendix is an "AI draft (Claude)", and 52 commits carry a Claude co-author line. Code, figures and tables are unmentioned; the remaining sections do not exist yet. | git f6ec526; `git log` trailers | Name appendix, code and artifact generation; rewrite when the paper is complete. |
| M22 | ext_rob.tex row "Grid + 6 chunkers (32)" | Wrong: 4 chunkers, 6 setups; and 26 is the choice set, not "grid". | RES §9; R:199 | "Primary + 4 chunkers, 6 setups (32)". |
| M23 | R:199-203 | HybridChunker result lacks its mapping caveat: 1,383 of 3,400 chunks could not be located, so it is not a test of HybridChunker as used directly. Reporting only the gap also hides that three setups are significantly worse. | RES §9 "docling_hybrid caveat" | Add the caveat and the per-setup outcome. |
| M24 | M:152-153 | "Cost is reported on two Pareto fronts (Table cost)": the table shows six 384-token setups per split, no front. | a1_index_cost.tex; CSV columns pareto_tokens, pareto_chunks | Report the fronts or drop the claim. |
| M25 | M:33-35, R, Table golden | Question quality is hidden: 20 of 60 checked Indian questions are invalid (33%, one rater, stopped early against the expansion rule); Indian is 570 of 860 tuning and 171 of 530 H1 questions. Never stated in prose; nor that OHR-Bench, UniDoc and Indian questions are LLM-generated. | RES §8.4, §8.7 | State in Method and Limitations. |

## SHOULD

| ID | Location | Problem | Evidence | Fix |
|---|---|---|---|---|
| S01 | R:40-49 | Same paragraph twice (tuning winner). | R:40-43 = 44-49 | Delete 40-43. |
| S02 | R:36-38 | Wrong cause: the difference -0.042 / -0.045 is a point estimate, so it comes from the random stream of the split-half splits (and the bootstrap), not "its own bootstrap". | p4_analyse.py:134-146 (one rng over scopes) | "draws its own random splits and resamples". |
| S03 | R:54-55 | Pooling paragraph still builds a bound from the replication (see M08); the pooled gap is a different quantity, so widths are not comparable. Spec purpose (narrow the interval) failed. | S:1255, 1672-1674 | "Pooling did not narrow it"; stop there. |
| S04 | M:141-153 | Two 5 Nov amendments merged into one. First amendment (11:03) moved ties from overlapping separate intervals to paired differences; second dropped cost. | S "S10 amendment", S:138-153 | Describe both. |
| S05 | M:134-136, 162, 205 | Holm p-values have no p definition (two-sided bootstrap, floor 2/2,000) and no families. | S:424-434 | Add one sentence. |
| S06 | M:172-178 | Omits that the RQ2 unit was clarified on 24 Nov (13 per parser instead of 26 setups), before scores; primary verdict is 6 rhos on the primary gold, not 18. Drop-rule sensitivity RQ2 was not in the plan. H2 sizes span only 256-512 targets, so it says nothing about 1,024. | S:1649-1651, 1440-1446 | State. |
| S07 | R:13-38, ext_rob | NO-GO labels on BM25, dense, no-Indian, extension and nomic rows apply the rule to descriptive/post-hoc analyses. | S:525-, 650-, 679- | Mark as descriptive in the caption. |
| S08 | R:191-192 | "Does not depend on ... chunker pool or the embedder" is tuning-only for both; the corpus-mix rows are H1 only. | ext_rob.tex | Qualify in the topic sentence. |
| S09 | R:209-210 | "Verdicts on RQ2 and RQ3 also hold" is sign-only; 3 nomic comparisons have Holm p > 0.05 without Indian. | RES §10 | Say "by sign". |
| S10 | R:160-164 | "Do not differ" from 8 documents, 34 questions, [-0.05, 0.08]. | RES §3 | "No difference detected"; same in R:158 and R:208-209. |
| S11 | M:41-42, R | Uses of held-out set 1 are scattered: RQ5(b), AQ, 12 Nov reports without run record, 14 Nov no-Indian and reproduction runs. | RES §8.3, §8.6 | List once in Method. |
| S12 | M:62-63, 78-79 | 16.3% / 27.6% exclude QASPER and UniDoc (n = 742); no H2 drop rates though pre-stated (286 to 229; drop-rule: pdfplumber 248, Docling 237 kept). | RES §6; S:1505-1510 | Add. |
| S13 | M:32-35 | "19 of them with questions" wrong wording: 25 have sources, 20 keep a question, 19 enter the main analysis; QASPER and UniDoc add none. | S:349-350 | Reword. |
| S14 | M:44-51 | Does not say two earlier H2 designs were replaced, that five corpora were screened (Finance-EN, Computer Science gave none), nor that charts/scans/over 200 pages are excluded as limits. | S:1319-1344 | Add. |
| S15 | M:37-39 | FinanceBench named without: 1 document, 1 kept question (86% dropped), recall 0 at 750/1,250. | S:348, 371 | Add. |
| S16 | M:86-92, grid.tex | Semantic was left out of held-out (GPU memory), so "full" is 98 not 100; "full" and "original" sets are never defined; LLM-regex model not named. | S:187-190; RES §1 | Define. |
| S17 | a5_compute.tex | Covers 650 records to 14 Nov (no H2, extension, nomic); 640 AQ calls vs 2,301 answers made, 1,661 without run record; LlamaParse and agent rows relate to nothing in the paper. | RES §8.5 | Footnote or update; remove unrelated rows. |
| S18 | a1, a2, a6, deviations | "Held-out" and "H1" (which is the spec's 13-document subset) where the text uses "held-out set 1". | tables | Rename; explain H1 in deviations. |
| S19 | M:17 vs a3_timeline | v1.2 is "from 3 November" in text; the table's first v1.2 row is 4 Nov. | git b1bd7d1 (11-03 14:54), 4584c8f (11-04) | Add the 3 Nov row. |
| S20 | G:1231 | 0.029 hand-typed in the Fig. 2 caption; check_paper misses it because it scans sections only. | G:1231 | Macro; scan captions too. |
| S21 | M:49-50 and M:145-150 | Hand-typed results/counts 286, 0.1, 98, 8 covered only by `% src:`; also "three" times (R:29). Values are correct. | S:1328, 140-143 | Macros. |
| S22 | R:91-101, Table rq3err, Fig. 2 | Recall@5/10, Hit@1, MRR, R@4000 undefined in Method; raw setup names (method1_tree T384, prefix_v11) clash with short names. Setup naming also differs between text (docling / method1_tree T256) and tables (D/M1-256). | numbers.tex | Define; use one naming. |
| S23 | Fig. 1 and Fig. 2 | Fig. 1 relies on red/blue plus shape, no rho shown; it shows only 1,250 while text cites it for every budget. | rq2.tex; R:66-68 | Cite for 1,250 only; B/W-safe. Fig. 2's "QASPER included" set differs from the text's winners: say so in text. |
| S24 | Fig. 3, R:154-158 | (a) has 5 documents: bootstrap on 5 clusters is weak; not in caption or text. | S:219-220 | Add n. |
| S25 | references.bib | Peer-reviewed versions exist for cited arXiv entries: bge-m3 (Findings ACL 2024, 2318-2335), OHR-Bench (ICCV 2025, 17443-17453), CUAD (NeurIPS D&B 2021), MP-DocVQA (Pattern Recognition, 2023, doi 10.1016/j.patcog.2023.109834; title "Multipage"). | publisher/search results, see G section | Replace. |
| S26 | M:85-92, 199-205, 196 | No citation for pdfplumber, LangChain, HybridChunker, Qwen3, Gemini, Tesseract/RapidOCR, semantic and LLM-regex chunkers (Adaptive Chunking), bge-m3 tokenizer, Spearman/cross-fitting. | M | Add. |
| S27 | whole | No data/code availability statement, repository link, dataset licence list (CC BY-NC for UniDoc, FinanceBench), ethics note, or limitation of evaluation on one seed/embedder and English only. | RES §8.4; NOTICE.md | Add. |
| S28 | R:118-131 | The M1-256 vs M1-384 difference is significant (Holm 0.025) but "not claimed"; the same standard is not applied to FT-1024. | S:801-802 | State the reason (contradicts recall; open). |
| S29 | M:204 | "An amendment on 11 November" was first committed on 12 Nov together with the result; git cannot show it came first. Only the table says so. | S:705-732 | Say in Method. |
| S30 | R:13-14 | "15 tied with it" counts the best setup itself. | P4-FINAL primary_setups.csv (15 True, best included) | "15 including it". Same for all Tied columns. |
| S31 | a2_retrievers, a6 | Larger choice sets: the text omits that the full-set interval lies entirely below 0, i.e. the oracle is *worse*, as the note explains (few questions). | S:203-204 | Explain (supports M09). |
| S32 | M:102-105 | The reasons for the primary choice set (from tuning: >512 worse, prefix no gain) are not given; it is tuning-informed. | S:174-175 | One sentence. |

## NIT

| ID | Location | Problem | Fix |
|---|---|---|---|
| N01 | main.tex:35 comment block | Stale comments "Write last", "Uncomment after your first \cite". | Delete. |
| N02 | build | Overfull hbox 1.92 pt (lines 9-5, rq2 float/section area); two float-only-page warnings; six columns of appendix floats leave large white areas (pp. 8-11). | Tune float sizes. |
| N03 | references.bib:23 | Stray "}" after the demourajunior2026adaptive entry (tolerated by BibTeX). | Remove. |
| N04 | references.bib | 16 entries are uncited now. They do not reach the reference list (10 bibitems). | Cite in Related Work or prune. |
| N05 | grid.tex, docling_settings | Caption and column head repeat "bold: primary choice set". Docling table omits table mode. | Trim; add mode. |
| N06 | R:80-81, 86 | Missing blank line before subsection; over-long line. | Reflow. |
| N07 | deviations.tex | "Tie rule changed ... before any RQ1 result" and "RQ1 rules amended after the development run" share a date; order unclear. | Add times. |
| N08 | S:194 | Spec says 8 UniDoc documents, later accounting 9; paper uses the correct 9. No paper change. | Spec note. |
| N09 | appendix.tex, main.tex | Appendix ends without newline; `\appendices` before Acknowledgment is fine in IEEEtran. | None needed. |
| N10 | ../paper_conf | Untracked paper_conf/ inputs paper_ieee/generated, so it inherits every caption/table finding above. | Keep in sync. |

## A-J summary
- **A** Numbers: all macros match; hand-typed leftovers S20, S21. **B** M08, M11-M18, M20, M22-M24. **C** M03-M07, M15, M19, S04, S06, S29.
- **D** M08-M10, S02, S05, S30. Interval signs agree with the CSVs. **E** S18, S19, S22. **F** every table and figure is referenced; M22, M24, S22-S24.
- **G** Five unresolved cites (M02). Confirmed by web search: bge-m3 Findings ACL 2024; OHR-Bench ICCV 2025; MoC ACL 2025 long.258, 5172-5189
  (uncited); CUAD NeurIPS D&B 2021; ViDoRe V3 ACL 2026 long.755, 16570-16600 (entry correct); MP-DocVQA DOI; nomic TMLR 2025 (search snippet only).
  UNVERIFIED against a publisher page: nomic volume/forum, MP-DocVQA volume and article number, singh2026parser author/metadata (title found, author not),
  Docling report venue (AAAI 2025 workshop version is a different paper), FinanceBench venue, UniDoc-Bench venue (none found), QASPER pages
  (entry taken from ACL Anthology), elbachyr2026 and santos2026 DOIs, OmniDocBench (CVPR 2025 not checked), orbach2025 (AAAI 2026 workshop reported on arXiv),
  and all other uncited arXiv entries.
- **H** M01, M25, S27. **I** M21. Verbatim overlap (12-word shingles against RES, README, NOTICE, spec): only one passage over 25 words,
  deviations.tex last row, 46 identical words from S:1741-1743 (a table quoting its own spec). Method and Results prose: none over 25; longest 12.
- **J** check_paper: checks 1, 3, 4, 5, 6 PASS, check 2 FAIL (5 undefined cites, 1 overfull). latexmk from clean: exit 0, 11 pages, no LaTeX errors,
  no `??` from \ref, five [?]. Conference class is used; 11 pages is over most IEEE conference limits.

## K. Known review items
| Item | Status | Note |
|---|---|---|
| Pooled "upper bound" wording | OPEN | Wording moved to "the bound comes from the replication" (M08, S03) |
| RQ2 per-corpus caveats (HR/Industrial at 2,000; H1 CUAD; FinanceBench) | OPEN | M11 |
| RQ3 MRR tone | OPEN | M13 |
| RQ3 budget sweep + Lift@5 | OPEN | M14 |
| RQ4 scanned wording | OPEN | M17 |
| "Two Pareto fronts" | OPEN | M24 |
| Extension "4 chunkers, 6 setups (32)" | OPEN | Text says four chunkers; table still wrong (M22) |
| HybridChunker mapping caveat | OPEN | M23 |
| Deviations: post-14-Nov runs | OPEN | M03 |
| Deviations: 1,661 answers without run record | OPEN (partial) | Row says "most"; give 1,661 of 2,301; not in text |
| Deviations: agent row | OPEN | No agent deviation row; Table compute lists agent calls, agent not described (S17) |
| Floor test failed under pre-written rule | OPEN (partial) | In table, not in Method (M18) |
| Fig. 2 caption 0.029 as macro | OPEN | S20 |
| v1.2 date 3 vs 4 Nov | OPEN | S19 |
| Peer-reviewed bge-m3 | OPEN | S25 |
| Peer-reviewed OHR-Bench | OPEN | S25 |
| Peer-reviewed MoC | OPEN | Still arXiv in bib, uncited |
| Peer-reviewed nomic | OPEN | Entry missing (M02) |
| CUAD and MP-DocVQA entries | OPEN | Present, arXiv versions (S25) |
