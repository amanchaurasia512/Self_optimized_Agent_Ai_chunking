"""P1-R01: summarise UniDoc-Bench per document across all domains.
Keeps single-document questions answerable from text (text_only, table_required); image questions are out of scope."""
import pandas as pd
from huggingface_hub import hf_hub_download

from src.common.manifest import PROJECT_ROOT

REPO_ID = "Salesforce/UniDoc-Bench"
DOMAINS = ["commerce_manufacturing", "construction", "crm", "education", "energy", "finance", "healthcare", "legal"]
TEXT_ANSWER_TYPES = ["text_only", "table_required"]
OUTPUT_DIR = PROJECT_ROOT / "data" / "external" / "unidoc"


def load_domain(domain):
    path = hf_hub_download(REPO_ID, f"data/{domain}-00000-of-00001.parquet", repo_type="dataset", local_dir=OUTPUT_DIR)
    return pd.read_parquet(path)


def page_number(image_path):
    return int(image_path.rsplit("_page_", 1)[1].split(".")[0])


def usable_questions(frame):
    doc_ids = frame["gt_image_paths"].map(lambda paths: sorted({path.split("/")[2] for path in paths}))
    usable = frame[frame["answer_type"].isin(TEXT_ANSWER_TYPES) & (doc_ids.map(len) == 1)].copy()
    usable["doc_id"] = doc_ids[usable.index].str[0]
    usable["doc_pages"] = usable["longdoc_image_paths"].map(len)
    usable["gold_pages"] = usable["gt_image_paths"].map(lambda paths: sorted(page_number(path) for path in paths))
    return usable[["domain", "doc_id", "doc_pages", "question", "answer", "answer_type", "question_type", "gold_pages"]]


def summarise_documents(usable):
    return (usable.groupby(["domain", "doc_id"])
            .agg(questions=("question", "size"), pages=("doc_pages", "first"),
                 table_questions=("answer_type", lambda types: (types == "table_required").sum()),
                 text_questions=("answer_type", lambda types: (types == "text_only").sum()))
            .reset_index())


def main():
    usable = pd.concat([usable_questions(load_domain(domain)) for domain in DOMAINS], ignore_index=True)
    documents = summarise_documents(usable)
    usable.to_csv(OUTPUT_DIR / "usable_questions.csv", index=False)
    documents.to_csv(OUTPUT_DIR / "document_summary.csv", index=False)

    overview = documents.groupby("domain").agg(documents=("doc_id", "size"), questions=("questions", "sum"),
                                               most_questions=("questions", "max"),
                                               min_pages=("pages", "min"), max_pages=("pages", "max"))
    print(overview, "\n")
    top = documents.sort_values(["domain", "questions", "pages"], ascending=[True, False, False]).groupby("domain").head(5)
    print(top.to_string(index=False))


if __name__ == "__main__":
    main()