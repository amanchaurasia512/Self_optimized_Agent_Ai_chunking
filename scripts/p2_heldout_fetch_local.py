"""P2 spec v1.2: fetch the held-out PDFs that need no Kaggle (CUAD, QASPER, FinanceBench) from the locked picks
(pdfs/heldout_picks.csv), the same way P1 fetched them, into data/raw/heldout, and add them to the PDF catalogue.
Prints ids and numbers only; no document text is shown."""
import shutil

import pandas as pd
from huggingface_hub import hf_hub_download

from scripts.p1_cuad_download import CUAD_DIR, LICENCE as CUAD_LICENCE, REPO_ID as CUAD_REPO, pdf_paths_by_title
from scripts.p1_qasper_add import arxiv_metadata, fetch
from scripts.p2_heldout_select import EXTERNAL, PICKS_FILE
from src.common.manifest import PROJECT_ROOT, file_sha256, project_path
from src.common.pdf_catalog import pdf_stats, update_manifest

HELDOUT_DIR = PROJECT_ROOT / "data" / "raw" / "heldout"
FINANCEBENCH_LICENCE = "annotations: CC BY-NC 4.0 (PatronusAI/financebench); PDF: public SEC filing"


def fetch_cuad(pick, target):
    candidates = pdf_paths_by_title().get(pick.source_title, [])
    if len(candidates) != 1:
        raise LookupError(f"{pick.source_title}: {len(candidates)} matching PDFs {candidates}")
    shutil.copyfile(hf_hub_download(CUAD_REPO, candidates[0], repo_type="dataset", local_dir=CUAD_DIR), target)
    return candidates[0], CUAD_LICENCE


def fetch_qasper(pick, target):
    metadata = arxiv_metadata(pick.source_title)
    url = f"https://arxiv.org/pdf/{pick.source_title}{metadata['arxiv_version']}"
    target.write_bytes(fetch(url))
    return url, f"annotations: CC BY 4.0; PDF: {metadata['pdf_licence']}"


def fetch_financebench(pick, target):
    source = EXTERNAL / "financebench" / "candidates" / f"{pick.doc_id}.pdf"
    shutil.copyfile(source, target)
    return project_path(source), FINANCEBENCH_LICENCE


FETCHERS = {"CUAD v1": fetch_cuad, "QASPER": fetch_qasper, "FinanceBench": fetch_financebench}


def main():
    picks = pd.read_csv(PICKS_FILE, dtype={"source_title": str})
    HELDOUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for pick in picks[picks["source_dataset"].isin(FETCHERS)].itertuples(index=False):
        target = HELDOUT_DIR / f"{pick.doc_id}.pdf"
        source_path, licence = FETCHERS[pick.source_dataset](pick, target)
        rows.append({"doc_id": pick.doc_id, "source_dataset": pick.source_dataset, "source_title": pick.source_title,
                     "source_path": source_path, "licence": licence, "file": project_path(target),
                     "sha256": file_sha256(target), "set": pick.set, **pdf_stats(target)})
    update_manifest(rows)
    print(pd.DataFrame(rows)[["doc_id", "set", "pages", "text_chars", "licence"]].to_string(index=False))


if __name__ == "__main__":
    main()