"""P2 answer-split check on the tuning documents: for every chunk setting and parser, the share of certain gold answer
pieces (P1 certain-only, span-level) that no single chunk contains. QASPER is reported separately (spec v1.1).
First checks that gold offsets line up with the extracted text (exact pieces must equal text[start:end])."""
import json
from collections import defaultdict

import pandas as pd

from src.common.manifest import PROJECT_ROOT
from src.common.split import tuning_ids

CHUNKS = PROJECT_ROOT / "data" / "chunks"
EXTRACTED = PROJECT_ROOT / "data" / "extracted"
GOLD = PROJECT_ROOT / "data" / "gold"
OUTPUT = PROJECT_ROOT / "runs" / "analysis" / "p2_answer_split_tuning.csv"


def gold_pieces(parser, tuning):
    """Certain, span-level gold pieces per tuning document: (start, end, source, method, gold text)."""
    pieces = defaultdict(list)
    for line in open(GOLD / f"spans_{parser}.jsonl", encoding="utf-8"):
        record = json.loads(line)
        if record["doc_id"] in tuning and str(record["certain"]) == "True" and record["kind"] == "span" and record["method"] != "page":
            pieces[record["doc_id"]].append((int(record["start"]), int(record["end"]), record["source"], record["method"], record["gold"]))
    return pieces


def alignment(parser, pieces):
    """Share of exact pieces whose text equals the extracted text at their offsets."""
    exact = [(doc_id, piece) for doc_id, doc_pieces in pieces.items() for piece in doc_pieces if piece[3] == "exact"]
    texts = {doc_id: json.loads((EXTRACTED / parser / f"{doc_id}.json").read_text(encoding="utf-8"))["text"] for doc_id in pieces}
    matched = sum(texts[doc_id][piece[0]:piece[1]] == piece[4] for doc_id, piece in exact)
    return matched, len(exact)


def main():
    tuning = tuning_ids()
    rows = []
    for parser in ["docling", "pdfplumber"]:
        pieces = gold_pieces(parser, tuning)
        matched, total = alignment(parser, pieces)
        print(f"{parser}: {sum(map(len, pieces.values()))} certain span pieces on {len(pieces)} tuning documents | "
              f"exact pieces aligned with the text: {matched} of {total}")
        for folder in sorted(path for path in (CHUNKS / parser).iterdir() if path.is_dir()):
            files = {path.stem: path for path in folder.glob("*.json") if path.stem in tuning}
            if len(files) < len(tuning):
                continue
            tokens, outcomes = [], defaultdict(list)
            for doc_id, path in files.items():
                chunks = json.loads(path.read_text(encoding="utf-8"))["chunks"]
                spans = [(chunk["start_char"], chunk["end_char"]) for chunk in chunks]
                tokens += [chunk["token_count"] for chunk in chunks]
                for start, end, source, method, gold in pieces.get(doc_id, []):
                    group = "qasper" if source.lower() == "qasper" else "main"
                    outcomes[group].append(not any(left <= start and end <= right for left, right in spans))
            rows.append({"parser": parser, "setting": folder.name, "median_tokens": int(pd.Series(tokens).median()),
                         "chunks_per_doc": round(len(tokens) / len(files), 1),
                         "main_pieces": len(outcomes["main"]), "main_split_pct": round(100 * sum(outcomes["main"]) / max(len(outcomes["main"]), 1), 1),
                         "qasper_pieces": len(outcomes["qasper"]), "qasper_split_pct": round(100 * sum(outcomes["qasper"]) / max(len(outcomes["qasper"]), 1), 1)})

    table = pd.DataFrame(rows).sort_values(["parser", "median_tokens", "setting"])
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUTPUT, index=False)
    pd.set_option("display.width", 200)
    print("\n" + table.to_string(index=False) + f"\n\nsaved: {OUTPUT}")


if __name__ == "__main__":
    main()