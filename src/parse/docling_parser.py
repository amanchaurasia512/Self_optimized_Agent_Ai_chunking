"""Docling parser: layout-aware extraction into the same frozen format as pdfplumber (text + page offsets),
plus every recognised element (label, depth, page, character range) for the structure profile."""
from importlib.metadata import version
from itertools import accumulate

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import EasyOcrOptions, PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import TableItem
from docling_core.types.doc import ListItem, TableItem

PAGE_SEPARATOR = "\n\n"
ELEMENT_SEPARATOR = "\n\n"

def make_converter(force_full_page_ocr=False, ocr_lang=None):
    options = PdfPipelineOptions()
    options.do_ocr = True
    options.do_table_structure = True
    if ocr_lang:
        options.ocr_options = EasyOcrOptions(lang=ocr_lang)
    options.ocr_options.force_full_page_ocr = force_full_page_ocr
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
    parser_info = {"name": "docling", "version": version("docling"),
                   "settings": {"do_ocr": True, "do_table_structure": True, "force_full_page_ocr": force_full_page_ocr,
                                "ocr_engine": type(options.ocr_options).__name__, "ocr_lang": ocr_lang or []}}
    return converter, parser_info


def item_text(item, document):
    """Table → Markdown; numbered list item → its number put back in front ('(4) Notwithstanding…'); bullets are left out."""
    if isinstance(item, TableItem):
        return item.export_to_markdown(doc=document)
    text = getattr(item, "text", "") or ""
    marker = item.marker if isinstance(item, ListItem) and item.enumerated else ""
    return f"{marker} {text}" if marker and not text.startswith(marker) else text

def page_entries(document):
    entries = {page_number: [] for page_number in sorted(document.pages)}
    for item, depth in document.iterate_items():
        text = item_text(item, document)
        if text.strip() and item.prov:
            entries[item.prov[0].page_no].append({"label": item.label.value, "depth": depth, "text": text})
    return entries


def assemble(entries_by_page):
    page_texts, pages, elements, offset = [], [], [], 0
    for page_number, entries in entries_by_page.items():
        starts = [0, *accumulate(len(entry["text"]) + len(ELEMENT_SEPARATOR) for entry in entries[:-1])]
        page_text = ELEMENT_SEPARATOR.join(entry["text"] for entry in entries)
        pages.append({"page": page_number, "start_char": offset, "end_char": offset + len(page_text)})
        elements += [{"label": entry["label"], "depth": entry["depth"], "page": page_number,
                      "start_char": offset + start, "end_char": offset + start + len(entry["text"])}
                     for entry, start in zip(entries, starts)]
        page_texts.append(page_text)
        offset += len(page_text) + len(PAGE_SEPARATOR)
    return PAGE_SEPARATOR.join(page_texts), pages, elements


def parse_pdf(pdf_path, converter):
    document = converter.convert(str(pdf_path)).document
    return assemble(page_entries(document))