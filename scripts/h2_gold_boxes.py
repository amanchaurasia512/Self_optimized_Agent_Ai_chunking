"""Held-out set 2 gold (spec v1.2 "Held-out set 2: ViDoRe V3" gold rule and "Held-out set 2: gold implementation"):
the words whose centre lies inside any human box (union over annotators) on each score-2 page, read with pdfplumber
from the PDF (boxes scaled page by page from image pixels to PDF points), joined in reading order, are that page's
evidence. Each page is placed separately in each parser's frozen text by the P1 rules (place + certain-only, no drop
rule). Primary: a query keeps gold only if all its score-2 pages are placed; sensitivity: at least one page placed.
Sealed split: refuses without --final, before any network, PDF or extraction access. Never overwrites.
- inputs:  data/heldout2/queries.jsonl, pdfs/heldout2_picks.csv, data/extracted/{pdfplumber,docling}/<doc_id>.json
- outputs: data/heldout2/page_sizes.csv, data/heldout2/box_evidence.jsonl, data/gold/h2_spans_<parser>.jsonl,
           runs/P1-H2-GOLD-<date>-<n>.json
Run from the repo root: python -m scripts.h2_gold_boxes --final"""
import argparse
import io
import json
from collections import Counter

import pandas as pd
import pdfplumber
import pyarrow.parquet as pq
from huggingface_hub import HfFileSystem
from PIL import Image

from src.common.cost_logger import CostLogger
from src.common.manifest import PROJECT_ROOT, RUNS_DIR, build_manifest, new_run_id, write_manifest
from src.common.pdf_catalog import PDF_MANIFEST
from src.common.split import tuning_ids
from src.gold.matching import place
from scripts.heldout2_vidore_register import PICKS_FILE, QUERIES_FILE, repo
from scripts.p1_gold_match import GOLD_DIR, certain, load_document

SPEC_VERSION = "v1.2"
EXTRACTION_RUNS = {"pdfplumber": "P1-LOCAL-20261122-1", "docling": "P1-H2-KN01-20261122-1"}
SIZES_FILE = PROJECT_ROOT / "data" / "heldout2" / "page_sizes.csv"
EVIDENCE_FILE = PROJECT_ROOT / "data" / "heldout2" / "box_evidence.jsonl"
EMPTY_INDUSTRIAL = "industrial"


def outputs_for(parsers):
    return [SIZES_FILE, EVIDENCE_FILE, *(GOLD_DIR / f"h2_spans_{parser}.jsonl" for parser in parsers)]


def refuse_early(queries, parsers, final):
    sealed = sorted({query["doc_id"] for query in queries} - tuning_ids())
    if sealed and not final:
        raise PermissionError(f"held-out documents need --final (final evaluation only): {len(sealed)}, e.g. {sealed[:3]}")
    existing = [str(path) for path in outputs_for(parsers) if path.exists()]
    if existing:
        raise FileExistsError(f"outputs exist, never overwritten: {existing}")


def image_sizes(queries, revisions):
    """corpus_id -> (width, height) from the image header only (PIL opens lazily; no pixel is decoded)."""
    fs, sizes = HfFileSystem(token=False), {}
    wanted = {(query["corpus"], page["corpus_id"]) for query in queries for page in query["pages"]}
    for corpus, revision in revisions.items():
        ids = {corpus_id for name, corpus_id in wanted if name == corpus}
        for path in sorted(fs.glob(f"datasets/{repo(corpus)}@{revision}/corpus/test-*.parquet")):
            with fs.open(path, "rb", block_size=2**20) as handle:
                parquet = pq.ParquetFile(handle)
                for group in range(parquet.num_row_groups):
                    if not ids & set(parquet.read_row_group(group, columns=["corpus_id"])["corpus_id"].to_pylist()):
                        continue
                    rows = parquet.read_row_group(group, columns=["corpus_id", "image"]).to_pylist()
                    sizes |= {row["corpus_id"]: Image.open(io.BytesIO(row["image"]["bytes"])).size
                              for row in rows if row["corpus_id"] in ids}
    missing = wanted - {(corpus, corpus_id) for corpus, corpus_id in wanted if corpus_id in sizes}
    if missing:
        raise SystemExit(f"no image size for {len(missing)} score-2 pages")
    return sizes


def box_words(page, boxes, image_size):
    """Words whose centre is inside any scaled box, in pdfplumber's reading order, each word once."""
    scale_x, scale_y = page.width / image_size[0], page.height / image_size[1]
    scaled = [(box["x1"] * scale_x, box["y1"] * scale_y, box["x2"] * scale_x, box["y2"] * scale_y) for box in boxes]
    inside = lambda word: any(x1 <= (word["x0"] + word["x1"]) / 2 <= x2 and y1 <= (word["top"] + word["bottom"]) / 2 <= y2
                              for x1, y1, x2, y2 in scaled)
    return " ".join(word["text"] for word in page.extract_words() if inside(word))


