"""Extension diagnostics (spec v1.2, note "Diagnostics before reading any diagnostic result", 2026-11-19), read-only:
(1) each new setup rebuilt with the frozen chunker code and checked against its rules; (2) size against the RQ2
size-recall curve; (3) section_table prefix cost; (4) failure cases of docling_hybrid and section_table against the
reference; (5) suspicious chunks. Tuning only, hybrid, Recall@1,250. Tables in data/results/ext/diagnostics/; no run
record and no chunk, rule or score change. The functions under "Added after first results (post-hoc)" were not in the
pre-written definitions: token-weighted sizes, causes of unlocated HybridChunker chunks, and what ranks above the gold
chunk; their tables are prefixed posthoc_."""
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.p3_score import CHUNKS, EXTRACTED, gold_questions, load_chunks
from scripts.p3_size_by_source import measured_sizes
from scripts.p4_analyse import in_scope, question_matrix
from src.chunk.base import MAX_TOKENS, build_chunks, section_nodes, table_header, token_counts
from src.chunk.chunkers import CHUNKERS
from src.chunk.dynamic import HIGH, LOW, dynamic_token_cuts, units_of
from src.chunk.hybrid import INPUT_FOLDERS, LIST_BULLET, SPACE, hybrid_report
from src.chunk.method1 import SENTENCE_END, tree_nodes, with_blocks
from src.chunk.section_table import build_chunks_keeping_rows, tables_of
from src.common.paths import RESULTS
from src.common.split import tuning_ids
from src.eval.embed import check_embedder, text_key
from src.eval.score import BM25, Gold, dense_ranking, hybrid_ranking, measure
from src.eval.stats import SEED

TUNING_RUN, EXTENSION_RUN = "P3-LOCAL-20261105-4", "P3-EXT-KN01-20261118-2"
REFERENCE = ("docling", "langchain_recursive_size256_overlap0_noprefix")
SETUPS = [("docling", "paragraph_group_noprefix"), ("docling", "dynamic_token_noprefix"),
          ("pdfplumber", "dynamic_token_noprefix"), ("docling", "section_table_prefix"),
          ("pdfplumber", "section_table_prefix"), ("docling", "docling_hybrid_noprefix")]
LOSERS = [("docling", "docling_hybrid_noprefix"), ("docling", "section_table_prefix")]
BUDGET, FAR_BELOW, DRAWN = 1250, 0.5, 10
EMBEDDINGS = RESULTS.parent / "embeddings" / "bge-m3"
OUTPUT = RESULTS / "ext" / "diagnostics"


def chunker_of(setting):
    return next(name for name in CHUNKERS if setting.startswith(name + "_"))


def rebuild(document, setting):
    """Spans and chunks from the frozen chunker code, as p2_chunk builds them (default settings of each chunker)."""
    entry = CHUNKERS[chunker_of(setting)]
    cuts = dynamic_token_cuts(document) if setting.startswith("dynamic_token") else None
    spans = [(start, end) for start, end, reason in cuts] if cuts else entry["function"](document)
    nodes = entry["nodes"](document) if "nodes" in entry else section_nodes(document)
    chunks = (build_chunks_keeping_rows(spans, document, nodes) if setting.startswith("section_table")
              else build_chunks(spans, document, nodes))
    return spans, chunks, cuts


def signature(chunks):
    return [(chunk["start_char"], chunk["end_char"], chunk["prefix"], chunk["token_count"], chunk["prefix_token_count"])
            for chunk in chunks]


def boundary_kind(text, previous_end, next_start, page_ends, block_ends):
    """D3 kind of the break between two consecutive chunks, strongest first."""
    gap = text[previous_end:next_start]
    if any(previous_end <= end <= next_start for end in page_ends) or re.search(r"\n[ \t]*\n", gap):
        return "1 page or blank line"
    if previous_end in block_ends:
        return "2 block end or table edge"
    if previous_end and text[previous_end - 1] in ".!?;।" and gap:
        return "3 sentence end"
    return "4 line end" if "\n" in gap else "5 inside a line"


