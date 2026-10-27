"""P1-R01: summarise QASPER per paper: length, sections, answerable questions with text evidence, table/figure evidence."""
import pandas as pd

from src.common.manifest import PROJECT_ROOT

QASPER_DIR = PROJECT_ROOT / "data" / "external" / "qasper" / "qasper"
SPLITS = ["train", "validation", "test"]
FLOAT_PREFIX = "FLOAT SELECTED"  # QASPER's marker for table/figure evidence


def load_papers():
    return pd.concat([pd.read_parquet(QASPER_DIR / split / "0000.parquet").assign(split=split) for split in SPLITS],
                     ignore_index=True)


def answer_evidence(answers):
    """All evidence strings from the answerable annotations of one question."""
    return [evidence for annotation in answers["answer"] if not annotation["unanswerable"]
            for evidence in annotation["evidence"]]


def paper_row(paper):
    evidence_per_question = [answer_evidence(answers) for answers in paper["qas"]["answers"]]
    text_evidence = [[item for item in evidence if not item.startswith(FLOAT_PREFIX)] for evidence in evidence_per_question]
    return {"paper_id": paper["id"], "split": paper["split"],
            "words": sum(len(paragraph.split()) for section in paper["full_text"]["paragraphs"] for paragraph in section),
            "sections": len(paper["full_text"]["section_name"]),
            "questions": len(evidence_per_question),
            "text_questions": sum(bool(evidence) for evidence in text_evidence),
            "float_questions": sum(any(item.startswith(FLOAT_PREFIX) for item in evidence) for evidence in evidence_per_question)}


def main():
    summary = pd.DataFrame([paper_row(paper) for paper in load_papers().to_dict("records")])
    summary.to_csv(QASPER_DIR.parent / "paper_summary.csv", index=False)
    print("papers:", len(summary), "| questions:", summary["questions"].sum(),
          "| with text evidence:", summary["text_questions"].sum(),
          "| with table/figure evidence:", summary["float_questions"].sum(), "\n")
    print(summary[["words", "sections", "questions", "text_questions", "float_questions"]].describe().round(1), "\n")
    print(summary.sort_values(["text_questions", "words"], ascending=False).head(10).to_string(index=False))


if __name__ == "__main__":
    main()