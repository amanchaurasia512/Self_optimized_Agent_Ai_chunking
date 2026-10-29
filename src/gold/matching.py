"""Place gold evidence in a parser's frozen text: exact -> normalised -> fuzzy (always flagged), choosing by page
when the evidence occurs more than once. Normalisation ignores case, whitespace, quote/dash style and table/LaTeX
notation, so glued words and Markdown/LaTeX tables still match; positions always map back to the original text."""
import re
import unicodedata
from bisect import bisect_left
from src.common.manifest import PROJECT_ROOT
from rapidfuzz import fuzz

LATEX_ENVIRONMENT = re.compile(r"\\(?:begin|end)\{[^}]*\}(?:\{[^}]*\})?")
LATEX_COMMAND = re.compile(r"\\[a-zA-Z]+")
DATASET_MARKUP = re.compile(r"\b(?:BIBREF|TABREF|FIGREF|SECREF|EQREF)\d+\b")
JSON_ESCAPE_DAMAGE = {0x08: "\\b", 0x0C: "\\f"}  # LaTeX "\b"/"\f" turned into control characters by JSON decoding
SEGMENT_BOUNDARY = re.compile(r"\.\.\.|…|\\\\|;\s+|(?<=[.!?:])\s+(?=[A-Z0-9\"'(])")
WORD = re.compile(r"\w+")
IGNORED = set("|&$\\{}^_*#`~-‐‑‒–—―−")
QUOTES = {"‘": "'", "’": "'", "‚": "'", "‛": "'", "“": '"', "”": '"', "„": '"', "‟": '"'}
LATEX_TABLE_FORMAT = re.compile(r"\\multicolumn\s*\{[^{}]*\}\s*\{[^{}]*\}"
                                r"|\\multirow\s*(?:\[[^\]]*\])?\s*\{[^{}]*\}\s*\{[^{}]*\}|\\cline\s*\{[^{}]*\}")
REFERENCE_LABEL = re.compile(r"\b[a-z]{2,3}:[A-Za-z][\w-]*")  # converted \ref labels such as eq:SMT, ta:quality
UNCERTAIN = {"fuzzy", "segment_fuzzy"}
DROP_RULE_FILE = PROJECT_ROOT / "configs" / "gold_drop_rule.json"


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


def strip_markup(evidence):
    restored = evidence.translate(JSON_ESCAPE_DAMAGE)
    without_latex = LATEX_COMMAND.sub(" ", LATEX_ENVIRONMENT.sub(" ", LATEX_TABLE_FORMAT.sub(" ", restored)))
    return REFERENCE_LABEL.sub(" ", DATASET_MARKUP.sub(" ", without_latex))


def gold_words(evidence):
    return set(WORD.findall(strip_markup(evidence).lower()))


def missing_words(evidence, placed_text):
    return sorted(gold_words(evidence) - set(WORD.findall(placed_text.lower())))


def clean_evidence(evidence):
    return normalise_with_map(strip_markup(evidence))[0]


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

def normalised_hits(needle, normalised_text, index_map, low=0, high=None):
    region = normalised_text[low:high]
    return [(index_map[low + start], index_map[low + start + len(needle) - 1] + 1) for start in find_all(region, needle)]


def snap(span, text):
    """Move span edges onto whole words: skip leading/trailing punctuation, extend cut words."""
    start, end = span
    while start < end and not text[start].isalnum():
        start += 1
    while start > 0 and text[start - 1].isalnum() and text[start].isalnum():
        start -= 1
    while end > start and not text[end - 1].isalnum():
        end -= 1
    while end < len(text) and text[end - 1].isalnum() and text[end].isalnum():
        end += 1
    return start, end



def word_coverage(evidence, placed_text):
    words = gold_words(evidence)
    return round(1 - len(missing_words(evidence, placed_text)) / len(words), 3) if words else 0.0

