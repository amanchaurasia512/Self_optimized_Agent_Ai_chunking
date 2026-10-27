"""P1-R02: seeded tuning / held-out split, stratified by source (30% held out per source, rounded half up, at least 1).
Hindi-track PDFs are held out entirely as a cross-language test. The split is written once and never overwritten."""
import math

import pandas as pd

from src.common.manifest import PROJECT_ROOT
from src.common.pdf_catalog import PDF_MANIFEST

SPLIT_FILE = PROJECT_ROOT / "pdfs" / "split.csv"
SEED = 42
HELD_OUT_SHARE = 0.3


def held_out_count(documents):
    return max(1, math.floor(HELD_OUT_SHARE * len(documents) + 0.5))


def draw_held_out(documents):
    return documents.sample(n=held_out_count(documents), random_state=SEED)["doc_id"].tolist()


def main():
    if SPLIT_FILE.exists():
        raise FileExistsError(f"{SPLIT_FILE} already exists: the split is locked and must not be redrawn")
    catalog = pd.read_csv(PDF_MANIFEST)
    hindi = catalog["track"].eq("hindi")
    main_track = catalog[~hindi]
    held_out_ids = {doc_id for source in sorted(main_track["source_dataset"].unique())
                    for doc_id in draw_held_out(main_track[main_track["source_dataset"] == source])}

    catalog["split"] = catalog["doc_id"].map(lambda doc_id: "held_out" if doc_id in held_out_ids else "tuning")
    catalog.loc[hindi, "split"] = "held_out_hindi"
    catalog[["doc_id", "source_dataset", "split"]].to_csv(SPLIT_FILE, index=False)

    print(pd.crosstab(catalog["source_dataset"], catalog["split"]), "\n")
    print("held out:", sorted(held_out_ids))


if __name__ == "__main__":
    main()