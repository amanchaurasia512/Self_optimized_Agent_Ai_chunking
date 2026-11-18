import json, difflib, pickle
from src.parse.docling_parser import make_converter, page_entries, assemble
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
doc = "cuad_bizzingoinc_20120322_8_k_ex_10_17_7504499_ex_10_17_endorsement_agreement"
S = "/tmp/claude-1000/-home-chaurasia008-Project-files-Self-optimized-Agent-Ai-chunking/7a5f59ae-12a8-4605-aa39-8c9778c6821a/scratchpad"
frozen = json.load(open(f"data/extracted/docling/{doc}.json"))
document = make_converter()[0].convert(f"data/raw/cuad/{doc}.pdf").document
open(f"{S}/cuad_doclingdoc.json", "w").write(json.dumps(document.export_to_dict()))
text, pages, elements = assemble(page_entries(document))
print("len frozen", len(frozen["text"]), "new", len(text), "| elements", len(frozen["elements"]), len(elements))
matcher = difflib.SequenceMatcher(None, frozen["text"], text, autojunk=False)
ops = [op for op in matcher.get_opcodes() if op[0] != "equal"]
print("differing regions:", len(ops), "| chars differing (frozen side):", sum(op[2] - op[1] for op in ops))
for tag, a1, a2, b1, b2 in ops[:6]:
    print(f"  {tag}: frozen {frozen['text'][a1:a2]!r} -> new {text[b1:b2]!r}   (context: {frozen['text'][max(0,a1-40):a1]!r})")
# per-item mapping check: HybridChunker doc_items -> frozen elements by iterate order
tokenizer = HuggingFaceTokenizer.from_pretrained("BAAI/bge-m3", max_tokens=512, revision="5617a9f61b028005a4858fdac845db406aefb181")
chunks = list(HybridChunker(tokenizer=tokenizer).chunk(dl_doc=document))
kept = [item.self_ref for item, depth in document.iterate_items() if (getattr(item, "text", "") or item.label.value == "table") and item.prov]
print("items kept by parse rule (approx):", len(kept), "| distinct doc_items in chunks:", len({i.self_ref for c in chunks for i in c.meta.doc_items}))
print("chunk.text joins items with '\\n':", sum("\n" in c.text for c in chunks), "of", len(chunks), "| frozen joins elements with", repr(frozen["text"][31:33]))