def paragraph_checks(document, spans, chunks):
    blocks = sorted((element["start_char"], element["end_char"]) for element in document["elements"])
    windows = {(start, end) for start, end in spans}
    sizes = Counter(sum(start <= block[0] and block[1] <= end for block in blocks) for start, end in spans)
    pairs = list(zip(chunks, chunks[1:]))
    return {"blocks": len(blocks), "windows": len(spans), "windows_2_blocks": sizes[2],
            "windows_other_blocks": len(spans) - sizes[2],
            "chunks_equal_a_window": sum((chunk["start_char"], chunk["end_char"]) in windows for chunk in chunks),
            "boundaries": len(pairs), "overlap_kept": sum(after["start_char"] < before["end_char"] for before, after in pairs)}


def dynamic_checks(document, chunks, cuts):
    text, docling = document["text"], document["parser"]["name"] == "docling"
    blocked = with_blocks(document)
    units, reasons = units_of(blocked, text), Counter(reason for start, end, reason in cuts)
    windows = [text[start:end] for start, end, reason in cuts if reason == "window"]
    window_tokens = token_counts(windows)
    tokens = np.array([chunk["token_count"] for chunk in chunks])
    pairs = list(zip(chunks, chunks[1:]))
    boundaries = [(before["end_char"], after["start_char"]) for before, after in pairs]
    page_ends = [page["end_char"] for page in document["pages"][:-1]]
    block_ends = {edge for element in blocked["elements"] for edge in
                  ([element["end_char"]] + ([element["start_char"]] if element["label"] == "table" else []))} if docling else set()
    kinds = Counter(boundary_kind(text, end, start, page_ends, block_ends) for end, start in boundaries)

    def cut_inside(unit):
        return [(end, start) for end, start in boundaries if unit[0] < end < unit[1] or unit[0] < start < unit[1]]

    fitting = [unit for unit in units if unit[2] <= MAX_TOKENS]
    large_tables = [unit for unit in units if unit[2] > MAX_TOKENS and unit[3]]
    return {"chunks": len(chunks), "cuts_window": reasons["window"], "cuts_D4": reasons["D4"], "cuts_D5": reasons["D5"],
            "cuts_D6": reasons["D6"], "windows_recounted_over_512": sum(count > HIGH for count in window_tokens),
            "windows_recounted_under_128": sum(count < LOW for count in window_tokens),
            "tokens_128_512": int(((tokens >= LOW) & (tokens <= HIGH)).sum()), "tokens_under_128": int((tokens < LOW).sum()),
            "tokens_under_128_not_last": int((tokens[:-1] < LOW).sum()), "tokens_513_1024": int(((tokens > HIGH) & (tokens <= MAX_TOKENS)).sum()),
            "tokens_at_least_1000": int((tokens >= 1000).sum()), "tokens_over_1024": int((tokens > MAX_TOKENS).sum()),
            "units_D4": len(units), "units_tables": sum(unit[3] for unit in units),
            "D4_violations": sum(bool(cut_inside(unit)) for unit in fitting),
            "D5_cuts_not_at_line_end": sum("\n" not in text[end:start] for unit in large_tables for end, start in cut_inside(unit)),
            **{f"break {kind}": count for kind, count in kinds.items()}}


