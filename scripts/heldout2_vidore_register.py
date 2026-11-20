"""Held-out set 2 (spec v1.2 "Held-out set 2: ViDoRe V3 (replaces PeerQA)"): recompute the eligible set from the
ViDoRe V3 metadata, download its PDFs from Hugging Face without a token, check them, and register them once as
held_out_2. Metadata only: no PDF is opened beyond its first 5 bytes (%PDF-) and its SHA-256.
- picks:    pdfs/heldout2_picks.csv
- PDFs:     data/raw/vidore_v3/<corpus>/<file> (git-ignored)
- gold inputs (not gold): data/heldout2/queries.jsonl (git-ignored); gold is placed later, with --final
- register: rows appended to pdfs/catalog.csv and pdfs/split.csv (split held_out_2); refuses if any are already there
Run from the repo root: python -m scripts.heldout2_vidore_register"""
import csv
import hashlib
import json
import urllib.request
from collections import Counter

import pandas as pd
import pyarrow.parquet as pq
from huggingface_hub import HfApi, HfFileSystem, hf_hub_download, hf_hub_url

from src.common.manifest import PROJECT_ROOT, project_path
from src.common.pdf_catalog import PDF_MANIFEST, safe_id
from src.common.split import SPLIT_FILE

CORPORA = ["hr", "finance_en", "industrial", "pharmaceuticals", "computer_science"]
EVIDENCE_TYPES, MIN_QUERIES, MAX_PAGES = {"Text", "Table"}, 2, 200
EXPECTED = {"documents": 53, "queries": 286, "per_corpus": {"hr": 13, "industrial": 11, "pharmaceuticals": 29}}
SOURCE, SPLIT, SET = "ViDoRe V3", "held_out_2", "H2"
PICKS_FILE = PROJECT_ROOT / "pdfs" / "heldout2_picks.csv"
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "vidore_v3"
QUERIES_FILE = PROJECT_ROOT / "data" / "heldout2" / "queries.jsonl"
PDF_LICENCE = {"hr": "CC BY 4.0", "industrial": "Distribution Statement A (USAF, approved for public release)",
               "pharmaceuticals": "public domain (FDA website)"}  # short forms; the full text is in the picks file
LICENCE_START = {"hr": "cc-by-4.0", "industrial": "DISTRIBUTION STATEMENT A", "pharmaceuticals": "Unless otherwise noted"}


def repo(corpus):
    return f"vidore/vidore_v3_{corpus}"


def table(corpus, name, revision):
    path = hf_hub_download(repo(corpus), f"{name}/test-00000-of-00001.parquet", repo_type="dataset",
                           revision=revision, token=False)
    return pd.read_parquet(path)


def page_ids(corpus, revision):
    """corpus_id -> doc_id and page number, reading only those columns of the page parquets (no images, no text)."""
    fs = HfFileSystem(token=False)
    parts = []
    for path in sorted(fs.glob(f"datasets/{repo(corpus)}@{revision}/corpus/test-*.parquet")):
        with fs.open(path, "rb", block_size=2**20) as handle:
            parts.append(pq.read_table(handle, columns=["corpus_id", "doc_id", "page_number_in_doc"]).to_pandas())
    return pd.concat(parts, ignore_index=True)


def eligible(corpus, revision):
    """Eligible queries and documents of one corpus by the note's rule, with the score-2 evidence of each query."""
    queries, qrels, metadata = (table(corpus, name, revision) for name in ("queries", "qrels", "documents_metadata"))
    english = queries[queries["language"] == "english"].set_index("query_id")
    qrels = qrels[qrels["query_id"].isin(english.index) & (qrels["score"] == 2)].merge(page_ids(corpus, revision), on="corpus_id")
    kept = []
    for query_id, pages in qrels.groupby("query_id"):
        types = {label for labels in pages["content_type"] for label in labels}
        if pages["doc_id"].nunique() == 1 and types and types <= EVIDENCE_TYPES:
            kept.append({"query_id": int(query_id), "doc_id": pages["doc_id"].iloc[0], "query": english.loc[query_id, "query"],
                         "pages": [{"corpus_id": int(page.corpus_id), "page_number_in_doc": int(page.page_number_in_doc),
                                    "content_type": list(page.content_type),
                                    "boxes": [{key: int(box[key]) for key in ("annotator", "x1", "y1", "x2", "y2")}
                                              for box in page.bounding_boxes]}
                                   for page in pages.sort_values("page_number_in_doc").itertuples()]})
    counts = Counter(query["doc_id"] for query in kept)
    documents = metadata[metadata["doc_id"].map(lambda doc: counts[doc] >= MIN_QUERIES) & (metadata["page_number"] <= MAX_PAGES)]
    documents = documents.assign(queries=documents["doc_id"].map(counts))
    return documents, [query for query in kept if query["doc_id"] in set(documents["doc_id"])]


def listing(corpus, revision):
    """file name -> (size, SHA-256 or None) for the repo's PDFs; files kept in plain git have no listed SHA-256."""
    files = HfApi().list_repo_tree(repo(corpus), path_in_repo="pdfs", repo_type="dataset", revision=revision, token=False)
    return {item.path.removeprefix("pdfs/"): (item.size, item.lfs.sha256 if item.lfs else None)
            for item in files if item.path.lower().endswith(".pdf")}


def hashed(target):
    """SHA-256 and first 5 bytes of a file already on disk."""
    digest = hashlib.sha256()
    with open(target, "rb") as handle:
        head = handle.read(5)
        digest.update(head)
        while block := handle.read(2**20):
            digest.update(block)
    return digest.hexdigest(), head


