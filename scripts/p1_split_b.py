"""Tuning B / Held-out B: seeded split of the set-B PDFs, stratified by OHR domain, with the same rule as P1-R02.
Existing rows of pdfs/split.csv stay unchanged; set-B rows are added once and never redrawn."""
import pandas as pd

from scripts.p1_split import SPLIT_FILE, draw_held_out
from src.common.pdf_catalog import PDF_MANIFEST


def main():
    split = pd.read_csv(SPLIT_FILE)
    catalog = pd.read_csv(PDF_MANIFEST)
    set_b = catalog[catalog["set"].eq("B")]
    if split["doc_id"].isin(set_b["doc_id"]).any():
        raise FileExistsError("set B is already in pdfs/split.csv: the split is locked and must not be redrawn")

    held_out_ids = {doc_id for domain in sorted(set_b["ohr_domain"].unique())
                    for doc_id in draw_held_out(set_b[set_b["ohr_domain"] == domain])}
    if "set" not in split.columns:
        split["set"] = split["split"].map(lambda value: "hindi" if value == "held_out_hindi" else "A")
    new_rows = set_b[["doc_id", "source_dataset"]].assign(
        split=set_b["doc_id"].map(lambda doc_id: "held_out" if doc_id in held_out_ids else "tuning"), set="B")
    combined = pd.concat([split, new_rows], ignore_index=True)
    combined.to_csv(SPLIT_FILE, index=False)

    print(pd.crosstab(combined["set"], combined["split"]), "\n")
    print("held out (set B):", sorted(held_out_ids))


if __name__ == "__main__":
    main()