def section_checks(document, chunks):
    text, nodes = document["text"], tree_nodes(document)
    tables, elements = tables_of(document), document.get("elements", [])
    tops = [node["start_char"] for node in nodes if node["parent_id"] is None]
    is_row = [any(start <= chunk["start_char"] and chunk["end_char"] <= end for start, end in tables) for chunk in chunks]
    rows = [chunk for chunk, row in zip(chunks, is_row) if row]
    others = [chunk for chunk, row in zip(chunks, is_row) if not row]
    expected = [(header + "\n") if (header := table_header((chunk["start_char"], chunk["end_char"]), elements, text)) else None
                for chunk in chunks]
    per_section = Counter(sum(top <= chunk["start_char"] for top in tops) for chunk in others)
    return {"sections": len(tops), "tables": len(tables), "row_chunks": len(rows), "section_chunks": len(others),
            "row_chunks_under_100": sum(chunk["token_count"] < 100 for chunk in rows),
            "row_chunks_more_than_one_row": sum(any(any(char.isalnum() for char in line)
                                                    for line in chunk["text"].split("\n")[1:]) for chunk in rows),
            "section_chunks_holding_2plus_sections": sum(any(chunk["start_char"] < top < chunk["end_char"] for top in tops)
                                                         for chunk in others),
            "sections_in_2plus_chunks": sum(count > 1 for count in per_section.values()),
            "chunks_with_prefix": sum(bool(chunk["prefix"]) for chunk in chunks),
            "prefix_not_own_table_header": sum(chunk["prefix"] != want for chunk, want in zip(chunks, expected)),
            "prefix_on_section_chunk": sum(bool(chunk["prefix"]) for chunk in others)}


def hybrid_checks(document):
    text = document["text"]
    saved = json.loads((INPUT_FOLDERS[""] / f"{document['doc_id']}.json").read_text(encoding="utf-8"))
    squeezed = "".join(char for char in text if not char.isspace())
    after, gap = 0, 0
    for chunk in saved["chunks"]:
        target = SPACE.sub("", LIST_BULLET.sub("", chunk["text"]))
        found = squeezed.find(target, after) if target else -1
        if found >= 0:
            gap, after = gap + found - after, found + len(target)
    headings = sum(len(SPACE.sub("", text[element["start_char"]:element["end_char"]]))
                   for element in document["elements"] if element["label"] in {"title", "section_header"})
    report = hybrid_report(document)
    return {"hybrid_chunks": report["hybrid_chunks"], "located": report["located"], "unlocated": report["unlocated"],
            "unlocated_chars": report["unlocated_chars"], "unlocated_labels": " ".join(report["unlocated_labels"]),
            "gap_chars": gap + len(squeezed) - after, "heading_chars": headings, "document_chars": len(squeezed)}


def suspicious(text, chunks, setting):
    spans = [(chunk["start_char"], chunk["end_char"]) for chunk in chunks]
    covered = np.zeros(len(text), dtype=bool)
    for start, end in spans:
        covered[max(start, 0):max(end, 0)] = True
    return {"empty": sum(not chunk["text"].strip() for chunk in chunks), "zero_tokens": sum(chunk["token_count"] == 0 for chunk in chunks),
            "no_letter_or_digit": sum(not any(char.isalnum() for char in chunk["text"]) for chunk in chunks),
            "duplicate_spans": len(spans) - len(set(spans)),
            "duplicate_texts": len(chunks) - len({chunk["text"] for chunk in chunks}),
            "text_over_1024": sum(chunk["token_count"] > MAX_TOKENS for chunk in chunks),
            "text_and_prefix_over_1024": sum(chunk["token_count"] + chunk["prefix_token_count"] > MAX_TOKENS for chunk in chunks),
            "offsets_outside": sum(not 0 <= start < end <= len(text) for start, end in spans),
            "text_not_span": sum(text[chunk["start_char"]:chunk["end_char"]] != chunk["text"] for chunk in chunks),
            "overlaps": sum(after[0] < before[1] for before, after in zip(spans, spans[1:])),
            "prefix_where_none_expected": 0 if setting.startswith("section_table") else sum(bool(chunk["prefix"]) for chunk in chunks),
            "uncovered_nonspace_chars": sum(1 for index in np.flatnonzero(~covered) if not text[index].isspace())}


