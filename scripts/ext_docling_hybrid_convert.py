"""Extension item 4, Kaggle side (spec v1.2, docling_hybrid clarification 83bbf6c; runs in the Docling environment only).
Tuning documents only, no --final: re-convert each PDF with the frozen default converter (pinned Docling 2.143.0), save
the DoclingDocument, compare its text with the frozen extraction, run HybridChunker (bge-m3, max 512 tokens, defaults)
and save each chunk's text and the labels of its doc items. The study side (src/chunk/hybrid.py) maps them to spans."""
import argparse
import json
from difflib import SequenceMatcher
from importlib.metadata import version

import pandas as pd
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer

from src.chunk.base import TOKENIZER
from src.common.cost_logger import CostLogger
from src.common.manifest import PROJECT_ROOT, RUNS_DIR, build_manifest, new_run_id
from src.common.pdf_catalog import PDF_MANIFEST
from src.common.split import tuning_ids
from src.parse.docling_parser import assemble, make_converter, page_entries

EXTRACTED, RESULTS = PROJECT_ROOT / "data" / "extracted", PROJECT_ROOT / "data" / "results" / "ext_docling_hybrid"
MAX_TOKENS = 512
TEST_DOC = "cuad_bizzingoinc_20120322_8_k_ex_10_17_7504499_ex_10_17_endorsement_agreement"


def differing_chars(old, new):
    """Characters outside matching blocks, (old side, new side): lines matched first, then characters inside changed lines."""
    if old == new:
        return 0, 0
    old_lines, new_lines = old.splitlines(keepends=True), new.splitlines(keepends=True)
    old_count = new_count = 0
    for tag, a1, a2, b1, b2 in SequenceMatcher(None, old_lines, new_lines, autojunk=False).get_opcodes():
        if tag != "equal":
            inner = SequenceMatcher(None, "".join(old_lines[a1:a2]), "".join(new_lines[b1:b2]), autojunk=False)
            changed = [op for op in inner.get_opcodes() if op[0] != "equal"]
            old_count += sum(op[2] - op[1] for op in changed)
            new_count += sum(op[4] - op[3] for op in changed)
    return old_count, new_count


def test_run_id(source):
    """new_run_id does not look in runs/tests/: take the next number not used by a test record there either."""
    prefix, number = new_run_id(2, source).rsplit("-", 1)
    used = [int(path.stem.rsplit("-", 1)[1]) for path in (RUNS_DIR / "tests").glob(f"*{prefix}-*.json")]
    return f"{prefix}-{max([int(number) - 1, *used]) + 1}"


def compare(frozen, parser_info, text, pages, elements):
    old_chars, new_chars = differing_chars(frozen["text"], text)
    return {"text_identical": text == frozen["text"], "frozen_chars_differing": old_chars, "new_chars_differing": new_chars,
            "frozen_chars": len(frozen["text"]), "new_chars": len(text), "pages_equal": pages == frozen["pages"],
            "elements_equal": elements == frozen["elements"], "parser_info_equal": parser_info == frozen["parser"]}


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--test", action="store_true",
                            help=f"one document ({TEST_DOC}); outputs under data/extracted/tests/, run record in runs/tests/")
    arg_parser.add_argument("--machine", default="kaggle")
    arg_parser.add_argument("--run-source", required=True, help="notebook id used in the run id, e.g. KN10; TEST for --test")
    args = arg_parser.parse_args()

    docs = [TEST_DOC] if args.test else sorted(tuning_ids())
    if not set(docs) <= tuning_ids():
        raise PermissionError(f"tuning documents only: {sorted(set(docs) - tuning_ids())}")
    catalog = pd.read_csv(PDF_MANIFEST).set_index("doc_id")
    converter, parser_info = make_converter()
    tokenizer = HuggingFaceTokenizer.from_pretrained(TOKENIZER["name"], max_tokens=MAX_TOKENS, revision=TOKENIZER["revision"])
    chunker = HybridChunker(tokenizer=tokenizer)
    chunker_info = {"name": "HybridChunker", "docling": version("docling"), "docling_core": version("docling-core"),
                    "tokenizer": TOKENIZER, "max_tokens": MAX_TOKENS, "merge_peers": chunker.merge_peers}
    run_id = test_run_id(args.run_source) if args.test else new_run_id(2, args.run_source)
    manifest_path = (RUNS_DIR / "tests" / f"test_docling_hybrid_convert_cuad_{run_id}.json" if args.test
                     else RUNS_DIR / f"{run_id}.json")
    if manifest_path.exists():
        raise FileExistsError(f"run record already exists: {manifest_path}")
    root, results = (EXTRACTED / "tests", RESULTS / "tests") if args.test else (EXTRACTED, RESULTS)
    folders = {name: root / name for name in ("docling_doc", "docling_hybrid")}
    for folder in [*folders.values(), results]:
        folder.mkdir(parents=True, exist_ok=True)
    logger, inputs, outputs, rows = CostLogger(), [], [], []
    for doc_id in docs:
        pdf_path, frozen_path = PROJECT_ROOT / catalog.loc[doc_id, "file"], EXTRACTED / "docling" / f"{doc_id}.json"
        frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
        with logger.stage(f"convert_chunk:{doc_id}") as stage:
            document = converter.convert(str(pdf_path)).document
            comparison = compare(frozen, parser_info, *assemble(page_entries(document)))
            chunks = [{"text": chunk.text, "labels": [item.label.value for item in chunk.meta.doc_items]}
                      for chunk in chunker.chunk(dl_doc=document)]
            stage.update(comparison, chunks=len(chunks))
        doc_path, hybrid_path = (folder / f"{doc_id}.json" for folder in folders.values())
        doc_path.write_text(json.dumps(document.export_to_dict(), ensure_ascii=False), encoding="utf-8")
        hybrid_path.write_text(json.dumps({"doc_id": doc_id, "run_id": run_id, "parser": parser_info, "chunker": chunker_info,
                                           "comparison": comparison, "chunks": chunks}, ensure_ascii=False, indent=2),
                               encoding="utf-8")
        inputs += [pdf_path, frozen_path]
        outputs += [doc_path, hybrid_path]
        rows.append({"doc_id": doc_id, **comparison, "chunks": len(chunks), "seconds": stage["wall_seconds"]})

    table_path = results / f"text_comparison_{run_id}.csv"
    pd.DataFrame(rows).to_csv(table_path, index=False)
    manifest = build_manifest(run_id, "v1.2", {"parser": parser_info, "chunker": chunker_info}, inputs,
                              [*outputs, table_path], logger.summary(), "laptop" if args.test else args.machine)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    pd.set_option("display.width", 250)
    print(pd.DataFrame(rows).to_string(index=False), f"\ncomparison: {table_path}\nmanifest: {manifest_path}")


if __name__ == "__main__":
    main()
