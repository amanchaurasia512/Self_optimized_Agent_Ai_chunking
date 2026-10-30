"""P1-R08: check the Docling re-run (P1-KN06) against the old extraction. The only allowed change is
a list number put back in front of a list item ('(4) Notwithstanding…'); anything else is reported."""
import json

import pandas as pd

from src.common.manifest import PROJECT_ROOT

EXTRACTED = PROJECT_ROOT / "data" / "extracted"
import argparse


def blocks(document):
    return [(element["label"], document["text"][element["start_char"]:element["end_char"]]) for element in document["elements"]]


def compare(old_document, new_document):
    old_blocks, new_blocks = blocks(old_document), blocks(new_document)
    if [block[0] for block in old_blocks] != [block[0] for block in new_blocks]:
        return {"same_blocks": False, "restored": None, "other_changes": None, "markers": "", "first_other": ""}
    restored, others = [], []
    for old, new in zip(old_blocks, new_blocks):
        if new[1] == old[1]:
            continue
        if old[0] == "list_item" and new[1].endswith(" " + old[1]):
            restored.append(new[1][:len(new[1]) - len(old[1]) - 1])
        else:
            others.append(f"{old[1][:50]!r} -> {new[1][:50]!r}")
    return {"same_blocks": True, "restored": len(restored), "other_changes": len(others),
            "markers": " ".join(dict.fromkeys(restored))[:40], "first_other": others[0] if others else ""}


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--old", default="docling_pre_r08", help="folder under data/extracted")
    arg_parser.add_argument("--new", default="docling", help="folder under data/extracted")
    arg_parser.add_argument("--only", nargs="+", help="doc ids to compare (default: all in --new)")
    args = arg_parser.parse_args()

    rows = []
    for new_path in sorted((EXTRACTED / args.new).glob("*.json")):
        if args.only and new_path.stem not in args.only:
            continue
        new_document = json.loads(new_path.read_text(encoding="utf-8"))
        old_document = json.loads((EXTRACTED / args.old / new_path.name).read_text(encoding="utf-8"))
        rows.append({"doc_id": new_path.stem, "same_settings": old_document["parser"] == new_document["parser"],
                     **compare(old_document, new_document)})
    table = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    print(f"{args.old} -> {args.new}")
    print(table.drop(columns="first_other").to_string(index=False), "\n")
    print(f"documents: {len(table)} | same settings: {table['same_settings'].sum()} | same blocks: {table['same_blocks'].sum()} | "
          f"numbers restored: {int(table['restored'].sum())} | other changes: {int(table['other_changes'].sum())}")
    for row in table[table["first_other"] != ""].itertuples():
        print(f"other change in {row.doc_id}: {row.first_other}")

if __name__ == "__main__":
    main()