def download(corpus, file_name, revision, target, listed_sha256):
    """Stream the PDF to target (kept if already there with the listed SHA-256); returns its SHA-256 and first 5 bytes."""
    if listed_sha256 and target.exists() and hashed(target)[0] == listed_sha256:
        return hashed(target)
    url = hf_hub_url(repo(corpus), f"pdfs/{file_name}", repo_type="dataset", revision=revision)
    digest, head = hashlib.sha256(), b""
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response, open(target, "wb") as out:
        while block := response.read(2**20):
            head = head or block[:5]
            digest.update(block)
            out.write(block)
    return digest.hexdigest(), head


def append_rows(path, rows):
    """Append rows under the file's existing header, leaving every existing line unchanged."""
    with open(path, encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    with open(path, "a", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=header).writerows(rows)


def main():
    catalog, split = pd.read_csv(PDF_MANIFEST), pd.read_csv(SPLIT_FILE)
    if (catalog["source_dataset"] == SOURCE).any() or (split["split"] == SPLIT).any():
        raise SystemExit(f"{SOURCE} / {SPLIT} rows already registered; registration runs once")

    api, picks, queries = HfApi(), [], []
    for corpus in CORPORA:
        revision = api.dataset_info(repo(corpus), token=False).sha
        documents, kept = eligible(corpus, revision)
        files = listing(corpus, revision)
        for document in documents.itertuples():
            if not document.license.startswith(LICENCE_START[corpus]):
                raise SystemExit(f"{corpus}/{document.doc_id}: unexpected licence text")
            picks.append({"doc_id": safe_id(f"vidore_{corpus}", document.doc_id), "corpus": corpus,
                          "vidore_doc_id": document.doc_id, "file": document.file_name, "pages": int(document.page_number),
                          "queries": int(document.queries), "revision": revision,
                          "listed_size": files[document.file_name][0], "listed_sha256": files[document.file_name][1],
                          "licence": document.license})
        id_of = {pick["vidore_doc_id"]: pick["doc_id"] for pick in picks if pick["corpus"] == corpus}
        queries += [{"corpus": corpus, **query, "doc_id": id_of[query["doc_id"]], "vidore_doc_id": query["doc_id"]}
                    for query in kept]

    if len({pick["doc_id"] for pick in picks}) != len(picks) or {pick["doc_id"] for pick in picks} & set(catalog["doc_id"]):
        raise SystemExit("doc ids collide")
    per_corpus = dict(Counter(pick["corpus"] for pick in picks))
    found = {"documents": len(picks), "queries": len(queries), "per_corpus": per_corpus}
    if found != EXPECTED:
        raise SystemExit(f"eligible set differs from the note: {found}")

    catalog_sha = set(catalog["sha256"])
    for pick in picks:
        target = RAW_DIR / pick["corpus"] / pick["file"]
        pick["sha256"], head = download(pick["corpus"], pick["file"], pick["revision"], target, pick["listed_sha256"])
        pick["path"], pick["size"] = target, target.stat().st_size
        pick["status"] = ("not a PDF" if head != b"%PDF-" else
                          "size differs from listing" if pick["size"] != pick["listed_size"] else
                          "SHA-256 differs from listing" if pick["listed_sha256"] not in (None, pick["sha256"]) else
                          "in pdfs/catalog.csv (overlap)" if pick["sha256"] in catalog_sha else "ok")
        pick["sha256_source"] = "listing (verified)" if pick["listed_sha256"] else "ours (no listed hash)"

    picks_table = pd.DataFrame(picks)
    picks_table[["doc_id", "corpus", "file", "pages", "sha256", "sha256_source", "queries", "status", "revision",
                 "licence"]].to_csv(PICKS_FILE, index=False)
    ok = picks_table[picks_table["status"] == "ok"]
    QUERIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUERIES_FILE.write_text("".join(json.dumps(query, ensure_ascii=False) + "\n" for query in queries
                                    if query["doc_id"] in set(ok["doc_id"])), encoding="utf-8")

    append_rows(PDF_MANIFEST, [{"doc_id": pick.doc_id, "source_dataset": SOURCE, "source_title": pick.vidore_doc_id,
                                "source_path": f"{repo(pick.corpus)}@{pick.revision[:7]} pdfs/{pick.file}",
                                "licence": f"annotations: CC BY 4.0 (ViDoRe V3); PDF: {PDF_LICENCE[pick.corpus]}",
                                "file": project_path(pick.path), "sha256": pick.sha256, "pages": pick.pages, "set": SET}
                               for pick in ok.itertuples()])
    append_rows(SPLIT_FILE, [{"doc_id": doc_id, "source_dataset": SOURCE, "split": SPLIT, "set": SET} for doc_id in ok["doc_id"]])

    print(f"eligible {found['documents']} documents, {found['queries']} queries {per_corpus}")
    print(f"downloaded {len(picks_table)} | {picks_table['size'].sum() / 1e6:.1f} MB | "
          f"hash from listing {int(picks_table['listed_sha256'].notna().sum())}, ours only {int(picks_table['listed_sha256'].isna().sum())}")
    print(f"status {dict(Counter(picks_table['status']))}")
    for pick in picks_table[picks_table["status"] != "ok"].itertuples():
        print(f"LEFT OUT {pick.doc_id}: {pick.status}")
    print(f"registered {len(ok)} documents, {int(ok['queries'].sum())} queries, {int(ok['pages'].sum())} pages as {SPLIT}")
    print(f"revisions {dict(zip(picks_table['corpus'], picks_table['revision'].str[:7]))}")


if __name__ == "__main__":
    main()
