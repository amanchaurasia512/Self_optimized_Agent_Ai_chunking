"""Which documents may be used during design (pdfs/split.csv): only 'tuning'. Every other split, and any document
missing from the split, is sealed."""
import pandas as pd

from src.common.manifest import PROJECT_ROOT

SPLIT_FILE = PROJECT_ROOT / "pdfs" / "split.csv"


def tuning_ids():
    split = pd.read_csv(SPLIT_FILE)
    return set(split.loc[split["split"] == "tuning", "doc_id"])