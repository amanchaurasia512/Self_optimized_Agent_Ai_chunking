"""Probe (scratchpad, not project code): re-convert one tuning PDF, compare with the frozen extraction, run HybridChunker."""
import json, sys, time
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from src.parse.docling_parser import make_converter, page_entries, assemble

doc = sys.argv[1]
frozen = json.load(open(f"data/extracted/docling/{doc}.json"))
converter, info = make_converter()
start = time.perf_counter()
document = converter.convert(f"data/raw/cuad/{doc}.pdf").document
text, pages, elements = assemble(page_entries(document))
print(f"convert {time.perf_counter() - start:.0f} s | parser info equal: {info == frozen['parser']} | text byte-identical: {text == frozen['text']} "
      f"| pages equal: {pages == frozen['pages']} | elements equal: {elements == frozen['elements']}")
tokenizer = HuggingFaceTokenizer.from_pretrained("BAAI/bge-m3", max_tokens=512, revision="5617a9f61b028005a4858fdac845db406aefb181")
chunks = list(HybridChunker(tokenizer=tokenizer).chunk(dl_doc=document))
found, previous, missing = 0, 0, []
for chunk in chunks:
    position = frozen["text"].find(chunk.text, previous)
    if position >= 0:
        found, previous = found + 1, position
    else:
        missing.append(chunk)
labels = lambda chunk: sorted({item.label.value for item in chunk.meta.doc_items})
print(f"HybridChunker chunks {len(chunks)} | chunk.text found exactly in order: {found} | not found: {len(missing)}")
print("token counts (bge-m3, chunk.text):", sorted(tokenizer.count_tokens(chunk.text) for chunk in chunks)[-3:], "max of", len(chunks))
for chunk in missing[:3]:
    print(f"  missing, labels {labels(chunk)}: {chunk.text[:160]!r}")
print("example contextualize vs text differ:", sum(HybridChunker(tokenizer=tokenizer).contextualize(chunk) != chunk.text for chunk in chunks), "of", len(chunks))
