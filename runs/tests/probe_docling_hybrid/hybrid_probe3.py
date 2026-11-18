import json, re
from docling_core.types.doc import DoclingDocument
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from src.parse.docling_parser import page_entries
doc = "cuad_bizzingoinc_20120322_8_k_ex_10_17_7504499_ex_10_17_endorsement_agreement"
S = "/tmp/claude-1000/-home-chaurasia008-Project-files-Self-optimized-Agent-Ai-chunking/7a5f59ae-12a8-4605-aa39-8c9778c6821a/scratchpad"
frozen = json.load(open(f"data/extracted/docling/{doc}.json"))["text"]
document = DoclingDocument.model_validate(json.load(open(f"{S}/cuad_doclingdoc.json")))
tokenizer = HuggingFaceTokenizer.from_pretrained("BAAI/bge-m3", max_tokens=512, revision="5617a9f61b028005a4858fdac845db406aefb181")
chunks = list(HybridChunker(tokenizer=tokenizer).chunk(dl_doc=document))
keep = [i for i, ch in enumerate(frozen) if not ch.isspace()]
squeezed = "".join(frozen[i] for i in keep)
def locate(piece, after):
    """Whitespace-insensitive, in order: (start, end) in the frozen text, or None."""
    target = re.sub(r"\s+", "", piece)
    position = squeezed.find(target, after)
    return (keep[position], keep[position + len(target) - 1] + 1, position + len(target)) if position >= 0 and target else None
for name, clean in (("whitespace-insensitive", lambda t: t),
                    ("+ list bullets '- ' removed", lambda t: re.sub(r"(?m)^- ", "", t))):
    after, found, spans = 0, 0, []
    for chunk in chunks:
        hit = locate(clean(chunk.text), after)
        if hit:
            found, after = found + 1, hit[2]; spans.append(hit[:2])
    covered = sum(b - a for a, b in spans)
    print(f"{name}: {found}/{len(chunks)} chunks located in order | frozen chars covered {covered}/{len(frozen)}")
labels = sorted({item.label.value for chunk in chunks for item in chunk.meta.doc_items})
in_chunks = {item.self_ref for chunk in chunks for item in chunk.meta.doc_items}
outside = [item for item, depth in document.iterate_items() if item.self_ref not in in_chunks and getattr(item, "text", "").strip()]
print("doc item labels in chunks:", labels, "| items with text not in any chunk:", len(outside), sorted({i.label.value for i in outside}), [i.text[:40] for i in outside[:3]])