def check_rules(docs):
    rule_rows, suspicious_rows = [], []
    for parser, setting in SETUPS:
        for doc in docs:
            document = json.loads((EXTRACTED / parser / f"{doc}.json").read_text(encoding="utf-8"))
            saved = json.loads((CHUNKS / parser / setting / f"{doc}.json").read_text(encoding="utf-8"))["chunks"]
            spans, chunks, cuts = rebuild(document, setting)
            row = {"parser": parser, "setting": setting, "doc_id": doc, "reproduced": signature(chunks) == signature(saved)}
            if setting.startswith("paragraph_group"):
                row.update(paragraph_checks(document, spans, saved))
            elif setting.startswith("dynamic_token"):
                row.update(dynamic_checks(document, saved, cuts))
            elif setting.startswith("section_table"):
                row.update(section_checks(document, saved))
            else:
                row.update(hybrid_checks(document), chunks=len(saved), chunks_over_512=sum(chunk["token_count"] > 512 for chunk in saved))
            rule_rows.append(row)
            suspicious_rows.append({"parser": parser, "setting": setting, "doc_id": doc, **suspicious(document["text"], saved, setting)})
        print(f"rules checked: {parser}/{setting}")
    return pd.DataFrame(rule_rows), pd.DataFrame(suspicious_rows)


def curve_fit(scores, parser):
    """Recall and measured size of the in-scope existing settings and the new setups on shared questions, and the
    least-squares line of recall on log(size) over the existing ones."""
    frame = scores[scores["parser"] == parser]
    new = [setting for setup_parser, setting in SETUPS if setup_parser == parser]
    existing = in_scope(set(frame["setting"]) - set(new))
    questions = question_matrix(frame, existing + new)[0]
    recall, sizes = questions.groupby(level="doc_id").mean().mean(), measured_sizes(questions)
    old = [f"{parser}/{setting}" for setting in existing]
    return questions, recall, sizes, old, new, np.polyfit(np.log(sizes[old]), recall[old], 1)


def size_curve(scores):
    """(2) per parser: measured size and recall of every in-scope existing setting and the new setups, on shared questions."""
    rows = []
    for parser in ["docling", "pdfplumber"]:
        questions, recall, sizes, old, new, (slope, intercept) = curve_fit(scores, parser)
        residual_sd = np.std(recall[old] - (intercept + slope * np.log(sizes[old])), ddof=2)
        for setting in new:
            setup = f"{parser}/{setting}"
            predicted = intercept + slope * np.log(sizes[setup])
            nearest = (np.log(sizes[old]) - np.log(sizes[setup])).abs().nsmallest(3).index
            rows.append({"parser": parser, "setting": setting, "documents": questions.index.get_level_values(0).nunique(),
                         "questions": len(questions), "measured_size": sizes[setup], "recall": recall[setup],
                         "curve_recall": predicted, "residual": recall[setup] - predicted, "residual_sd": residual_sd,
                         "size_range": f"{sizes[old].min():.0f}-{sizes[old].max():.0f}",
                         "on_curve": bool(abs(recall[setup] - predicted) <= 2 * residual_sd
                                          and sizes[old].min() <= sizes[setup] <= sizes[old].max()),
                         "nearest_existing": "; ".join(f"{name.split('/')[1]} {sizes[name]:.0f} tok {recall[name]:.3f}" for name in nearest),
                         "nearest_mean_recall": recall[nearest].mean()})
    return pd.DataFrame(rows)


def chunk_sizes():
    rows = []
    for parser, setting in SETUPS:
        tokens = np.array([chunk["token_count"] + chunk["prefix_token_count"]
                           for path in sorted((CHUNKS / parser / setting).glob("*.json"))
                           for chunk in json.loads(path.read_text(encoding="utf-8"))["chunks"]])
        rows.append({"parser": parser, "setting": setting, "chunks": len(tokens), "mean_tokens": tokens.mean(),
                     "median_tokens": float(np.median(tokens)), "max_tokens": int(tokens.max())})
    return pd.DataFrame(rows)


