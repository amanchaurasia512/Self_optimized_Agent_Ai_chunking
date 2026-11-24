"""What the app chunks with and why (spec/agent_v1.md, App v1.1). The chunker line is read from the index run record;
the reasons quote RESULTS.md, and tests/agent/test_explain.py checks every number in them against that file."""
CHUNKER_KINDS = {"method1_tree": "structure-tree", "langchain_recursive": "LangChain recursive"}  # display label; the chunker registry has no description field
PARSER_NAMES = {"docling": "Docling", "pdfplumber": "pdfplumber"}
README_QUESTIONS = "https://github.com/amanchaurasia512/Self_optimized_Agent_Ai_chunking#research-questions"

WHY = [
    "The chunker is LangChain's recursive splitter at 256 tokens, no overlap, no prefix: the best setup on the tuning "
    "documents, chosen before the sealed held-out sets were opened. On held-out it stayed statistically tied with the "
    "best (held-out 1: 0.715, rank 20 of 26, best 0.772; 15 of 26 setups tied), so it is a safe choice, not a unique "
    "winner.",
    "Small chunks (the tuned sizes, 256 or 384 tokens) beat large ones at a fixed reading budget: more of the budget "
    "goes to text near the question. Large chunks (fixed 1,024) gave answers 0.123 token-F1 below the best setup "
    "(method1_tree T256) on held-out.",
    "LangChain's default chunk size was 0.10–0.12 Recall below the tuned size.",
    "Choosing a different setup per PDF gave no gain (gap −0.007 [−0.045, 0.023]), so the agent uses one fixed setup "
    "for every PDF.",
    "Budget 1,250 is the study's main evaluation budget. A larger budget reads more, but is slower and uses more of "
    "the LLM quota.",
]


def chunker_line(record):
    """'Chunker: <name> (<kind>), <T> tokens, <prefix> · parser: <parser>' from an index run record's stack."""
    chunker, parser = record["stack"]["chunker"], record["stack"]["parser"]["name"]
    settings = chunker["settings"]
    prefix = "heading prefix" if settings["heading_prefix"] else "no prefix"
    kind = f" ({CHUNKER_KINDS[chunker['name']]})" if chunker["name"] in CHUNKER_KINDS else ""
    return (f"Chunker: {chunker['name']}{kind}, {settings.get('T', settings.get('size'))} tokens, {prefix} · "
            f"parser: {PARSER_NAMES.get(parser, parser)}")
