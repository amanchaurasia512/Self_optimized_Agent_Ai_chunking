"""RQ5(a) scanned sample (spec v1.2): from MP-DocVQA val, read only doc_id, page_ids and questionId over the network,
keep documents whose page list is identical across their questions, with at least MIN_PAGES pages, and pick the
SAMPLE with the most questions (ties by doc_id). Writes pdfs/scanned_picks.csv with the parquet files that hold them.
Prints ids and counts only."""
import json

import pandas as pd
import pyarrow.parquet as pq
from huggingface_hub import HfFileSystem
import ast
from src.common.manifest import PROJECT_ROOT

REPO = "datasets/lmms-lab/MP-DocVQA"
MIN_PAGES, MAX_PAGES, SAMPLE = 10, 20, 10
PICKS_FILE = PROJECT_ROOT / "pdfs" / "scanned_picks.csv"


def doc_names(system, path):
    """Document names from the parquet's Hugging Face feature metadata, when doc_id is stored as a class label."""
    with system.open(path) as handle:
        metadata = pq.read_schema(handle).metadata or {}
    features = json.loads(metadata.get(b"huggingface", b"{}")).get("info", {}).get("features", {})
    return features.get("doc_id", {}).get("names")

def page_list(value):
    """The page ids of a question, whether stored as a list or as its text form."""
    return tuple(ast.literal_eval(value)) if isinstance(value, str) else tuple(value)

def main():
    system = HfFileSystem()
    files = sorted(system.glob(f"{REPO}/data/val-*.parquet"))
    names = doc_names(system, files[0])
    frames = []
    for path in files:
        frame = pd.read_parquet(f"hf://{path}", columns=["questionId", "doc_id", "page_ids"], filesystem=system)
        frames.append(frame.assign(file=path.rsplit("/", 1)[1]))
    questions = pd.concat(frames, ignore_index=True)
    if names:
        questions["doc_id"] = questions["doc_id"].map(lambda index: names[index])
    questions["pages"] = questions["page_ids"].map(page_list)
    print("page_ids stored as:", type(questions["page_ids"].iloc[0]).__name__, "| first example has",
          len(questions["pages"].iloc[0]), "pages")

    documents = questions.groupby("doc_id").agg(page_lists=("pages", "nunique"), pages=("pages", lambda pages: len(pages.iloc[0])),
                                                 questions=("questionId", "size"),
                                                 files=("file", lambda files: " ".join(sorted(set(files))))).reset_index()
    single = documents[documents["page_lists"] == 1]
    eligible = single[single["pages"].between(MIN_PAGES, MAX_PAGES)]
    picks = eligible.sort_values(["questions", "doc_id"], ascending=[False, True], kind="stable").head(SAMPLE)
    picks.to_csv(PICKS_FILE, index=False)

    print(f"val questions {len(questions):,} | documents {len(documents):,} | one page list {len(single):,} | "
          f"eligible ({MIN_PAGES}-{MAX_PAGES} pages) {len(eligible):,}")
    print(f"pages per document: {documents['pages'].describe()[['min', '50%', 'max']].to_dict()}")
    print(picks[["doc_id", "pages", "questions", "files"]].to_string(index=False))
    print(f"\nfiles to download: {sorted({name for files in picks['files'] for name in files.split()})}\nsaved {PICKS_FILE}")


if __name__ == "__main__":
    main()