def box_evidence(queries, files, sizes):
    """One row per (query, score-2 page): evidence text, PDF page (n + 1), shapes and annotator count."""
    rows = []
    for doc_id in sorted({query["doc_id"] for query in queries}):
        with pdfplumber.open(PROJECT_ROOT / files[doc_id]) as pdf:
            for query in (query for query in queries if query["doc_id"] == doc_id):
                for index, page in enumerate(query["pages"]):
                    pdf_page, image_size = pdf.pages[page["page_number_in_doc"]], sizes[page["corpus_id"]]
                    rows.append({"question_id": f"vidore_{query['corpus']}::{query['query_id']}", "corpus": query["corpus"],
                                 "doc_id": doc_id, "evidence_index": index, "page": page["page_number_in_doc"] + 1,
                                 "image_width": image_size[0], "image_height": image_size[1],
                                 "pdf_width": float(pdf_page.width), "pdf_height": float(pdf_page.height),
                                 "annotators": len({box["annotator"] for box in page["boxes"]}),
                                 "evidence": box_words(pdf_page, page["boxes"], image_size)})
    return rows


def judge_page(evidence_row, document):
    """(placements, reason): reason is None when the page is placed (every piece placed, certain)."""
    bounds = next(page for page in document["pages"] if page["page"] == evidence_row["page"])
    if not evidence_row["evidence"].strip():
        return [], "no words in box"
    if bounds["start_char"] == bounds["end_char"]:
        return [], "parser page empty"
    placements = place(evidence_row["evidence"], document["text"], document["pages"], document["normalised"],
                       document["index_map"], evidence_row["page"])
    if any(placement["span"] is None for placement in placements):
        return placements, "not placed"
    return placements, None if certain(placements) else "not certain"


def place_parser(parser, queries, evidence_rows, split):
    documents = {doc_id: load_document(parser, doc_id) for doc_id in {query["doc_id"] for query in queries}}
    by_page = {(row["question_id"], row["evidence_index"]): row for row in evidence_rows}
    spans, summary = [], []
    for query in queries:
        question_id = f"vidore_{query['corpus']}::{query['query_id']}"
        judged = [judge_page(by_page[(question_id, index)], documents[query["doc_id"]]) for index in range(len(query["pages"]))]
        reasons = [reason for placements, reason in judged]
        keep_all, keep_any = all(reason is None for reason in reasons), any(reason is None for reason in reasons)
        summary.append({"parser": parser, "corpus": query["corpus"], "question_id": question_id, "keep_primary": keep_all,
                        "keep_sensitivity": keep_any, "reasons": [reason for reason in reasons if reason]})
        for index, (placements, reason) in enumerate(judged):
            row = by_page[(question_id, index)]
            for piece_index, placement in enumerate(placements):
                span, segment = placement.pop("span"), placement.pop("segment", None)
                spans.append({"source": "ViDoRe V3", "question_id": question_id, "doc_id": query["doc_id"],
                              "question": query["query"], "page": row["page"], "gold_pages": [page["page_number_in_doc"] + 1
                              for page in query["pages"]], "kind": "span", **placement, "certain": reason is None,
                              "keep_primary": keep_all, "keep_sensitivity": keep_any, "drop_reason": reason,
                              "parser": parser, "evidence_index": index, "piece_index": piece_index,
                              "gold": segment or row["evidence"], "split": split[query["doc_id"]],
                              "start": span[0] if span else None, "end": span[1] if span else None})
    return spans, summary


def check_extractions(parsers, doc_ids):
    for parser in parsers:
        listed = set(json.loads((RUNS_DIR / f"{EXTRACTION_RUNS[parser]}.json").read_text())["outputs"])
        absent = sorted(doc_id for doc_id in doc_ids if f"data/extracted/{parser}/{doc_id}.json" not in listed)
        if absent:
            raise SystemExit(f"{parser}: {len(absent)} documents not in run {EXTRACTION_RUNS[parser]}, e.g. {absent[:3]}")


