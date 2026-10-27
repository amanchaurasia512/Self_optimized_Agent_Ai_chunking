"""P1-R01: draw QASPER papers (top 10% by text-evidence questions, seeded draw),
fetch their PDFs from arXiv and add them, with licence and version, to the PDF catalogue."""
import re
import time
import urllib.request

import pandas as pd

from src.common.manifest import PROJECT_ROOT, file_sha256, project_path
from src.common.pdf_catalog import pdf_stats, safe_id, update_manifest

QASPER_DIR = PROJECT_ROOT / "data" / "external" / "qasper"
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "qasper"
SEED, DRAW = 42, 5
ARXIV_PAUSE_SECONDS = 3  # arXiv asks for at most one request every 3 seconds
HEADERS = {"User-Agent": "Self_optimized_Agent_Ai_chunking research script"}


def fetch(url):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=60) as response:
        content = response.read()
    time.sleep(ARXIV_PAUSE_SECONDS)
    return content


def arxiv_metadata(paper_id):
    record = fetch(f"https://export.arxiv.org/oai2?verb=GetRecord&identifier=oai:arXiv.org:{paper_id}"
                   "&metadataPrefix=arXivRaw").decode("utf-8")
    licence = re.search(r"<license>(.*?)</license>", record)
    versions = re.findall(r'<version version="(v\d+)"', record)
    return {"pdf_licence": licence.group(1) if licence else "arXiv default (non-exclusive distribution licence)",
            "arxiv_version": versions[-1] if versions else ""}


def main():
    summary = pd.read_csv(QASPER_DIR / "paper_summary.csv", dtype={"paper_id": str})
    cutoff = summary["text_questions"].quantile(0.9)
    eligible = summary[summary["text_questions"] >= cutoff]
    selected = eligible.sample(n=DRAW, random_state=SEED)
    selected.to_csv(QASPER_DIR / "selected_papers.csv", index=False)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for record in selected.itertuples(index=False):
        metadata = arxiv_metadata(record.paper_id)
        doc_id = safe_id("qasper", record.paper_id)
        target = RAW_DIR / f"{doc_id}.pdf"
        source_url = f"https://arxiv.org/pdf/{record.paper_id}{metadata['arxiv_version']}"
        target.write_bytes(fetch(source_url))
        rows.append({"doc_id": doc_id, "source_dataset": "QASPER", "source_title": record.paper_id,
                     "source_path": source_url, "licence": f"annotations: CC BY 4.0; PDF: {metadata['pdf_licence']}",
                     "file": project_path(target), "sha256": file_sha256(target), "words": record.words,
                     "arxiv_version": metadata["arxiv_version"], **pdf_stats(target)})
    update_manifest(rows)

    print("text-question cut-off (90th percentile):", cutoff, "| eligible papers:", len(eligible), "\n")
    print(pd.DataFrame(rows)[["doc_id", "arxiv_version", "pages", "words", "text_chars", "licence"]].to_string(index=False))


if __name__ == "__main__":
    main()