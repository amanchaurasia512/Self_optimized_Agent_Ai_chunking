"""P2 spec v1.2 H2/H3: pick the new held-out documents by the written rule (P1 eligibility per source computed on the
full data, drop documents already picked, the largest by the metadata length measure, a tie to the first in dataset
order) and lock them into pdfs/split.csv as held_out_c (known types) and held_out_ood (unseen kinds and sources).
Dry run unless --write. Only FinanceBench candidates are downloaded, and only their page count is read."""
import argparse
import json
import urllib.request

import pandas as pd
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from scripts.p1_cuad_select import CUAD_JSON, contract_table, gold_spans
from scripts.p1_split import SPLIT_FILE
from src.common.manifest import PROJECT_ROOT
from src.common.pdf_catalog import PDF_MANIFEST, safe_id

EXTERNAL = PROJECT_ROOT / "data" / "external"
PICKS_FILE = PROJECT_ROOT / "pdfs" / "heldout_picks.csv"
OHR_SETS = {"C": ["academic", "administration", "finance", "law", "manual"], "OOD": ["news", "textbook"]}
UNIDOC_SETS = {"C": ["finance", "healthcare"],
               "OOD": ["commerce_manufacturing", "construction", "crm", "education", "energy", "legal"]}
SPLIT_NAMES = {"C": "held_out_c", "OOD": "held_out_ood"}
TOP_SHARE = 0.10
HEADERS = {"User-Agent": "Self_optimized_Agent_Ai_chunking research script"}


def top_share(documents, column):
    return documents[documents[column] >= documents[column].quantile(1 - TOP_SHARE)]


def largest(candidates, measure):
    """The largest candidate by the measure; a tie goes to the first in dataset order."""
    return candidates.sort_values(measure, ascending=False, kind="stable").iloc[0]


def pick(set_name, source, domain, title, doc_id, measure, value, eligible):
    return {"set": set_name, "source_dataset": source, "domain": domain, "source_title": title, "doc_id": doc_id,
            "measure": measure, "value": value, "eligible": eligible}


def cuad_picks(titles):
    contracts = json.loads(CUAD_JSON.read_text(encoding="utf-8"))["data"]
    spans = gold_spans(contracts)
    table = contract_table(contracts, spans[spans["occurrences"] == 1])
    picked = set(pd.read_csv(EXTERNAL / "cuad" / "selected_contracts.csv")["contract"]) | titles
    eligible = table[table["usable_spans"] >= table["usable_spans"].quantile(0.25)]
    eligible = eligible[~eligible["contract"].isin(picked)]
    best = largest(eligible, "words")
    return [pick("C", "CUAD v1", "contracts", best["contract"], safe_id("cuad", best["contract"]), "words", best["words"], len(eligible))]


def qasper_picks(titles):
    summary = pd.read_csv(EXTERNAL / "qasper" / "paper_summary.csv", dtype={"paper_id": str})
    picked = set(pd.read_csv(EXTERNAL / "qasper" / "selected_papers.csv", dtype={"paper_id": str})["paper_id"]) | titles
    eligible = top_share(summary, "text_questions")
    eligible = eligible[~eligible["paper_id"].isin(picked)]
    best = largest(eligible, "words")
    return [pick("C", "QASPER", "papers", best["paper_id"], safe_id("qasper", best["paper_id"]), "words", best["words"], len(eligible))]


def ohr_picks(titles):
    summary = pd.read_csv(EXTERNAL / "ohr_bench" / "document_summary.csv")
    summary["usable_questions"] = summary[["text", "table"]].sum(axis=1)
    picked = set(pd.read_csv(EXTERNAL / "ohr_bench" / "selected_documents.csv")["doc_name"]) | titles
    picks = []
    for set_name, domains in OHR_SETS.items():
        for domain in domains:
            eligible = top_share(summary[summary["domain"] == domain], "usable_questions")
            eligible = eligible[~eligible["doc_name"].isin(picked)]
            best = largest(eligible, "pages")
            picked.add(best["doc_name"])
            picks.append(pick(set_name, "OHR-Bench v2", domain, best["doc_name"], safe_id("ohr", best["doc_name"]),
                              "pages", best["pages"], len(eligible)))
    return picks


def unidoc_picks(catalog):
    summary = pd.read_csv(EXTERNAL / "unidoc" / "document_summary.csv", dtype={"doc_id": str})
    picked = {doc_id.rsplit("_", 1)[1] for doc_id in catalog["doc_id"] if doc_id.startswith("unidoc_")}
    picks = []
    for set_name, domains in UNIDOC_SETS.items():
        for domain in domains:
            eligible = top_share(summary[summary["domain"] == domain], "questions")
            eligible = eligible[~eligible["doc_id"].isin(picked)]
            best = largest(eligible, "pages")
            picked.add(best["doc_id"])
            picks.append(pick(set_name, "UniDoc-Bench", domain, best["doc_id"], f"unidoc_{domain}_{best['doc_id']}",
                              "pages", best["pages"], len(eligible)))
    return picks


def page_count(url, target):
    """Download a candidate once and read only its number of pages; None when it cannot be fetched or read."""
    try:
        if not target.exists():
            request = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(request, timeout=120) as response:
                target.write_bytes(response.read())
        return len(PdfReader(target).pages)
    except (OSError, PdfReadError) as error:
        print(f"  skipped {target.name}: {error}")
        return None


def financebench_picks():
    questions = pd.read_json(EXTERNAL / "financebench" / "financebench_merged.jsonl", lines=True)
    documents = (questions.groupby("doc_name", sort=False)
                 .agg(questions=("question", "size"), doc_link=("doc_link", "first")).reset_index())
    eligible = top_share(documents, "questions").copy()
    folder = EXTERNAL / "financebench" / "candidates"
    folder.mkdir(exist_ok=True)
    eligible["pages"] = [page_count(row.doc_link, folder / f"{safe_id('financebench', row.doc_name)}.pdf")
                         for row in eligible.itertuples()]
    eligible = eligible.dropna(subset=["pages"])
    best = largest(eligible, "pages")
    return [pick("OOD", "FinanceBench", "finance_reports", best["doc_name"], safe_id("financebench", best["doc_name"]),
                 "pages", int(best["pages"]), len(eligible))]


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--write", action="store_true", help="lock the picks into pdfs/split.csv (only once)")
    args = arg_parser.parse_args()

    split = pd.read_csv(SPLIT_FILE)
    if split["split"].isin(SPLIT_NAMES.values()).any():
        raise FileExistsError("Set C / OOD are already in pdfs/split.csv: the picks are locked and must not be redrawn")
    catalog = pd.read_csv(PDF_MANIFEST, dtype={"source_title": str})
    titles = set(catalog["source_title"].dropna())
    picks = pd.DataFrame(cuad_picks(titles) + qasper_picks(titles) + ohr_picks(titles) + unidoc_picks(catalog)
                         + financebench_picks())
    print(picks.to_string(index=False))
    print("\nper set:", picks["set"].value_counts().to_dict(), "| doc_ids already in split:", picks["doc_id"].isin(split["doc_id"]).sum())

    if args.write:
        picks.to_csv(PICKS_FILE, index=False)
        new_rows = picks[["doc_id", "source_dataset"]].assign(split=picks["set"].map(SPLIT_NAMES), set=picks["set"])
        pd.concat([split, new_rows], ignore_index=True).to_csv(SPLIT_FILE, index=False)
        print(f"locked: {len(new_rows)} rows added to {SPLIT_FILE.name}, picks saved to {PICKS_FILE.name}")


if __name__ == "__main__":
    main()