def load_vectors():
    """bge-m3 cache parts of the tuning runs and the extension run only (held-out parts are not opened)."""
    check_embedder(EMBEDDINGS)
    keys, parts = [], []
    for keys_path in sorted(EMBEDDINGS.glob("*.keys.json")):
        if "heldout" in keys_path.name.lower() or not keys_path.name.startswith(("P3-KN", "EXT-KN")):
            continue
        keys += json.loads(keys_path.read_text(encoding="utf-8"))
        parts.append(np.load(keys_path.with_name(keys_path.name.replace(".keys.json", ".npy"))))
    return {key: row for row, key in enumerate(keys)}, np.vstack(parts)


class Ranker:
    """scorer_v1 hybrid ranking of one setup's chunks for one document, and its Recall@1,250."""

    def __init__(self, parser, setting, doc, text, cache):
        self.chunks, self.text = load_chunks(CHUNKS / parser / setting / f"{doc}.json"), text
        self.bm25, self.cache = BM25([chunk["index_text"] for chunk in self.chunks]), cache
        self.vectors = cache[1][[cache[0][text_key(chunk["index_text"])] for chunk in self.chunks]]

    def order(self, question):
        dense = dense_ranking(self.cache[1][self.cache[0][text_key(question)]], self.vectors)
        return hybrid_ranking(self.bm25.ranking(question), dense)

    def evaluate(self, question, gold):
        order = self.order(question)
        chunk_gold = [gold.inside(chunk["start"], chunk["end"]) for chunk in self.chunks]
        holding = [index for index, value in enumerate(chunk_gold) if value > 0]
        main = int(np.argmax(chunk_gold))
        rank = {index: position for position, index in enumerate(order, start=1)}
        return {"recall": measure(order, self.chunks, self.text, gold, BUDGET, chunk_gold)["recall"],
                "gold_chunks": len(holding), "whole_in_one": gold.whole_in(self.chunks),
                "main_chunk_tokens": self.chunks[main]["tokens"] + self.chunks[main]["prefix_tokens"],
                "main_chunk_rank": rank[main], "first_gold_rank": min(rank[index] for index in holding),
                "chunks_in_document": len(self.chunks)}


def prefix_cost(scores, docs, cache):
    """(3) section_table: prefix tokens read within the budget per question (chunks are disjoint, so each read chunk
    costs its prefix plus its text, the last cut at the budget), checked against the stored tokens read."""
    rows = []
    for parser in ["docling", "pdfplumber"]:
        questions = gold_questions(parser, docs)[0]
        stored = scores[(scores["parser"] == parser) & (scores["setting"] == "section_table_prefix")].set_index("question_id")
        for doc in docs:
            text = json.loads((EXTRACTED / parser / f"{doc}.json").read_text(encoding="utf-8"))["text"]
            ranker = None
            for question_id, question in questions.items():
                if question["doc_id"] != doc or question_id not in stored.index:
                    continue
                ranker = ranker or Ranker(parser, "section_table_prefix", doc, text, cache)
                used = prefix = read = 0
                for index in ranker.order(question["question"]):
                    if used >= BUDGET:
                        break
                    chunk = ranker.chunks[index]
                    prefix += min(chunk["prefix_tokens"], BUDGET - used)
                    used = min(used + chunk["prefix_tokens"] + chunk["tokens"], BUDGET)
                    read += 1
                rows.append({"parser": parser, "doc_id": doc, "question_id": question_id, "chunks_read": read,
                             "prefix_tokens_read": prefix, "prefix_share": prefix / BUDGET, "tokens_read": used,
                             "stored_tokens_read": stored.loc[question_id, "tokens_read"]})
    return pd.DataFrame(rows)


