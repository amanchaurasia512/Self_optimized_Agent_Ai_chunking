"""Docling parser: layout-aware extraction into the same frozen format as pdfplumber (text + page offsets),
plus every recognised element (label, depth, page, character range) for the structure profile."""
from importlib.metadata import version
from itertools import accumulate

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (EasyOcrOptions, PdfPipelineOptions, RapidOcrOptions, TableFormerMode,
                                                TesseractCliOcrOptions)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import ListItem, TableItemom importlib.metadata import version
from itertools import accumulate

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import EasyOcrOptions, PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import TableItem
from docling_core.types.doc import ListItem, TableItem

PAGE_SEPARATOR = "\n\n"
ELEMENT_SEPARATOR = "\n\n"

VARIANTS = {"default": {}, "ocr_off": {"do_ocr": False}, "table_mode_switched": {"switch_table_mode": True},
            "headings": {"heading_hierarchy": True}, "replace_broken_text": {"replace_broken_text_layer": True},
            "ocr_tesseract": {"ocr_engine": TesseractCliOcrOptions}, "ocr_rapidocr": {"ocr_engine": RapidOcrOptions},
            "ocr_scale_double": {"ocr_scale_factor": 2}}


def option(owner, name):
    """An existing option of a Docling options object; stops if this Docling version does not have it."""
    if not hasattr(owner, name):
        raise AttributeError(f"{type(owner).__name__} has no option '{name}' in Docling {version('docling')}")
    return getattr(owner, name)


def make_converter(force_full_page_ocr=False, ocr_lang=None, variant="default"):
    """The frozen default converter, or one named variant of it (RQ5a); every variant changes only its own settings."""
    change = VARIANTS[variant]
    options = PdfPipelineOptions()
    options.do_ocr = change.get("do_ocr", True)
    options.do_table_structure = True
    if ocr_lang:
        options.ocr_options = EasyOcrOptions(lang=ocr_lang)
    if "ocr_engine" in change:
        options.ocr_options = change["ocr_engine"]()
    options.ocr_options.force_full_page_ocr = force_full_page_ocr
    table = option(options, "table_structure_options")
    if change.get("switch_table_mode"):
        table.mode = TableFormerMode.FAST if table.mode == TableFormerMode.ACCURATE else TableFormerMode.ACCURATE
    if change.get("heading_hierarchy"):
        option(options, "heading_hierarchy_options").enabled = True
    if change.get("replace_broken_text_layer"):
        option(options.ocr_options, "replace_broken_text_layer")
        options.ocr_options.replace_broken_text_layer = True
    if "ocr_scale_factor" in change:
        options.ocr_options.scale = option(options.ocr_options, "scale") * change["ocr_scale_factor"]
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
    parser_info = {"name": "docling", "version": version("docling"),
                   "settings": {"do_ocr": options.do_ocr, "do_table_structure": True, "force_full_page_ocr": force_full_page_ocr,
                                "ocr_engine": type(options.ocr_options).__name__, "ocr_lang": ocr_lang or []}}
    if variant != "default":
        parser_info["settings"].update(variant=variant, table_mode=str(table.mode),
                                       ocr_scale=getattr(options.ocr_options, "scale", None))
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