def report(evidence_rows, summary, parsers):
    """Counts only: no question, evidence or document text is printed."""
    shapes = pd.DataFrame(evidence_rows).assign(
        shape_diff=lambda df: ((df["image_width"] / df["image_height"]) / (df["pdf_width"] / df["pdf_height"]) - 1).abs())
    print("score-2 pages:", len(shapes), "| several annotators:", int((shapes["annotators"] > 1).sum()),
          dict(Counter(shapes["annotators"])))
    print("image vs PDF shape, |aspect ratio difference| (no correction):",
          shapes["shape_diff"].describe(percentiles=[0.5, 0.95]).round(4).to_dict(),
          "| pages over 1%:", int((shapes["shape_diff"] > 0.01).sum()), "| over 5%:", int((shapes["shape_diff"] > 0.05).sum()))
    print("pages with no words in box:", dict(Counter(shapes.loc[shapes["evidence"].str.strip() == "", "corpus"])))
    table = pd.DataFrame(summary)
    grouped = table.groupby(["parser", "corpus"]).agg(questions_in=("question_id", "size"),
                                                      gold_primary=("keep_primary", "sum"),
                                                      gold_sensitivity=("keep_sensitivity", "sum"))
    grouped["dropped_primary"] = grouped["questions_in"] - grouped["gold_primary"]
    grouped["drop_rate_primary"] = (grouped["dropped_primary"] / grouped["questions_in"]).round(3)
    grouped["drop_rate_sensitivity"] = (1 - grouped["gold_sensitivity"] / grouped["questions_in"]).round(3)
    print(grouped.to_string())
    reasons = Counter((row["parser"], row["corpus"], reason) for row in summary if not row["keep_primary"]
                      for reason in set(row["reasons"]))
    print("drop reasons (dropped questions, primary; a question can have several):")
    print("\n".join(f"  {parser} {corpus}: {reason} {count}" for (parser, corpus, reason), count in sorted(reasons.items())))
    for parser in parsers:
        empty = {(doc_id, page["page"]) for doc_id in shapes.loc[shapes["corpus"] == EMPTY_INDUSTRIAL, "doc_id"].unique()
                 for page in load_document(parser, doc_id)["pages"] if page["start_char"] == page["end_char"]}
        hits = shapes[[(doc_id, page) in empty for doc_id, page in zip(shapes["doc_id"], shapes["page"])]]
        print(f"{parser}: Industrial pages without text {len(empty)} | score-2 pages on them:",
              len(hits), sorted(set(zip(hits["doc_id"], hits["page"]))))


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--parsers", nargs="+", default=list(EXTRACTION_RUNS), choices=list(EXTRACTION_RUNS))
    arg_parser.add_argument("--final", action="store_true", help="allow held-out documents (final evaluation only)")
    args = arg_parser.parse_args()

    queries = [json.loads(line) for line in QUERIES_FILE.read_text(encoding="utf-8").splitlines()]
    refuse_early(queries, args.parsers, args.final)

    catalog = pd.read_csv(PDF_MANIFEST).set_index("doc_id")
    split = pd.read_csv(PROJECT_ROOT / "pdfs" / "split.csv").set_index("doc_id")["split"].to_dict()
    doc_ids = sorted({query["doc_id"] for query in queries})
    if {split.get(doc_id) for doc_id in doc_ids} != {"held_out_2"}:
        raise SystemExit("queries.jsonl holds documents outside held_out_2")
    numbers = [page["page_number_in_doc"] for query in queries for page in query["pages"]]
    over = [query["doc_id"] for query in queries for page in query["pages"]
            if page["page_number_in_doc"] >= catalog.loc[query["doc_id"], "pages"]]
    print(f"page_number_in_doc min {min(numbers)}, max {max(numbers)}, at or above the document's page count: {len(over)}")
    if min(numbers) != 0 or over:
        raise SystemExit("page numbers are not 0-based within the documents")
    check_extractions(args.parsers, doc_ids)

    logger = CostLogger()
    with logger.stage("image_sizes"):
        sizes = image_sizes(queries, pd.read_csv(PICKS_FILE).groupby("corpus")["revision"].first().to_dict())
    with logger.stage("box_evidence"):
        evidence_rows = box_evidence(queries, catalog["file"].to_dict(), sizes)
    SIZES_FILE.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(evidence_rows).drop(columns="evidence").to_csv(SIZES_FILE, index=False)
    EVIDENCE_FILE.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in evidence_rows), encoding="utf-8")

    summary = []
    for parser in args.parsers:
        with logger.stage(f"place:{parser}"):
            spans, parser_summary = place_parser(parser, queries, evidence_rows, split)
        (GOLD_DIR / f"h2_spans_{parser}.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in spans), encoding="utf-8")
        summary += parser_summary

    inputs = [QUERIES_FILE, PICKS_FILE, *(PROJECT_ROOT / catalog.loc[doc_id, "file"] for doc_id in doc_ids),
              *(PROJECT_ROOT / "data" / "extracted" / parser / f"{doc_id}.json" for parser in args.parsers for doc_id in doc_ids)]
    stack = {"evidence_reader": "pdfplumber extract_words (defaults)", "placement": "P1 place + certain, no drop rule",
             "extraction_runs": {parser: EXTRACTION_RUNS[parser] for parser in args.parsers}}
    manifest = build_manifest(new_run_id(1, "H2-GOLD"), SPEC_VERSION, stack, inputs, outputs_for(args.parsers),
                              logger.summary(), "laptop")
    print("manifest:", write_manifest(manifest))
    report(evidence_rows, summary, args.parsers)


if __name__ == "__main__":
    main()