def failures(scores, docs, cache):
    """(4) far-below questions of each loser against the reference; DRAWN of them in detail (seed 42)."""
    questions = gold_questions("docling", docs)[0]
    texts = {doc: json.loads((EXTRACTED / "docling" / f"{doc}.json").read_text(encoding="utf-8"))["text"] for doc in docs}
    nonspace = {doc: np.concatenate([[0], np.cumsum([not char.isspace() for char in text])]) for doc, text in texts.items()}
    recall = scores[scores["parser"] == "docling"].pivot_table(index="question_id", columns="setting", values="recall")
    detail, overview, rankers = [], [], {}

    def ranker(setting, doc):
        if (setting, doc) not in rankers:
            rankers[setting, doc] = Ranker("docling", setting, doc, texts[doc], cache)
        return rankers[setting, doc]

    for parser, setting in LOSERS:
        difference = (recall[setting] - recall[REFERENCE[1]]).dropna()
        far = sorted(difference[difference <= -FAR_BELOW].index)
        drawn = set(np.random.default_rng(SEED).choice(far, size=min(DRAWN, len(far)), replace=False))
        for question_id in far:
            question = questions[question_id]
            gold = Gold(question["pieces"], nonspace[question["doc_id"]])
            new, old = (ranker(name, question["doc_id"]).evaluate(question["question"], gold) for name in (setting, REFERENCE[1]))
            row = {"setting": setting, "question_id": question_id, "doc_id": question["doc_id"], "source": question["source"],
                   "question": question["question"], "stored_recall": recall.loc[question_id, setting],
                   "stored_reference_recall": recall.loc[question_id, REFERENCE[1]],
                   **new, **{f"reference_{key}": value for key, value in old.items()}}
            overview.append(row)
            if question_id in drawn:
                detail.append(row)
    return pd.DataFrame(detail), pd.DataFrame(overview)


# Added after first results (post-hoc): not in the pre-written definitions of 2026-11-19.

def weighted_sizes(scores):
    """Post-hoc. Token-weighted chunk size (the size of the chunk an average token sits in, pooled over the tuning
    documents, with prefix), the share of tokens in chunks of at least 900, and the curve recall at that size (same fit
    as size_curve, size measured differently, so a check rather than a placement)."""
    rows = []
    for parser in ["docling", "pdfplumber"]:
        questions, recall, sizes, old, new, (slope, intercept) = curve_fit(scores, parser)
        for setting in new + ([REFERENCE[1]] if parser == REFERENCE[0] else []):
            tokens = np.array([chunk["token_count"] + chunk["prefix_token_count"]
                               for path in sorted((CHUNKS / parser / setting).glob("*.json"))
                               for chunk in json.loads(path.read_text(encoding="utf-8"))["chunks"]])
            weighted = (tokens ** 2).sum() / tokens.sum()
            rows.append({"parser": parser, "setting": setting, "mean_tokens": tokens.mean(), "token_weighted_size": weighted,
                         "share_tokens_in_chunks_900plus": tokens[tokens >= 900].sum() / tokens.sum(),
                         "recall": recall[f"{parser}/{setting}"], "curve_recall_at_weighted": intercept + slope * np.log(weighted),
                         "residual_at_weighted": recall[f"{parser}/{setting}"] - (intercept + slope * np.log(weighted))})
    return pd.DataFrame(rows)


LIST_NUMBER, MARKUP = re.compile(r"\d+(\.\d+)*\.?"), set("[]()<`*_#|=")


def matched_length(squeezed, target, after):
    """Longest prefix of target found in squeezed from after on (binary search)."""
    low, high = 0, len(target)
    while low < high:
        middle = (low + high + 1) // 2
        low, high = (middle, high) if squeezed.find(target[:middle], after) >= 0 else (low, middle - 1)
    return low


