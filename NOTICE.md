# Third-party data and text in this repository

Licences as checked on each dataset's official page on 2026-11-14 (RESULTS.md section 8.4). "Text" means questions,
reference answers, gold spans, document excerpts, or answers a model wrote from document context. A licence marked
**unknown** was not stated where we looked.

| Source | Licence | Link | Tracked files that contain its text |
|---|---|---|---|
| CUAD v1 | CC BY 4.0 | https://huggingface.co/datasets/theatticusproject/cuad | data/results/aq/sample.csv (questions, references); data/results/aq/judge_check.csv (questions, references, model answers); runs/tests/test_p3_hand_check_20_cases.txt (questions, gold spans, document excerpts); runs/tests/agent/A-LOCAL-20261113-{102,169,236,315}.json (one question each) |
| QASPER | CC BY 4.0 | https://huggingface.co/datasets/allenai/qasper | none |
| OHR-Bench v2 | CC BY 4.0 (questions and answers); PDFs: their own licences, not recorded per PDF: **unknown** | https://huggingface.co/datasets/opendatalab/OHR-Bench | data/results/aq/sample.csv (questions, references); data/results/aq/judge_check.csv (questions, references, model answers); runs/tests/test_p3_hand_check_20_cases.txt (questions, gold spans, document excerpts: PDF text, licence unknown) |
| UniDoc-Bench | CC BY-NC 4.0 | https://huggingface.co/datasets/Salesforce/UniDoc-Bench | none |
| FinanceBench | CC BY-NC 4.0 (annotations); PDFs are public SEC filings | https://huggingface.co/datasets/PatronusAI/financebench | data/results/aq/sample.csv (1 question and its reference; the attribution and non-commercial terms apply to it) |
| MP-DocVQA | MIT at the source (rubentito/mp-docvqa); the copy we read (lmms-lab/MP-DocVQA) states none; document images: **unknown** | https://huggingface.co/datasets/rubentito/mp-docvqa | data/external/mpdocvqa/selected_questions.json (questions, answer lists); data/results/aq/sample.csv (questions, references) |
| Indian regulatory documents (GOLDEN_200) | Apache-2.0 (repository, commit 654c512); PDFs: Government of India documents, licence **unknown** | https://github.com/shubham-61291/pre_generation_rag_retrieval_benchmark | data/results/aq/sample.csv (questions, references); data/results/aq/judge_check.csv (questions, references, model answers); runs/tests/test_p3_hand_check_20_cases.txt (questions, gold spans, document excerpts: PDF text, licence unknown) |
| Adaptive Chunking code (ekimetrics/adaptive-chunking, commit ea87ce8) | MIT (src/chunk/vendor/LICENSE_adaptive_chunking) | https://github.com/ekimetrics/adaptive-chunking | src/chunk/vendor/ (code); src/chunk/few_shot_examples/hccr_report_md_adi.json (a document excerpt shipped in that repository; licence of the underlying document **unknown**) |

The specifications (spec/*.md) and RESULTS.md quote short passages from some documents and questions as examples,
for instance the CCS Conduct Rules sub-rule quoted in spec/spec_v1.1.md.

Not distributed: data/results/aq/answers.jsonl (model answers written from document context for CUAD, OHR-Bench,
Indian, MP-DocVQA and FinanceBench documents). It is listed with its SHA-256 in docs/paper_checksums.txt, so a copy
can be checked; scripts/redraw_judge_check.py needs it.

Model-written text: the answers in data/results/aq/judge_check.csv were written by gemini-3.5-flash-lite from
retrieved document text. data/results/aq/judgements.jsonl holds only the judge's scores (replies of at most three
characters), and data/results/golden_check/ holds labels, identifiers, counts and one note by the author; neither
contains source text.

This repository has no licence file of its own; the terms above apply to the listed files.

## How the files were found (2026-11-15)

- Scope: all 876 files tracked in git on 2026-11-15 (`git ls-files`), plus the 27 result files un-ignored for
  paper-v1.2, which hold numbers, identifiers and setup names only (checked by their columns).
- (A) Exact match: every tracked file was searched for the 540 questions and references of at least 30 characters
  in data/results/aq/sample.csv and data/external/mpdocvqa/selected_questions.json.
- (B) Prose: every string value (JSON, notebooks) or line (other files) with 15 or more consecutive words, in all
  tracked files except .md, .tex, .bib, .sty and .bst, was reviewed by hand; apart from the files above, every hit
  was our own code comments, docstrings, prompts or notebook boilerplate.
- Not covered: document excerpts shorter than 15 words that match no listed question or reference, and text in the
  .md, .tex and .bib files (our own writing, apart from the quotations noted above).
