"""GOLDEN_200 validity check (spec v1.2, 2026-11-14), tuning documents only.
Stage 'sample': 20 random questions per document (seed 42) as batch 1. Stage 'label': terminal labelling by the author
(y valid / n invalid / s unsure, optional note), saved after every label, 20 per session, resumable. Key m shows a longer
context. Stage 'expand': one more batch of 20 for a document whose batch-1 invalid count is 3 or more. Stage 'review'
(added after batch 1): a reason for each invalid or unsure label, with a longer context. Stage 'report': invalid and
defect rates with Wilson 95% intervals. No LLM call. The held-out document D2 is never read."""
import argparse
import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src.common.paths import EXTRACTED, GOLD, PROJECT_ROOT, RESULTS
from src.common.split import tuning_ids
from src.gold.matching import page_bounds

DOCS = {"indian_d1": "D1", "indian_d3_fundamental_rules": "D3_Fundamental_Rules", "indian_d4_rti_act": "D4_RTI_Act"}
SOURCE = PROJECT_ROOT / "data" / "external" / "indian_regulatory"
OUTPUT = RESULTS / "golden_check"
SAMPLE_FILE, LABELS_FILE, REASONS_FILE = OUTPUT / "sample.csv", OUTPUT / "labels.csv", OUTPUT / "reasons.csv"
SEED, BATCH, CONTEXT, LONG_CONTEXT, EXPAND_AT, Z, WIDTH = 42, 20, 600, 2000, 3, 1.96, 80
KEYS = {"y": "valid", "n": "invalid", "s": "unsure"}
LABEL_COLUMNS = ["doc_id", "question_id", "label", "note", "labelled_at"]
REASONS = {"1": "question unclear", "2": "evidence does not answer", "3": "gold answer wrong",
           "4": "context too short (not a defect)", "5": "other"}
DEFECTS, OTHER = {"1", "2", "3"}, "5"
REASON_COLUMNS = ["doc_id", "question_id", "reason", "reason_text", "note", "reviewed_at"]


def checked_docs():
    """The three Indian documents, each confirmed as tuning in pdfs/split.csv (raises otherwise)."""
    held_out = sorted(set(DOCS) - tuning_ids())
    if held_out:
        raise ValueError(f"not tuning documents, refusing to read: {held_out}")
    return DOCS


def questions(doc):
    return json.loads((SOURCE / f"{checked_docs()[doc]}_GOLDEN_200.json").read_text(encoding="utf-8"))


def certain_flags(doc):
    """question_id -> True if the study's Docling gold for it is certain (every evidence piece placed and certain)."""
    rows = [json.loads(line) for line in (GOLD / "spans_docling.jsonl").read_text(encoding="utf-8").splitlines()
            if f'"doc_id": "{doc}"' in line]
    return pd.DataFrame(rows).groupby("question_id")["certain"].all().to_dict()


def batch_rows(doc, batch):
    """Batch n (1-based) of the document's seed-42 permutation of its 200 question ids."""
    items = questions(doc)
    order = np.random.default_rng(SEED).permutation(len(items))[(batch - 1) * BATCH:batch * BATCH]
    flags = certain_flags(doc)
    return [{"doc_id": doc, "question_id": items[index]["id"], "batch": batch, "certain": flags.get(items[index]["id"], False)}
            for index in order]


def draw_sample():
    if SAMPLE_FILE.exists():
        raise FileExistsError(f"{SAMPLE_FILE} exists; the sample is drawn once")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    sample = pd.DataFrame([row for doc in checked_docs() for row in batch_rows(doc, 1)])
    sample.to_csv(SAMPLE_FILE, index=False)
    print(sample.groupby("doc_id").agg(questions=("question_id", "size"), certain=("certain", "sum")).to_string())
    print(f"saved {SAMPLE_FILE}")


def load_csv(path, columns):
    return pd.read_csv(path, dtype=str, keep_default_na=False) if path.exists() else pd.DataFrame(columns=columns)