def unlocated_causes(docs):
    """Post-hoc. Each HybridChunker chunk the in-order search (hybrid rule 4) does not locate, by the first place its
    serialised text departs from the frozen text: table (rule 5's case), table of contents (document_index), list
    number inserted, markup added (links, checkboxes, formula or code marks), other; and whether it is found earlier."""
    rows = []
    for doc in docs:
        text = json.loads((EXTRACTED / "docling" / f"{doc}.json").read_text(encoding="utf-8"))["text"]
        squeezed, after = "".join(char for char in text if not char.isspace()), 0
        for chunk in json.loads((INPUT_FOLDERS[""] / f"{doc}.json").read_text(encoding="utf-8"))["chunks"]:
            target = SPACE.sub("", LIST_BULLET.sub("", chunk["text"]))
            found = squeezed.find(target, after) if target else -1
            if found >= 0:
                after = found + len(target)
                continue
            depart = matched_length(squeezed, target, after)
            number = LIST_NUMBER.match(target, depart)
            cause = ("table" if "table" in chunk["labels"] else "table of contents" if "document_index" in chunk["labels"]
                     else "list number inserted" if number and number.end() > depart
                     else "markup added" if depart < len(target) and target[depart] in MARKUP else "other")
            rows.append({"doc_id": doc, "cause": cause, "labels": " ".join(sorted(set(chunk["labels"]))),
                         "characters": len(target), "matched_before_departure": depart,
                         "found_earlier": bool(target) and squeezed.find(target) >= 0,
                         "at_departure": target[depart:depart + 40]})
    return pd.DataFrame(rows)


def above_gold(overview, cache):
    """Post-hoc. For each far-below question of the losers: the chunks the hybrid ranking puts above the chunk holding
    most gold, how many lie inside a table (row chunks in section_table), their tokens, and the tokens before the gold."""
    rows = []
    for (setting, doc), group in overview.groupby(["setting", "doc_id"]):
        document = json.loads((EXTRACTED / "docling" / f"{doc}.json").read_text(encoding="utf-8"))
        nonspace = np.concatenate([[0], np.cumsum([not char.isspace() for char in document["text"]])])
        spans, questions = tables_of(document), gold_questions("docling", [doc])[0]
        ranker = Ranker("docling", setting, doc, document["text"], cache)
        for question_id in group["question_id"]:
            question = questions[question_id]
            gold = Gold(question["pieces"], nonspace)
            order = list(ranker.order(question["question"]))
            main = int(np.argmax([gold.inside(chunk["start"], chunk["end"]) for chunk in ranker.chunks]))
            above = [ranker.chunks[index] for index in order[:order.index(main)]]
            in_table = [any(start <= chunk["start"] and chunk["end"] <= end for start, end in spans) for chunk in above]
            sizes = [chunk["tokens"] + chunk["prefix_tokens"] for chunk in above]
            rows.append({"setting": setting, "doc_id": doc, "question_id": question_id, "chunks_above_gold": len(above),
                         "table_chunks_above": sum(in_table), "other_chunks_above": len(above) - sum(in_table),
                         "tokens_above_gold": sum(sizes),
                         "other_chunk_tokens_median": float(np.median([size for size, table in zip(sizes, in_table) if not table]))
                         if len(above) > sum(in_table) else np.nan})
    return pd.DataFrame(rows)


