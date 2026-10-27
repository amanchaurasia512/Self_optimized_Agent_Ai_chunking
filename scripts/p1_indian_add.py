"""P1-R01: add the Indian regulatory benchmark (4 PDFs, 200 questions each) to the PDF list,
and preview how often each verbatim evidence string occurs in the pdfplumber text (0 = missing, 1 = usable, >1 = ambiguous)."""
import json
import re
import shutil

import pandas as pd
import pdfplumber

from src.common.manifest import PROJECT_ROOT, file_sha256, project_path
from src.common.pdf_catalog import pdf_stats, safe_id, update_manifest

SOURCE_DIR = PROJECT_ROOT / "data" / "external" / "indian_regulatory"
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "indian_regulatory"
SOURCE_DATASET = "Indian regulatory benchmark (arXiv 2609.31660)"
LICENCE = "Apache-2.0 (benchmark); PDFs: Government of India public documents"


def normalise(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def pdf_text(path):
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def evidence_rows(doc_id, questions, document_text):
    text = normalise(document_text)
    return [{"doc_id": doc_id, "question_id": question["id"], "question_type": question["question_type"],
             "evidence_words": len(evidence.split()), "occurrences": text.count(normalise(evidence))}
            for question in questions for evidence in question["required_evidence"]]


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    rows, evidence = [], []
    for pdf_path in sorted(SOURCE_DIR.glob("D*.pdf")):
        questions = json.loads((SOURCE_DIR / f"{pdf_path.stem}_GOLDEN_200.json").read_text(encoding="utf-8"))
        doc_id = safe_id("indian", pdf_path.stem)
        target = RAW_DIR / f"{doc_id}.pdf"
        shutil.copyfile(pdf_path, target)
        document_text = pdf_text(target)
        evidence += evidence_rows(doc_id, questions, document_text)
        rows.append({"doc_id": doc_id, "source_dataset": SOURCE_DATASET, "source_title": pdf_path.stem,
                     "source_path": pdf_path.name, "licence": LICENCE, "file": project_path(target),
                     "sha256": file_sha256(target), "words": len(document_text.split()), **pdf_stats(target)})
    update_manifest(rows)

    evidence = pd.DataFrame(evidence)
    evidence.to_csv(SOURCE_DIR / "evidence_preview.csv", index=False)
    print(pd.DataFrame(rows)[["doc_id", "pages", "words", "text_chars"]].to_string(index=False), "\n")
    print(evidence.groupby("doc_id").agg(questions=("question_id", "nunique"), evidence=("question_id", "size"),
                                         found_once=("occurrences", lambda counts: (counts == 1).sum()),
                                         ambiguous=("occurrences", lambda counts: (counts > 1).sum()),
                                         missing=("occurrences", lambda counts: (counts == 0).sum()),
                                         median_words=("evidence_words", "median")), "\n")
    print(evidence.drop_duplicates("question_id")["question_type"].value_counts())


if __name__ == "__main__":
    main()