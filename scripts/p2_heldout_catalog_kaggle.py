"""P2 spec v1.2: add the held-out PDFs fetched on Kaggle (P2-KN02: OHR-Bench, UniDoc-Bench) to the PDF catalogue, from
the locked picks (pdfs/heldout_picks.csv), verifying each file's hash against the Kaggle log. Stops without writing if
any hash differs. Prints ids and numbers only; no document text is shown."""
import re

import pandas as pd

from scripts.p1_ohr_add import source_licence
from scripts.p1_unidoc_add import LICENCE as UNIDOC_LICENCE
from scripts.p2_heldout_fetch_local import HELDOUT_DIR
from scripts.p2_heldout_select import PICKS_FILE
from src.common.manifest import PROJECT_ROOT, file_sha256, project_path
from src.common.pdf_catalog import pdf_stats, update_manifest

KAGGLE_LOG = PROJECT_ROOT / "data" / "external" / "kaggle_out" / "P2-KN02" / "p2-kn02.log"


def logged_hashes():
    return dict(re.findall(r"  (\S+): [\d,]+ bytes \| sha256 ([0-9a-f]{16})", KAGGLE_LOG.read_text(encoding="utf-8")))


def source_fields(pick):
    if pick.source_dataset == "OHR-Bench v2":
        return {"source_path": f"opendatalab/OHR-Bench pdfs.zip -> {pick.source_title}.pdf (Kaggle P2-KN02)",
                "licence": source_licence(pick.source_title), "ohr_domain": pick.domain}
    return {"source_path": f"Salesforce/UniDoc-Bench {pick.domain}_pdfs.tar.gz -> {pick.domain}/{pick.source_title}.pdf "
                           "(Kaggle P2-KN02)", "licence": UNIDOC_LICENCE}


def main():
    picks = pd.read_csv(PICKS_FILE, dtype={"source_title": str})
    hashes = logged_hashes()
    rows = []
    for pick in picks[picks["source_dataset"].isin(["OHR-Bench v2", "UniDoc-Bench"])].itertuples(index=False):
        target = HELDOUT_DIR / f"{pick.doc_id}.pdf"
        sha256 = file_sha256(target)
        rows.append({"doc_id": pick.doc_id, "source_dataset": pick.source_dataset, "source_title": pick.source_title,
                     "file": project_path(target), "sha256": sha256, "set": pick.set,
                     "hash_matches_kaggle": hashes.get(pick.doc_id) == sha256[:16], **source_fields(pick),
                     **pdf_stats(target)})
    table = pd.DataFrame(rows)
    print(table[["doc_id", "set", "pages", "text_chars", "hash_matches_kaggle"]].to_string(index=False))
    if not table["hash_matches_kaggle"].all():
        raise ValueError("hash differs from the Kaggle log; catalogue not changed")
    update_manifest(rows)
    print("\nadded:", len(rows))


if __name__ == "__main__":
    main()