def main():
    docs = sorted(tuning_ids())
    scores = pd.concat([pd.read_csv(RESULTS / "p3" / f"{run}.csv.gz") for run in (TUNING_RUN, EXTENSION_RUN)])
    scores = scores[(scores["retriever"] == "hybrid") & (scores["budget"] == BUDGET) & (scores["source"].str.lower() != "qasper")]
    if set(scores["doc_id"]) - set(docs):
        raise SystemExit(f"documents outside the tuning split: {sorted(set(scores['doc_id']) - set(docs))}")
    rules, odd = check_rules(docs)
    sizes, curve = chunk_sizes(), size_curve(scores)
    cache = load_vectors()
    scored = sorted(scores["doc_id"].unique())
    prefix, (detail, overview) = prefix_cost(scores, scored, cache), failures(scores, scored, cache)
    weighted, causes, ranked_above = weighted_sizes(scores), unlocated_causes(docs), above_gold(overview, cache)

    setup_keys = ["parser", "setting"]
    tables = {"rules_per_document": rules, "rules_summary": rules.drop(columns=["doc_id", "unlocated_labels"], errors="ignore")
              .groupby(setup_keys).agg(lambda column: column.all() if column.dtype == bool else column.sum()).reset_index(),
              "suspicious_per_document": odd, "suspicious_summary": odd.drop(columns="doc_id").groupby(setup_keys).sum().reset_index(),
              "chunk_sizes": sizes, "size_curve": curve, "prefix_cost_questions": prefix,
              "prefix_cost_summary": prefix.groupby("parser").agg(questions=("question_id", "size"), chunks_read=("chunks_read", "mean"),
                                                                 prefix_tokens_read=("prefix_tokens_read", "mean"),
                                                                 prefix_share=("prefix_share", "mean"),
                                                                 prefix_share_max=("prefix_share", "max")).reset_index(),
              "failures_drawn": detail, "failures_all": overview,
              "failures_overview": overview.groupby("setting").agg(
                  far_below=("question_id", "size"), whole_in_one=("whole_in_one", "mean"),
                  gold_chunks_median=("gold_chunks", "median"), main_rank_median=("main_chunk_rank", "median"),
                  main_tokens_median=("main_chunk_tokens", "median"), reference_whole_in_one=("reference_whole_in_one", "mean"),
                  reference_gold_chunks_median=("reference_gold_chunks", "median"),
                  reference_main_rank_median=("reference_main_chunk_rank", "median"),
                  reference_main_tokens_median=("reference_main_chunk_tokens", "median")).reset_index(),
              "posthoc_weighted_sizes": weighted, "posthoc_unlocated_chunks": causes,
              "posthoc_unlocated_summary": causes.groupby("cause").agg(
                  chunks=("doc_id", "size"), documents=("doc_id", "nunique"), characters=("characters", "sum"),
                  found_earlier=("found_earlier", "sum")).reset_index(),
              "posthoc_above_gold": ranked_above,
              "posthoc_above_gold_summary": ranked_above.groupby("setting").agg(
                  questions=("question_id", "size"), chunks_above=("chunks_above_gold", "sum"),
                  table_chunks_above=("table_chunks_above", "sum"), other_chunks_above=("other_chunks_above", "sum"),
                  tokens_above_median=("tokens_above_gold", "median"),
                  share_1250_plus_above=("tokens_above_gold", lambda tokens: (tokens >= BUDGET).mean()),
                  other_chunk_tokens_median=("other_chunk_tokens_median", "median")).reset_index()}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        table.to_csv(OUTPUT / f"{name}.csv", index=False)

    checks = {"recomputed recall equals stored (failure questions)":
              bool(np.allclose(overview["recall"], overview["stored_recall"]) and
                   np.allclose(overview["reference_recall"], overview["stored_reference_recall"])),
              "recomputed tokens read equal stored (prefix cost)": bool((prefix["tokens_read"] == prefix["stored_tokens_read"]).all())}
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 60)
    pd.set_option("display.max_colwidth", 70)
    for name in ["rules_summary", "suspicious_summary", "chunk_sizes", "size_curve", "prefix_cost_summary", "failures_overview",
                 "posthoc_weighted_sizes", "posthoc_unlocated_summary", "posthoc_above_gold_summary"]:
        print(f"\n== {name}\n{tables[name].round(3).T.to_string() if name.endswith('summary') and 'unlocated' not in name else tables[name].round(3).to_string(index=False)}")
    columns = ["setting", "doc_id", "question", "recall", "reference_recall", "gold_chunks", "whole_in_one", "main_chunk_tokens",
               "main_chunk_rank", "reference_gold_chunks", "reference_main_chunk_tokens", "reference_main_chunk_rank"]
    print(f"\n== failures_drawn\n{detail[columns].round(2).to_string(index=False)}\n\nchecks: {checks}\ntables: {OUTPUT}")


if __name__ == "__main__":
    main()
