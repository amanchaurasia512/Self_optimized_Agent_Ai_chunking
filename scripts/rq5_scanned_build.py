"""RQ5(a): build one scanned PDF per picked MP-DocVQA document from its page images (lossless, img2pdf, in page-list
order), save the picked questions, and add the PDFs to the catalogue and to pdfs/split.csv (split 'scanned_rq5').
Class-label columns are converted through the names stored in the parquet. Prints ids and counts only."""
import json

import img2pdf
import pandas as pd
import pyarrow.parquet as pq

from scripts.rq5_scanned_select import PICKS_FILE, page_list
from src.common.manifest import PROJECT_ROOT, file_sha256, project_path
from src.common.pdf_catalog import pdf_stats, update_manifest

SOURCE = PROJECT_ROOT / "data" / "external" / "mpdocvqa" / "data"
RAW = PROJECT_ROOT / "data" / "raw" / "mpdocvqa"
QUESTIONS = PROJECT_ROOT / "data" / "external" / "mpdocvqa" / "selected_questions.json"
SPLIT_FILE = PROJECT_ROOT / "pdfs" / "split.csv"
SPLIT = "scanned_rq5"
LICENCE = "MIT (MP-DocVQA, Tito et al.); read from the Hugging Face copy lmms-lab/MP-DocVQA"
IMAGES = [f"image_{number}" for number in range(1, 21)]


def label_names(path, column):
    """Names of a class-label column from the parquet's Hugging Face feature metadata, or None if stored as values."""
    metadata = pq.read_schema(path).metadata or {}
    features = json.loads(metadata.get(b"huggingface", b"{}")).get("info", {}).get("features", {})
    return features.get(column, {}).get("names")


def picked_questions(picks):
    wanted, frames = set(picks["doc_id"]), []
    for name in sorted({name for names in picks["files"] for name in names.split()}):
        path = SOURCE / name
        frame = pd.read_parquet(path)
        for column in ["doc_id", "answer_page_idx"]:
            names = label_names(path, column)
            if names:
                frame[column] = frame[column].map(lambda index: names[index])
        frames.append(frame[frame["doc_id"].isin(wanted)])
    return pd.concat(frames, ignore_index=True).drop_duplicates("questionId")


def main():
    picks = pd.read_csv(PICKS_FILE)
    questions = picked_questions(picks)
    RAW.mkdir(parents=True, exist_ok=True)
    catalog, saved = [], []
    for doc in sorted(picks["doc_id"]):
        doc_questions = questions[questions["doc_id"] == doc]
        pages = page_list(doc_questions["page_ids"].iloc[0])
        first = doc_questions.iloc[0]
        images = [first[column]["bytes"] if first[column] is not None else None for column in IMAGES[:len(pages)]]
        assert all(images), f"{doc}: page images missing"
        target = RAW / f"mpdocvqa_{doc}.pdf"
        target.write_bytes(img2pdf.convert(images))
        catalog.append({"doc_id": f"mpdocvqa_{doc}", "source_dataset": "MP-DocVQA", "source_title": doc,
                        "source_path": "lmms-lab/MP-DocVQA val", "licence": LICENCE, "file": project_path(target),
                        "sha256": file_sha256(target), "set": "scanned", **pdf_stats(target)})
        saved += [{"question_id": f"mpdocvqa::{row.questionId}", "doc_id": f"mpdocvqa_{doc}", "question": row.question,
                   "answers": [str(answer) for answer in row.answers], "answer_page": int(row.answer_page_idx) + 1,
                   "page_ids": list(pages)} for row in doc_questions.itertuples(index=False)]
        print(f"{doc}: {len(pages)} pages | {len(doc_questions)} questions | {target.stat().st_size / 1e6:.1f} MB")

    QUESTIONS.write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
    update_manifest(catalog)
    split = pd.read_csv(SPLIT_FILE)
    new = pd.DataFrame({"doc_id": [row["doc_id"] for row in catalog], "split": SPLIT})
    pd.concat([split, new[~new["doc_id"].isin(split["doc_id"])]], ignore_index=True).to_csv(SPLIT_FILE, index=False)
    print(f"\n{len(catalog)} PDFs in {RAW} | {len(saved)} questions saved to {QUESTIONS} | split '{SPLIT}' added")


if __name__ == "__main__":
    main()