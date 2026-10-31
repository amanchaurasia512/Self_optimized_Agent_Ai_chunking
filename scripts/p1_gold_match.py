"""P1-R06: place every gold answer into each parser's frozen text and save the spans per parser.
Sources: CUAD (dataset template as query), Indian regulatory (page-guided), QASPER (union of annotators, text evidence),
OHR-Bench v2 (text + table evidence, page-guided), UniDoc (page-level gold, kept separate from span-level metrics)."""
import argparse
import json
import re

import pandas as pd

from src.common.manifest import PROJECT_ROOT
from src.common.pdf_catalog import safe_id
from src.gold.matching import normalise_with_map, place
from src.gold.matching import DROP_RULE_FILE, missing_words, UNCERTAIN

EXTERNAL = PROJECT_ROOT / "data" / "external"
EXTRACTED = PROJECT_ROOT / "data" / "extracted"
GOLD_DIR = PROJECT_ROOT / "data" / "gold"
PAGE_PATTERN = re.compile(r"Page\s+(\d+)", re.IGNORECASE)
FLOAT_PREFIX = "FLOAT SELECTED"


def question(source, question_id, doc_id, text, evidence, page=None, gold_pages=None, kind="span"):
    return {"source": source, "question_id": question_id, "doc_id": doc_id, "question": text, "evidence": evidence,
            "page": page, "gold_pages": gold_pages or [], "kind": kind}

def heading_or_text(evidence):
    """QASPER marks section-title evidence as a heading path 'A ::: B'; only the last heading appears on the page."""
    return evidence.split(" ::: ")[-1]

def cuad_questions():
    spans = pd.read_csv(EXTERNAL / "cuad" / "selected_gold_spans.csv")
    return [question("CUAD", f"cuad::{contract}::{category}", safe_id("cuad", contract), group["question"].iloc[0],
                     group["answer_text"].tolist())
            for (contract, category), group in spans.groupby(["contract", "category"])]


def indian_questions():
    records = []
    for path in sorted((EXTERNAL / "indian_regulatory").glob("*_GOLDEN_200.json")):
        doc_id = safe_id("indian", path.name.removesuffix("_GOLDEN_200.json"))
        for item in json.loads(path.read_text(encoding="utf-8")):
            pages = [int(found) for location in item["source_location"] for found in PAGE_PATTERN.findall(location)]
            records.append(question("Indian", item["id"], doc_id, item["question"], item["required_evidence"],
                                    pages[0] if pages else None))
    return records


def qasper_questions():
    selected = set(pd.read_csv(EXTERNAL / "qasper" / "selected_papers.csv", dtype={"paper_id": str})["paper_id"])
    papers = pd.concat([pd.read_parquet(path) for path in sorted((EXTERNAL / "qasper" / "qasper").glob("*/0000.parquet"))])
    records = []
    for paper in papers[papers["id"].isin(selected)].to_dict("records"):
        for text, question_id, answers in zip(paper["qas"]["question"], paper["qas"]["question_id"], paper["qas"]["answers"]):
            evidence = sorted({heading_or_text(item) for annotation in answers["answer"] if not annotation["unanswerable"]
                               for item in annotation["evidence"] if not item.startswith(FLOAT_PREFIX)})
            if evidence:
                records.append(question("QASPER", question_id, safe_id("qasper", paper["id"]), text, evidence))
    return records


def unidoc_questions():
    rows = pd.read_csv(EXTERNAL / "unidoc" / "usable_questions.csv", dtype={"doc_id": str})
    chosen = {path.stem for path in (PROJECT_ROOT / "data" / "raw" / "unidoc").glob("*.pdf")}
    return [question("UniDoc", f"unidoc::{index}", f"unidoc_{row.domain}_{row.doc_id}", row.question, [],
                     gold_pages=json.loads(row.gold_pages), kind="page")
            for index, row in enumerate(rows.itertuples(index=False)) if f"unidoc_{row.domain}_{row.doc_id}" in chosen]


def as_list(value):
    return list(value) if isinstance(value, (list, tuple)) else [value]


