"""Agent command line (spec/agent_v1.md): chunk, ask, and providers add / list."""
import argparse


def chunk_command(args):
    from src.agent.pipeline import chunk_pdf
    chunk_doc, record_path = chunk_pdf(args.pdf, args.output, args.fast, args.from_extraction, args.machine)
    print(f"{len(chunk_doc['chunks'])} chunks -> {args.output}\nrun record: {record_path}")


def ask_command(args):
    from src.agent.ask import ask_pdf
    from src.agent.providers import ProviderError
    try:
        result = ask_pdf(args.pdf, args.question, args.budget, args.fast, args.from_extraction, args.context_only,
                         args.record_text, args.machine)
    except ProviderError as error:
        raise SystemExit(str(error)) from None
    sources = ", ".join(f"{source['chunk_id']} (p. {', '.join(map(str, source['pages']))})" for source in result["sources"])
    if args.context_only:
        print(result["context"])
    else:
        provider = result["provider"]
        print(f"{result['answer']}\n\nanswered by: {provider['entry']} ({provider['provider']}, {provider['model']})")
    print(f"sources: {sources}\ntokens read: {result['tokens_read']} of {args.budget} | "
          f"index: {'cached' if result['cache_hit'] else 'built'}\nrun record: {result['run_record']}")


def providers_command(args):
    from src.agent.providers import ProviderError, add_entry, list_entries
    try:
        if args.action == "add":
            entry = add_entry(args.name, args.provider, args.model)
            print(f"added '{entry['name']}' ({entry['provider']}, {entry['model']}); key saved to {entry['key_file']}")
        else:
            for row in list_entries():
                found = "key file found" if row["key_file_found"] else "KEY FILE MISSING"
                print(f"{row['position']}. {row['name']:16} {row['provider']:7} {row['model']:28} {found:16} {row['status']}")
    except ProviderError as error:
        raise SystemExit(str(error)) from None


def main():
    arg_parser = argparse.ArgumentParser(prog="python -m src.agent", description=__doc__)
    modes = arg_parser.add_subparsers(dest="mode", required=True)
    for mode in ("chunk", "ask"):
        command = modes.add_parser(mode)
        command.add_argument("pdf")
        if mode == "chunk":
            command.add_argument("-o", "--output", required=True, help="chunk.json to write")
        else:
            command.add_argument("question")
            command.add_argument("--budget", type=int, default=1250, choices=(750, 1250, 2000))
            command.add_argument("--context-only", action="store_true", help="print the retrieved context; no API call")
            command.add_argument("--record-text", action="store_true", help="store question and answer text in the run record")
        command.add_argument("--fast", action="store_true", help="pdfplumber for digital PDFs (Docling if any page has no text)")
        command.add_argument("--from-extraction", help="start from an existing extraction file instead of parsing")
        command.add_argument("--machine", default="laptop")
    provider_parser = modes.add_parser("providers", help="manage the answer-provider list")
    actions = provider_parser.add_subparsers(dest="action", required=True)
    add = actions.add_parser("add", help="add an entry; the key is asked for with hidden input")
    add.add_argument("--name", required=True)
    add.add_argument("--provider", required=True, choices=("gemini", "groq"))
    add.add_argument("--model", required=True)
    actions.add_parser("list", help="entries in order with their status (never the keys)")
    args = arg_parser.parse_args()
    {"chunk": chunk_command, "ask": ask_command, "providers": providers_command}[args.mode](args)


if __name__ == "__main__":
    main()
