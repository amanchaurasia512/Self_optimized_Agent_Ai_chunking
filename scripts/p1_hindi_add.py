"""P1-R01: add the Hindi-track pair (RTI Act, Hindi and English editions) to the PDF catalogue."""
import pandas as pd

from src.common.manifest import PROJECT_ROOT, file_sha256, project_path
from src.common.pdf_catalog import pdf_stats, update_manifest

HINDI_DIR = PROJECT_ROOT / "data" / "raw" / "hindi"
LICENCE = "Government of India public document"
SOURCES = {
    "rti_act_en": {"language": "en",
                   "source_title": "RTI Act, 2005 (Amended) - English version, as on 18-11-2025",
                   "source_path": "https://rti.dopt.gov.in/Writereaddata/RTI%20Act,%202005%20(Amended)-English%20Version.PDF"},
    "rti_act_hi": {"language": "hi",
                   "source_title": "RTI Act, 2005 - Hindi version (earlier edition, before the 2023 amendment)",
                   "source_path": "https://doe.gov.in/circulars/rti-act-2005-english-hindi"},
}


def main():
    rows = [{"doc_id": doc_id, "source_dataset": "Own (Hindi track)", "track": "hindi", "licence": LICENCE, **source,
             "file": project_path(HINDI_DIR / f"{doc_id}.pdf"), "sha256": file_sha256(HINDI_DIR / f"{doc_id}.pdf"),
             **pdf_stats(HINDI_DIR / f"{doc_id}.pdf")}
            for doc_id, source in SOURCES.items()]
    update_manifest(rows)
    print(pd.DataFrame(rows)[["doc_id", "language", "pages", "text_chars"]].to_string(index=False))


if __name__ == "__main__":
    main()