# AUDIT_CONF — paper_conf/ (6-page) against paper_ieee/ (tag paper-v1.4)

Report only; no source edited. Build checked on a scratch copy.

## Checks
- (1) Claims: abstract and conclusion match the full paper word for word (the conclusion only drops its last sentence). No result is stronger than in the full paper; one Related Work sentence is reworded into a slightly new claim (S1).
- (2) Caveats kept: pre-registration covers RQ1 only and the other designs are dated post-hoc; the gap is not a bound (abstract, intro, method, discussion, conclusion); RQ2 is limited to 750/1,250 and covers sizes 256–512 only; RQ3 is tuning-only and its MRR/Hit@1 winners are nominal; RQ4 is weak evidence; RQ5(b) is post-hoc and LangChain-only; English and one embedder; held-out set 1 reuse; the HybridChunker span-mapping caveat; the tool's two modes. Some sub-caveats were lost (S2–S5).
- (3) Floats: Tables I–III and Figs. 1–3 are all referenced. Captions match the text and data, and the figure panels render cleanly.
- (4) References: all 34 cited, none undefined, no BibTeX warnings. The cut papers (Smigielski, StrucChunk, Orbach, Amiri, OmniDocBench, Sun, Lin) are dropped cleanly.
- (5) Acknowledgment: Sections I–VII is correct (Intro … Conclusion), but it still names an Appendix (M1).
- (6) Availability names `paper-v1.4`. The tag holds the held-out set 2 score files (data/results/h2, P4-H2-*), plus deviations.tex, a3_timeline.tex, ext_rob.tex and rq3_erratum.tex, as the text claims.
- (7) latexmk exit 0; **6 pages**; **0 overfull**; 4 underfull (N3). check_paper (adapted to paper_conf, numbers.tex from paper_ieee): **all 6 checks PASS**.

## Findings
| ID | Sev | Location | Problem | One-line fix |
|---|---|---|---|---|
| M1 | MUST | main.tex, Acknowledgment | Says Claude drafted "the Appendix"; this version has no appendix. | Delete "the Appendix" from the list. |
| S1 | SHOULD | related.tex, "Chunk size and budgets" | "Our RQ3 offers one possible reason for such differences" now refers to Bhat's data and embedder dependence. The full paper says that studies' recommendations disagree, which is a different claim. | Write "…one possible reason why such recommendations differ between studies, which we do not test". |
| S2 | SHOULD | method.tex §Documents and §Gold; limitations.tex | Held-out set 2 selection and gold caveats were lost: documents over 200 pages are excluded; pages without a text layer give no gold; certain-only was the rule first fixed, and the 23 Nov change replaced it. | Add "and documents over 200 pages" and "pages without a text layer give no gold". Write "made the drop rule primary in place of the certain-only rule fixed earlier". |
| S3 | SHOULD | method.tex §Question quality / limitations.tex | The question-quality caveat is incomplete: it no longer says that the Indian held-out questions were not checked. | Append "; the Indian held-out questions were not checked." |
| S4 | SHOULD | results.tex §RQ4 / limitations.tex | The RQ4 caveats are incomplete: one answering model, and 1,661 of 2,301 answers (\AQUnrecordedAnswers/\AQAnswers) have no run record. | Add one limitations sentence with both, using the macros. |
| S5 | SHOULD | results.tex §RQ3 | The Recall@5 winner is reported without saying it is over the settings kept after the erratum (superseded and sanity settings left out). The erratum is only mentioned as "in the repository". | Add "over the \RQthreeSettingsKept{} settings kept after the erratum". |
| S6 | SHOULD | main.tex, Acknowledgment | The cut to 6 pages was itself AI-assisted (commit 0ab88c2), but the disclosure does not say so. | Add "Claude Code also prepared this shortened version from the full paper, which I reviewed." |
| N1 | NIT | related.tex | Stray spaces: "regular expressions ." and "jointly ,". | Remove the spaces. |
| N2 | NIT | method.tex §RQ4 and RQ5, last line | "answers from the 1,250 tokens hybrid retrieval reads" reads awkwardly. | "…from the 1,250 tokens that hybrid retrieval reads". |
| N3 | NIT | build log | 4 underfull boxes: Index Terms (6876), availability (1377), bib URL of zhang2024ocr (10000), vbox on p.3. | Optional; none is visible as a defect. |
| N4 | NIT | method.tex §Setups | "D-Tess" is defined but appears nowhere in this version. | Drop "and D-Tess Docling with Tesseract OCR". |
| N5 | NIT | method.tex §Statistics | Lost: "the bootstrap repeats neither choice". The core point that the gap is not an upper bound is kept. | Optional: add it after "push the gap down". |
| N6 | NIT | method.tex §Gold vs Table II | The text says there are "two sensitivity variants", but Table II labels them "Sensitivity" and "Certain-only". | Write "(sensitivity: any page placed; certain-only)". |
| N7 | NIT | availability.tex | Two qualifiers dropped: MP-DocVQA "though the copy we read states no licence", and "PDFs can be obtained from the dataset sources". | Optional re-add if space allows. |
| N8 | NIT | repo / outside scope | paper_conf is not in tag paper-v1.4 (the tag is 48d21fc, before 0ab88c2). paper_ieee's own availability (at v1.4) still names `paper-v1.3.2`. check_paper on paper_ieee fails on the typed "200" (method.tex:79, limitations.tex:25). | Decide whether the conf version needs its own tag; fix the full paper separately. |

**Counts: MUST 1 · SHOULD 6 · NIT 8**
