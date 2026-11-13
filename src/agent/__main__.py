"""Agent command line (spec/agent_v1.md): chunk, ask, chat, batch, and providers add / list."""
import argparse
import json
from pathlib import Path

INDEX_STAGES = ("scan_check", "load_index", "parse", "chunk", "embed", "load_vectors")  # everything before retrieval


def timing_line(record_path, parts):
    """'time: total X s | name Y s ...' from the run record's stage timings; parts maps a label to its stage names
    (a label whose steps are not in the record is left out)."""
    costs = json.loads(Path(record_path).read_text(encoding="utf-8"))["costs"]
    seconds = {label: sum(stage["wall_seconds"] for stage in costs["stages"] if stage["stage"] in names)
               for label, names in parts.items() if any(stage["stage"] in names for stage in costs["stages"])}
    return " | ".join([f"time: total {costs['totals']['wall_seconds']:.1f} s",
                       *(f"{label} {value:.1f} s" for label, value in seconds.items())])


def chunk_command(args):
    from src.agent.pipeline import chunk_pdf
    chunk_doc, record_path = chunk_pdf(args.pdf, args.output, args.fast, args.from_extraction, args.machine)
    print(f"{len(chunk_doc['chunks'])} chunks -> {args.output}\n"
          f"{timing_line(record_path, {'parse': ('parse',), 'chunk': ('chunk',)})}\nrun record: {record_path}")


def ask_command(args):
    from src.agent.ask import ask_pdf
    from src.agent.providers import ProviderError
    try:
        result = ask_pdf(args.pdf, args.question, args.budget, args.fast, args.from_extraction, args.context_only,
                         args.record_text, args.machine)
    except ProviderError as error:
        raise SystemExit(str(error)) from None
    if args.context_only:
        print(result["context"])
    else:
        provider = result["provider"]
        print(f"{result['answer']}\n\nanswered by: {provider['entry']} ({provider['provider']}, {provider['model']})")
    index_label = f"index ({'cached' if result['cache_hit'] else 'built'})"
    parts = {index_label: INDEX_STAGES, "retrieve": ("retrieve",), **({} if args.context_only else {"answer": ("answer",)})}
    print(timing_line(result["run_record"], parts))
    print(f"{sources_line(result['sources'])}\ntokens read: {result['tokens_read']} of {args.budget} | "
          f"index: {'cached' if result['cache_hit'] else 'built'}\nrun record: {result['run_record']}")


def sources_line(sources):
    return "sources: " + ", ".join(f"{source['chunk_id']} (p. {', '.join(map(str, source['pages']))})" for source in sources)


def typed_questions():
    while True:
        try:
            yield input("\nquestion (empty line to stop): ")
        except EOFError:
            return


def chat_command(args):
    from src.agent.ask import chat
    from src.agent.providers import ProviderError
    results = chat(args.pdf, typed_questions(), args.budget, args.fast, args.record_text, args.machine)
    try:
        opened = next(results)
        print(f"index {'cached' if opened['cache_hit'] else 'built'}: {opened['chunks']} chunks ({opened['parser']})")
        for result in results:
            provider = result["provider"]
            parts = {"model load": ("load_embedder",), "index": INDEX_STAGES, "retrieve": ("retrieve",), "answer": ("answer",)}
            print(f"\n{result['answer']}\n\nanswered by: {provider['entry']} ({provider['provider']}, {provider['model']})\n"
                  f"{timing_line(result['run_record'], parts)}\n{sources_line(result['sources'])}\n"
                  f"run record: {result['run_record']}")
    except ProviderError as error:
        raise SystemExit(str(error)) from None


def batch_command(args):
    from src.agent.batch import run_batch
    from src.agent.providers import ProviderError
    options = {"cache_root": args.cache_root} if args.cache_root else {}
    try:
        table, record_path = run_batch(args.questions, args.output, args.budget, args.fast, machine=args.machine, **options)
    except ProviderError as error:
        raise SystemExit(f"{error}\nanswers so far are in {args.output}; see the newest run record") from None
    print(f"{len(table)} questions answered -> {args.output}\nmean token F1 {table['f1'].mean():.3f} | "
          f"contained {table['contained'].mean():.3f}\n"
          f"answers by entry: {table['provider_entry'].value_counts().to_dict()}\nrun record: {record_path}")


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
    chat_parser = modes.add_parser("chat", help="questions one per line about one PDF until an empty line")
    chat_parser.add_argument("pdf")
    batch_parser = modes.add_parser("batch", help="answer a CSV of pdf, question, gold")
    batch_parser.add_argument("questions", help="CSV with the columns pdf, question, gold")
    batch_parser.add_argument("-o", "--output", required=True, help="answers CSV to write")
    batch_parser.add_argument("--cache-root", help="index cache folder (default data/agent_cache)")
    for command in (chat_parser, batch_parser):
        command.add_argument("--budget", type=int, default=1250, choices=(750, 1250, 2000))
        command.add_argument("--fast", action="store_true", help="pdfplumber for digital PDFs (Docling if any page has no text)")
        command.add_argument("--machine", default="laptop")
    chat_parser.add_argument("--record-text", action="store_true", help="store question and answer text in the run records")
    provider_parser = modes.add_parser("providers", help="manage the answer-provider list")
    actions = provider_parser.add_subparsers(dest="action", required=True)
    add = actions.add_parser("add", help="add an entry; the key is asked for with hidden input")
    add.add_argument("--name", required=True)
    add.add_argument("--provider", required=True, choices=("gemini", "groq"))
    add.add_argument("--model", required=True)
    actions.add_parser("list", help="entries in order with their status (never the keys)")
    args = arg_parser.parse_args()
    {"chunk": chunk_command, "ask": ask_command, "chat": chat_command, "batch": batch_command,
     "providers": providers_command}[args.mode](args)


if __name__ == "__main__":
    main()