def load_labels():
    return load_csv(LABELS_FILE, LABEL_COLUMNS)


def context(doc, question_id, item, size=CONTEXT):
    """About size characters of the Docling extraction around the study's placement of the first evidence string."""
    extraction = json.loads((EXTRACTED / "docling" / f"{doc}.json").read_text(encoding="utf-8"))
    text = extraction["text"]
    spans = [json.loads(line) for line in (GOLD / "spans_docling.jsonl").read_text(encoding="utf-8").splitlines()
             if f'"question_id": "{question_id}"' in line and f'"doc_id": "{doc}"' in line]
    placed = sorted((span for span in spans if span["start"] is not None), key=lambda span: span["start"])
    if placed:
        start, end = placed[0]["start"], placed[0]["end"]
        margin = max(0, (size - (end - start)) // 2)
        return (f"{text[max(0, start - margin):start]}>>>{text[start:end]}<<<{text[end:end + margin]}",
                "evidence as placed by the study (Docling)")
    pages = [int(word) for location in item["source_location"] for word in location.split() if word.isdigit()][:1]
    bounds = page_bounds(extraction["pages"], pages[0]) if pages else None
    if bounds:
        return text[bounds[0]:bounds[0] + size], f"evidence NOT placed by the study; start of cited page {pages[0]}"
    return "", "evidence NOT placed by the study and no page cited"


def context_block(row, item, size=CONTEXT):
    """The context between two lines of =, labelled CONTEXT (LONGER CONTEXT for more than the default size)."""
    shown, where = context(row.doc_id, row.question_id, item, size)
    equals = "=" * WIDTH
    return f"{equals}\n{'CONTEXT' if size == CONTEXT else f'LONGER CONTEXT, {size:,} characters'} ({where}):\n{shown}\n{equals}"


def screen(count, total, row, item):
    """The text shown for one question: progress line, question, answer and evidence in *, context in =."""
    evidence = "\n".join(f"  - {piece}" for piece in item["required_evidence"])
    progress = f"---- {count} / {total} · {DOCS[row.doc_id].split('_')[0]} · {row.question_id} "
    stars = "*" * WIDTH
    return (f"\n{progress.ljust(WIDTH, '-')}\nQ: {item['question']}\n{stars}\nANSWER:   {item['answer']}\n"
            f"EVIDENCE:\n{evidence}\nSOURCE:   {', '.join(item['source_location'])}\n{stars}\n{context_block(row, item)}")


def label(ask=input):
    """Label the next BATCH unlabelled sample questions; save after each; m shows a longer context; q quits."""
    sample, labels = pd.read_csv(SAMPLE_FILE, dtype={"question_id": str}), load_labels()
    done = set(zip(labels["doc_id"], labels["question_id"]))
    pending = sample[[(doc, question) not in done for doc, question in zip(sample["doc_id"], sample["question_id"])]]
    print(f"{len(pending)} of {len(sample)} questions to label | y = valid, n = invalid, s = unsure, "
          f"m = {LONG_CONTEXT:,} characters of context, q = quit | "
          f"this session: up to {BATCH}")
    items = {doc: {item["id"]: item for item in questions(doc)} for doc in pending["doc_id"].unique()}
    for count, row in enumerate(pending.head(BATCH).itertuples(), start=1):
        item = items[row.doc_id][row.question_id]
        print(screen(count, min(BATCH, len(pending)), row, item))
        key = ""
        while key not in KEYS and key != "q":
            key = ask("[y] valid [n] invalid [s] unsure [m] more context [q] quit: ").strip().lower()
            if key == "m":
                print(context_block(row, item, LONG_CONTEXT))
        if key == "q":
            break
        note = ask("note (Enter for none): ").strip()
        labels.loc[len(labels)] = [row.doc_id, row.question_id, KEYS[key], note, datetime.now(timezone.utc).isoformat(timespec="seconds")]
        labels.to_csv(LABELS_FILE, index=False)
    print(f"\nlabelled {len(labels)} of {len(sample)} | saved {LABELS_FILE}")


def review(ask=input):
    """A reason for each question labelled invalid or unsure, with a longer context; save after each; q quits."""
    sample, labels = pd.read_csv(SAMPLE_FILE, dtype={"question_id": str}), load_labels()
    reasons = load_csv(REASONS_FILE, REASON_COLUMNS)
    done = set(zip(reasons["doc_id"], reasons["question_id"]))
    flagged = labels[labels["label"].isin(["invalid", "unsure"])].merge(sample, on=["doc_id", "question_id"])
    pending = flagged[[(doc, question) not in done for doc, question in zip(flagged["doc_id"], flagged["question_id"])]]
    choices = " ".join(f"[{key}] {text}" for key, text in REASONS.items())
    print(f"{len(pending)} of {len(flagged)} invalid or unsure questions to review | q = quit")
    items = {doc: {item["id"]: item for item in questions(doc)} for doc in pending["doc_id"].unique()}
    for count, row in enumerate(pending.itertuples(), start=1):
        item = items[row.doc_id][row.question_id]
        print(f"{screen(count, len(pending), row, item)}\nYOUR LABEL: {row.label}"
              f"{f' | note: {row.note}' if row.note else ''}\n{context_block(row, item, LONG_CONTEXT)}")
        key = ""
        while key not in REASONS and key != "q":
            key = ask(f"reason {choices} [q] quit: ").strip().lower()
        if key == "q":
            break
        note = ask("note (required): " if key == OTHER else "note (Enter for none): ").strip()
        while key == OTHER and not note:
            note = ask("note (required): ").strip()
        reasons.loc[len(reasons)] = [row.doc_id, row.question_id, key, REASONS[key], note,
                                     datetime.now(timezone.utc).isoformat(timespec="seconds")]
        reasons.to_csv(REASONS_FILE, index=False)
    print(f"\nreviewed {len(reasons)} of {len(flagged)} | saved {REASONS_FILE}")


def wilson(hits, total, z=Z):
    """Wilson score interval for a proportion hits / total."""
    if total == 0:
        return math.nan, math.nan
    spread = z * math.sqrt(hits * (total - hits) / total + z * z / 4) / total
    centre, scale = (hits + z * z / 2) / total, 1 + z * z / total
    return (centre - spread) / scale, (centre + spread) / scale


def rates(labels):
    """Rows of labelled, invalid, unsure, invalid rate with Wilson interval, and unsure-as-invalid, per group."""
    def row(group):
        total, invalid, unsure = len(group), int((group["label"] == "invalid").sum()), int((group["label"] == "unsure").sum())
        low, high = wilson(invalid, total)
        strict_low, strict_high = wilson(invalid + unsure, total)
        return pd.Series({"labelled": total, "invalid": invalid, "unsure": unsure, "invalid_rate": invalid / total if total else math.nan,
                          "low": low, "high": high, "invalid_or_unsure_rate": (invalid + unsure) / total if total else math.nan,
                          "strict_low": strict_low, "strict_high": strict_high})
    per_doc = labels.groupby("doc_id").apply(row, include_groups=False)
    per_doc.loc["overall"] = row(labels)
    return per_doc


def defect_rates(labels):
    """Per document and overall: the original invalid rate next to the defect rate (reasons 1-3 / labelled) with
    Wilson intervals, reason 4 and 5 counts, the sensitivity rate with reason 5 as a defect, and questions unreviewed."""
    def row(group):
        total, reason = len(group), group["reason"]
        defects, other = int(reason.isin(DEFECTS).sum()), int((reason == OTHER).sum())
        low, high = wilson(defects, total)
        other_low, other_high = wilson(defects + other, total)
        return pd.Series({"labelled": total, "invalid_rate": (group["label"] == "invalid").mean(), "defects": defects,
                          "defect_rate": defects / total, "low": low, "high": high,
                          "too_short": int((reason == "4").sum()), "other": other,
                          "defect_or_other_rate": (defects + other) / total, "other_low": other_low, "other_high": other_high,
                          "unreviewed": int((group["label"].isin(["invalid", "unsure"]) & reason.eq("")).sum())})
    per_doc = labels.groupby("doc_id").apply(row, include_groups=False)
    per_doc.loc["overall"] = row(labels)
    return per_doc


def report():
    sample, labels = pd.read_csv(SAMPLE_FILE, dtype={"question_id": str}), load_labels()
    labels = labels.merge(sample, on=["doc_id", "question_id"])
    pd.set_option("display.width", 200)
    print(f"labelled {len(labels)} of {len(sample)}")
    if labels.empty:
        return
    overall = lambda group: rates(group).loc["overall"]
    by_certain = labels.groupby("certain").apply(overall, include_groups=False)
    by_batch = labels.groupby("batch").apply(overall, include_groups=False)
    print(f"\n{rates(labels).round(3).to_string()}\n\nby the study's certain flag (Docling gold):\n{by_certain.round(3).to_string()}"
          f"\n\nby batch (batch 2 could use key m, {LONG_CONTEXT:,} characters):\n{by_batch.round(3).to_string()}"
          f"\n\nexpansion due (batch 1 invalid >= {EXPAND_AT} of {BATCH}): {expansion_due(labels) or 'none'}")
    reasons = load_csv(REASONS_FILE, REASON_COLUMNS)
    if len(reasons):
        reviewed = labels.merge(reasons[["doc_id", "question_id", "reason", "reason_text"]], how="left",
                                on=["doc_id", "question_id"]).fillna({"reason": "", "reason_text": ""})
        counts = reviewed[reviewed["reason"] != ""].groupby(["reason", "reason_text"]).size().rename("questions")
        print(f"\nreason review (added after batch 1; defect = reasons 1-3; valid labels not re-checked):\n"
              f"{defect_rates(reviewed).round(3).to_string()}\n\nreasons:\n{counts.to_string()}")
        labels = reviewed
    notes = [frame[frame["note"] != ""][["doc_id", "question_id", column, "note"]]
             for frame, column in ((labels, "label"), (reasons, "reason_text"))]
    for title, frame in zip(("label notes", "review notes"), notes):
        if len(frame):
            print(f"\n{title}:\n{frame.to_string(index=False)}")


def expansion_due(labels):
    """Documents with batch 1 fully labelled, invalid count >= EXPAND_AT, and no batch 2 yet."""
    first = labels[labels["batch"] == 1]
    return [doc for doc, group in first.groupby("doc_id")
            if len(group) == BATCH and (group["label"] == "invalid").sum() >= EXPAND_AT and (labels["doc_id"].eq(doc) & labels["batch"].ne(1)).sum() == 0]


def expand(doc):
    sample, labels = pd.read_csv(SAMPLE_FILE, dtype={"question_id": str}), load_labels()
    if doc not in expansion_due(labels.merge(sample, on=["doc_id", "question_id"])) or (sample["doc_id"].eq(doc) & sample["batch"].ne(1)).any():
        raise ValueError(f"{doc}: expansion not due by the spec rule (batch 1 complete with >= {EXPAND_AT} invalid, once only)")
    sample = pd.concat([sample, pd.DataFrame(batch_rows(doc, 2))], ignore_index=True)
    sample.to_csv(SAMPLE_FILE, index=False)
    print(f"{doc}: batch 2 added ({BATCH} questions) | saved {SAMPLE_FILE}")


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--stage", required=True, choices=["sample", "label", "expand", "review", "report"])
    arg_parser.add_argument("--doc", help="document for --stage expand")
    args = arg_parser.parse_args()
    if args.stage == "sample":
        draw_sample()
    elif args.stage == "label":
        label()
    elif args.stage == "expand":
        expand(args.doc)
    elif args.stage == "review":
        review()
    else:
        report()


if __name__ == "__main__":
    main()