def segments(evidence):
    """Pieces of the evidence; a piece with fewer than two letters or digits (a list label like 'A.') can't be placed."""
    pieces = [piece.strip() for piece in SEGMENT_BOUNDARY.split(strip_markup(evidence))]
    return [piece for piece in pieces if sum(char.isalnum() for char in piece) >= 2]

def place_segments(evidence, around, text, normalised_text, index_map):
    """Place each piece within one evidence-length of the fuzzy match: exactly if possible, otherwise fuzzily (flagged)."""
    reach = len(evidence)
    low, high = bisect_left(index_map, max(around[0] - reach, 0)), bisect_left(index_map, around[1] + reach)
    placements = []
    for piece in segments(evidence):
        needle = clean_evidence(piece)
        hits = normalised_hits(needle, normalised_text, index_map, low, high)
        if hits:
            span = min(hits, key=lambda hit: abs(hit[0] - around[0]))
            placement = {"method": "segment", "resolution": "in_region" if len(hits) == 1 else "nearest",
                         "span": span, "score": 100.0, "word_coverage": 1.0}
        else:
            placement = align(needle, piece, text, normalised_text, index_map, low, high, "segment_fuzzy")
        placements.append({**placement, "segment": piece})
    exact_share = sum(len(item["segment"]) for item in placements if item["method"] == "segment")
    coverage = round(exact_share / max(sum(len(item["segment"]) for item in placements), 1), 3)
    return [{**item, "segment_coverage": coverage} for item in placements] if exact_share else []

def search_window(pages, page_number, index_map, length):
    nearby = [page for page in pages if page_number is not None and abs(page["page"] - page_number) <= 1]
    if not nearby:
        return 0, length
    return (bisect_left(index_map, min(page["start_char"] for page in nearby)),
            bisect_left(index_map, max(page["end_char"] for page in nearby)))


def align(needle, evidence, text, normalised_text, index_map, low, high, method):
    """Best fuzzy alignment of needle inside normalised_text[low:high], snapped to whole words."""
    alignment = fuzz.partial_ratio_alignment(needle, normalised_text[low:high])
    start, end = low + alignment.dest_start, low + alignment.dest_end
    if end <= start:
        return {"method": method, "resolution": "missing", "span": None, "score": 0.0, "word_coverage": 0.0}
    span = snap((index_map[start], index_map[end - 1] + 1), text)
    return {"method": method, "resolution": "flagged", "span": span, "score": round(alignment.score, 1),
            "word_coverage": word_coverage(evidence, text[span[0]:span[1]])}


def fuzzy(needle, evidence, text, pages, normalised_text, index_map, page_number):
    low, high = search_window(pages, page_number, index_map, len(normalised_text))
    return align(needle, evidence, text, normalised_text, index_map, low, high, "fuzzy")


def place(evidence, text, pages, normalised_text, index_map, page_number):
    """Returns a list of placements: one for exact/normalised/fuzzy, several when the evidence is placed piecewise."""
    exact = [(start, start + len(evidence)) for start in find_all(text, evidence)] if evidence.strip() else []
    if exact:
        span, resolution = choose(exact, pages, page_number)
        return [{"method": "exact", "resolution": resolution, "span": span, "score": 100.0, "word_coverage": 1.0}]
    needle = clean_evidence(evidence)
    if not needle:
        return [{"method": "empty", "resolution": "missing", "span": None, "score": 0.0, "word_coverage": 0.0}]
    normalised = normalised_hits(needle, normalised_text, index_map)
    if normalised:
        span, resolution = choose(normalised, pages, page_number)
        return [{"method": "normalised", "resolution": resolution, "span": span, "score": 100.0, "word_coverage": 1.0}]
    approximate = fuzzy(needle, evidence, text, pages, normalised_text, index_map, page_number)
    pieces = place_segments(evidence, approximate["span"], text, normalised_text, index_map) if approximate["span"] else []
    return pieces or [approximate]