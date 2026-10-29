"""Place gold evidence in a parser's frozen text: exact -> normalised -> fuzzy (always flagged), choosing by page
when the evidence occurs more than once. Normalisation ignores case, whitespace, quote/dash style and table/LaTeX
notation, so glued words and Markdown/LaTeX tables still match; positions always map back to the original text."""
import re
import unicodedata
from bisect import bisect_left

from rapidfuzz import fuzz

LATEX_COMMAND = re.compile(r"\\[a-zA-Z]+")
DATASET_MARKUP = re.compile(r"\b(?:BIBREF|TABREF|FIGREF|SECREF|EQREF)\d+\b")
IGNORED = set("|&$\\{}^_*#`~-‐‑‒–—―−")
QUOTES = {"‘": "'", "’": "'", "‚": "'", "‛": "'", "“": '"', "”": '"', "„": '"', "‟": '"'}


def normalise_char(char):
    if char.isspace() or char in IGNORED:
        return ""
    return QUOTES.get(char) or unicodedata.normalize("NFKC", char).lower()


def normalise_with_map(text):
    """Normalised text plus, for each normalised character, the index of the original character it came from."""
    characters, index_map = [], []
    for index, char in enumerate(text):
        for piece in normalise_char(char):
            characters.append(piece)
            index_map.append(index)
    return "".join(characters), index_map


def clean_evidence(evidence):
    return normalise_with_map(DATASET_MARKUP.sub(" ", LATEX_COMMAND.sub(" ", evidence)))[0]


def find_all(haystack, needle):
    positions, start = [], haystack.find(needle)
    while start != -1:
        positions.append(start)
        start = haystack.find(needle, start + 1)
    return positions


def page_bounds(pages, page_number):
    return next(((page["start_char"], page["end_char"]) for page in pages if page["page"] == page_number), None)


def choose(spans, pages, page_number):
    """A single span is kept; with several, only a single span on the stated page is kept."""
    if len(spans) == 1:
        return spans[0], "unique"
    bounds = page_bounds(pages, page_number) if page_number is not None else None
    on_page = [span for span in spans if bounds and bounds[0] <= span[0] < bounds[1]]
    return (on_page[0], "page_disambiguated") if len(on_page) == 1 else (None, "ambiguous")


def search_window(pages, page_number, index_map, length):
    nearby = [page for page in pages if page_number is not None and abs(page["page"] - page_number) <= 1]
    if not nearby:
        return 0, length
    return (bisect_left(index_map, min(page["start_char"] for page in nearby)),
            bisect_left(index_map, max(page["end_char"] for page in nearby)))


def fuzzy(needle, pages, normalised_text, index_map, page_number):
    window_start, window_end = search_window(pages, page_number, index_map, len(normalised_text))
    alignment = fuzz.partial_ratio_alignment(needle, normalised_text[window_start:window_end])
    start, end = window_start + alignment.dest_start, window_start + alignment.dest_end
    span = (index_map[start], index_map[end - 1] + 1) if end > start else None
    return {"method": "fuzzy", "resolution": "flagged", "span": span, "score": round(alignment.score, 1)}


def place(evidence, text, pages, normalised_text, index_map, page_number):
    exact = [(start, start + len(evidence)) for start in find_all(text, evidence)] if evidence.strip() else []
    if exact:
        span, resolution = choose(exact, pages, page_number)
        return {"method": "exact", "resolution": resolution, "span": span, "score": 100.0}
    needle = clean_evidence(evidence)
    if not needle:
        return {"method": "empty", "resolution": "missing", "span": None, "score": 0.0}
    normalised = [(index_map[start], index_map[start + len(needle) - 1] + 1) for start in find_all(normalised_text, needle)]
    if normalised:
        span, resolution = choose(normalised, pages, page_number)
        return {"method": "normalised", "resolution": resolution, "span": span, "score": 100.0}
    return fuzzy(needle, pages, normalised_text, index_map, page_number)