def ohr_questions():
    items = json.loads((EXTERNAL / "ohr_bench" / "selected_questions.json").read_text(encoding="utf-8"))
    records = [question("OHR-Bench", item["ID"], safe_id("ohr", item["doc_name"]), item["questions"],
                        [str(context) for context in as_list(item["evidence_context"])],
                        int(as_list(item["evidence_page_no"])[0]) + 1) for item in items]
    multi_page = sum(len(as_list(item["evidence_page_no"])) > 1 for item in items)
    print(f"OHR-Bench: {len(records)} questions, {multi_page} with evidence on several pages")
    return records


def load_document(parser, doc_id):
    path = EXTRACTED / parser / f"{doc_id}.json"
    if not path.exists():
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    document["normalised"], document["index_map"] = normalise_with_map(document["text"])
    return document


def place_question(record, document):
    """(evidence_index, piece_index, placement) for every placement of a question."""
    if record["kind"] == "page":
        pages = [page for page in document["pages"] if page["page"] in record["gold_pages"]]
        return [(0, index, {"method": "page", "resolution": "page_level", "span": (page["start_char"], page["end_char"]),
                            "score": None}) for index, page in enumerate(pages)]
    return [(evidence_index, piece_index, placement)
            for evidence_index, evidence in enumerate(record["evidence"])
            for piece_index, placement in enumerate(place(evidence, document["text"], document["pages"],
                                                          document["normalised"], document["index_map"], record["page"]))]

def load_drop_threshold():
    if not DROP_RULE_FILE.exists():
        print(f"no drop rule at {DROP_RULE_FILE}: all uncertain placements kept")
        return None
    return json.loads(DROP_RULE_FILE.read_text())["threshold"]


def judge(placement, span, gold, placed_text, threshold):
    """keep: placed and not below the drop rule; incomplete: kept, but some gold words are not in the placed text."""
    below_rule = placement["method"] in UNCERTAIN and threshold is not None and placement["word_coverage"] < threshold
    keep = span is not None and not below_rule
    missing = missing_words(gold, placed_text) if gold and placed_text else []
    return {"keep": keep, "incomplete": keep and bool(missing), "missing_words": missing}

CERTAIN_METHODS = {"exact", "normalised", "page"}


def certain(placements):
    """Certain: placed exactly/normalised at one place, or piecewise with every piece exact at one place near the match."""
    methods = {placement["method"] for placement in placements}
    single_place = all(placement["resolution"] not in {"ambiguous", "nearest"} for placement in placements)
    return single_place and (methods <= CERTAIN_METHODS or methods == {"segment"})

def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--parsers", nargs="+", default=["pdfplumber", "docling", "llamaparse_agentic"])
    args = arg_parser.parse_args()

    splits = pd.read_csv(PROJECT_ROOT / "pdfs" / "split.csv").set_index("doc_id")["split"].to_dict()
    records = cuad_questions() + indian_questions() + qasper_questions() + unidoc_questions() + ohr_questions()
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    for parser in args.parsers:
        documents, rows = {}, []
        for record in records:
            if record["doc_id"] not in documents:
                documents[record["doc_id"]] = load_document(parser, record["doc_id"])
            document = documents[record["doc_id"]]
            if document is None:
                continue
            by_evidence = {}
            for evidence_index, piece_index, placement in place_question(record, document):
                by_evidence.setdefault(evidence_index, []).append((piece_index, placement))
            for evidence_index, pieces in by_evidence.items():
                is_certain = certain([pair[1] for pair in pieces])
                for piece_index, placement in pieces:
                    span = placement.pop("span")
                    gold = placement.pop("segment", None) or (record["evidence"][evidence_index] if record["kind"] == "span" else None)
                    rows.append({**{key: value for key, value in record.items() if key != "evidence"}, **placement,
                                 "certain": is_certain, "parser": parser, "evidence_index": evidence_index,
                                 "piece_index": piece_index, "gold": gold, "split": splits.get(record["doc_id"]),
                                 "start": span[0] if span else None, "end": span[1] if span else None})
        with (GOLD_DIR / f"spans_{parser}.jsonl").open("w", encoding="utf-8") as output:
            output.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        print(f"{parser}: {len(rows)} placements written")

if __name__ == "__main__":
    main()