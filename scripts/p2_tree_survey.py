"""P2: test the structure tree on every extracted document (except held-out ones): one line of counts per document,
then a look at the tree at the start, the middle and the end of each document. Read-only."""
import argparse
import json
from collections import Counter
from pathlib import Path

from src.chunk.base import token_counts
from src.chunk.tree import build_tree, fit_report
from src.common.split import tuning_ids

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def source_of(path, root):
    relative = path.relative_to(root)
    return relative.parts[0] if len(relative.parts) > 1 else path.stem.split("_")[0]


def survey(path, budget):
    document = json.loads(path.read_text(encoding="utf-8"))
    nodes, stats = build_tree(document)
    body = nodes[1:]
    return {"name": path.stem, "nodes": body, "stats": stats, "fit": fit_report(nodes, document, budget),
            "tokens": token_counts([document["text"]])[0],
            "headers": sum(element["label"] == "section_header" for element in document.get("elements", [])),
            "levels": max((node["level"] for node in body), default=0),
            "styles": Counter(str(node["style"]) for node in body).most_common(3)}


def windows(nodes, size):
    """The first, middle and last nodes of a tree (all of them when it is small, none when size is 0)."""
    if size == 0:
        return {}
    if len(nodes) <= 3 * size:
        return {"all": nodes}
    middle = len(nodes) // 2 - size // 2
    return {"start": nodes[:size], "middle": nodes[middle:middle + size], "end": nodes[-size:]}


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--parser", default="docling")
    arg_parser.add_argument("--budget", type=int, default=1024)
    arg_parser.add_argument("--show", type=int, default=4)
    args = arg_parser.parse_args()

    root = PROJECT_ROOT / "data" / "extracted" / args.parser
    tuning = tuning_ids()
    paths = sorted(path for path in root.rglob("*.json") if path.stem in tuning)
    results = [survey(path, args.budget) for path in paths]
    print(dict(Counter(source_of(path, root) for path in paths)), f"| tuning documents only | budget {args.budget}\n")

    print(f"{'document':<42} {'tokens':>7} {'headers':>7} {'proven':>6} {'nodes':>5} {'levels':>6} {'break%':>6} "
          f"{'pieces':>6} {'largest':>7} {'conf_lbl':>8} {'conf':>5}")
    for result in results:
        stats, fit = result["stats"], result["fit"]
        breaks = stats["sequence_breaks"] / len(result["nodes"]) if result["nodes"] else 0
        print(f"{result['name'][:42]:<42} {result['tokens']:>7} {result['headers']:>7} {stats['styles_proven']:>6} "
              f"{len(result['nodes']):>5} {result['levels']:>6} {breaks:>6.0%} {fit['pieces']:>6} {fit['largest']:>7} "
              f"{fit['conf_lbl']:>8.2f} {fit['confidence']:>5.2f}")

    for result in results:
        print(f"\n=== {result['name']} | {result['stats']} | styles {result['styles']}")
        for part, nodes in windows(result["nodes"], args.show).items():
            print(f"  [{part}]")
            for node in nodes:
                print(f"    {'  ' * min(node['level'] - 1, 8)}{(node['label'] or '[heading]')[:12]:<12} | {node['title'][:60]}")

if __name__ == "__main__":
    main()