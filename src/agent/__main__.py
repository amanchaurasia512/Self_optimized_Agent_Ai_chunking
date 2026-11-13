"""Agent command line (spec/agent_v1.md). Part A: chunk mode only."""
import argparse

from src.agent.pipeline import chunk_pdf


def main():
    arg_parser = argparse.ArgumentParser(prog="python -m src.agent", description=__doc__)
    modes = arg_parser.add_subparsers(dest="mode", required=True)
    chunk = modes.add_parser("chunk", help="PDF -> chunk.json (spec/chunk.schema.json)")
    chunk.add_argument("pdf")
    chunk.add_argument("-o", "--output", required=True, help="chunk.json to write")
    chunk.add_argument("--fast", action="store_true", help="pdfplumber for digital PDFs (Docling if any page has no text)")
    chunk.add_argument("--from-extraction", help="start from an existing extraction file instead of parsing")
    chunk.add_argument("--machine", default="laptop")
    modes.add_parser("ask", help="not implemented yet (Part B)")
    args = arg_parser.parse_args()

    if args.mode == "ask":
        raise SystemExit("ask mode is not implemented yet (agent spec Part B)")
    chunk_doc, record_path = chunk_pdf(args.pdf, args.output, args.fast, args.from_extraction, args.machine)
    print(f"{len(chunk_doc['chunks'])} chunks -> {args.output}\nrun record: {record_path}")


if __name__ == "__main__":
    main()
