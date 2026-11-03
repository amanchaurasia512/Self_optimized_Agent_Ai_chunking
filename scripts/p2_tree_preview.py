"""P2 own method 1: print a document's tree with subtree token sizes, to check the levels by eye (tuning PDFs only)."""
import argparse
import json
from collections import Counter
from src.common.split import tuning_ids
from src.chunk.tree import build_tree, subtree_tokens
from src.common.manifest import PROJECT_ROOT


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--doc", default="indian_d4_rti_act")
    arg_parser.add_argument("--parser", default="docling")
    arg_parser.add_argument("--limit", type=int, default=80)
    args = arg_parser.parse_args()
    if args.doc not in tuning_ids():
        raise PermissionError(f"{args.doc} is not a tuning document in pdfs/split.csv: it is sealed")

    document = json.loads((PROJECT_ROOT / "data" / "extracted" / args.parser / f"{args.doc}.json").read_text(encoding="utf-8"))
    nodes, stats = build_tree(document)
    tokens = subtree_tokens(nodes, document["text"])
    print(f"{args.doc} ({args.parser}): {len(nodes) - 1} nodes | {stats}")
    print("nodes per level:", dict(sorted(Counter(node["level"] for node in nodes[1:]).items())))
    first_style = {}
    for node in nodes[1:]:
        first_style.setdefault(node["level"], node["style"])
    print("first style seen per level:", first_style, "\n")
    for node, size in list(zip(nodes, tokens))[1:args.limit + 1]:
        print(f"{'    ' * (node['level'] - 1)}{node['label']:<12} {size:>6} tok | {node['title'][:60]}")

    breaks = [node for node in nodes[1:] if node["how"] in ("fallback", "new")]
    print(f"\nsequence breaks ({len(breaks)}), first 30:")
    for node in breaks[:30]:
        print(f"  level {node['level']} {node['label']:<10} {node['how']:<8} | {node['title'][:60]}")
        
if __name__ == "__main__":
    main()