"""Checks of the built IEEE paper: hand-typed numbers, log warnings, labels, macros, terms, caption places. Run after a
build: python -m paper_ieee.scripts.check_paper (exit code 1 if any check fails). Reads only; changes nothing."""
import re
import sys
from pathlib import Path

PAPER = Path(__file__).resolve().parents[1]

TERMS = {  # editable: pattern -> what is wrong
    r"(?i)\bheld-out[ ~-]\d": "held-out N without 'set'",
    r"\bFig(?:ure)?s?\b(?!\.~\\ref)": r"Fig without .~\ref",
    r"\bTables?\b(?!~\\ref)": r"Table without ~\ref",
}
NAMES = [  # editable: digits that belong to a name, not a typed result
    r"@[\d,]*\d",  # Recall@1,250
    r"\bset[~ ]\d",  # held-out set~1
    r"held-out-\d",
    r"\b4-bit\b",
    r"[A-Za-z][\w-]*\d\w*(?:[.-]\w+)*",  # RQ2, F1, BM25, Qwen3-8B, v1.2
]
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
ALLOWED = [  # editable: design constants, dates and versions that may be typed
    rf"\b\d{{1,2}}[~ ](?:{MONTHS})(?:[~ ]\d{{4}})?",  # dates
    r"\b(?:Docling|pdfplumber|Gemini)~\d+(?:\.\d+)+",  # versions
    r"(?<![\d.,])(?:750|1,250|2,000)(?![\d%]|[.,]\d)",  # budgets; 2,000 resamples
    r"(?<![\d.,])(?:256|384|512|1,024)(?![\d%]|[.,]\d)",  # chunk sizes; post-processing maximum; embedding dimensions
    r"\b100 tokens",  # post-processing minimum
    r"\bseed\s+42\b", r"\b200 random splits", r"\b(?:95|10|5)\\%",  # statistics; shares
    r"(?<![\d.])(?:k=60|k_?1=1\.5|b=0\.75)(?![\d.])",  # retrieval (outside math)
]
LATEX_CAPITALS = {"Alpha", "Beta", "Gamma", "Delta", "Theta", "Lambda", "Pi", "Sigma", "Phi", "Psi", "Omega", "LaTeX", "TeX"}


def blank(pattern, text, flags=0):
    """Remove matches but keep their line breaks, so line numbers stay right."""
    return re.sub(pattern, lambda match: " " + "\n" * match[0].count("\n"), text, flags=flags)


def load(path):
    return blank(r"(?<!\\)%[^\n]*", path.read_text(encoding="utf-8"))


def included(path):
    """The file and every file it inputs, as LaTeX sees them."""
    found = {path: load(path)}
    for name in re.findall(r"\\input\{([^}]+)\}", found[path]):
        child = PAPER / (name if name.endswith(".tex") else f"{name}.tex")
        if child.exists():
            found |= included(child)
    return found


def hits(files, pattern, note=None):
    return [f"{path.relative_to(PAPER)}:{text.count(chr(10), 0, match.start()) + 1}  {note or ''}{' ' if note else ''}"
            f"[{text.splitlines()[text.count(chr(10), 0, match.start())].strip()[:90] if note else match[0]}]"
            for path, text in files.items() for match in re.finditer(pattern, text)]


def without_sourced(path, text):
    """Blank the lines whose raw line ends with '% src: <file>:<line>' (or :<first>-<last>), if that place exists."""
    lines = text.split("\n")
    for index, raw in enumerate(path.read_text(encoding="utf-8").split("\n")):
        match = re.search(r"(?<!\\)% src: (\S+):(\d+)(?:-(\d+))?\s*$", raw)
        if match and (source := PAPER.parent / match[1]).is_file():
            if int(match[3] or match[2]) <= len(source.read_text(encoding="utf-8").splitlines()):
                lines[index] = ""
    return "\n".join(lines)


def typed_numbers(sections):
    """Math holding a letter ($k=60$, $B$) is left out; purely numeric math is still reported."""
    bare = {}
    for path, text in sections.items():
        text = blank(r"\\(?:ref|label|cite|input|eqref)\{[^}]*\}", text)
        text = blank(r"\$[^$]*[A-Za-z][^$]*\$", text)
        for allowed in ALLOWED:
            text = blank(allowed, text)
        text = blank(r"\\[A-Za-z]+(?:\[[^\]]*\])?", text)
        for name in NAMES:
            text = blank(name, text)
        bare[path] = text
    return hits({path: without_sourced(path, text) for path, text in bare.items()}, r"\d(?:[\d.,]|\{,\})*")


def log_problems():
    log = PAPER / "main.log"
    if not log.exists():
        return ["main.log missing: build first"]
    text = re.sub(r"(?m)^(.{79})\n", r"\1", log.read_text(encoding="utf-8", errors="replace"))  # TeX wraps log lines at 79
    found = re.findall(r"(?m)^(?:!.*|LaTeX Warning: (?:Reference|Citation) .*undefined.*|Overfull \\[hv]box.*)", text)
    return list(dict.fromkeys(line.replace("LaTeX Warning: ", "") for line in found))


def label_problems(files):
    text = "\n".join(files.values())
    labels = re.findall(r"\\label\{([^}]+)\}", text)
    refs = {name for group in re.findall(r"\\(?:eq|auto|page|c|C)?ref\{([^}]+)\}", text) for name in group.split(",")}
    return ([f"never referenced: {name}" for name in labels if name.startswith(("tab:", "fig:")) and name not in refs]
            + [f"no label for: {name}" for name in sorted(refs - set(labels))]
            + [f"label defined twice: {name}" for name in sorted({name for name in labels if labels.count(name) > 1})])


def missing_macros(sections):
    """Study macros start with a capital letter; other unknown commands are LaTeX errors ('!' in the log check)."""
    defined = set(re.findall(r"\\newcommand\{\\([A-Za-z]+)\}", load(PAPER / "generated/numbers.tex"))) | LATEX_CAPITALS
    return [line for line in hits(sections, r"\\[A-Z][A-Za-z]+") if re.search(r"\[\\(\w+)\]", line)[1] not in defined]


def caption_problems(files):
    body = {"table": r"\\begin\{(?:tabular|tabularx)", "figure": r"\\(?:input|includegraphics)\b|\\begin\{tikzpicture"}
    problems = []
    for path, text in files.items():
        for kind, content in re.findall(r"\\begin\{(table|figure)\*?\}(.*?)\\end\{\1\*?\}", text, flags=re.S):
            caption, start = content.find(r"\caption"), re.search(body[kind], content)
            if caption < 0 or not start or (caption < start.start()) != (kind == "table"):
                problems.append(f"{path.relative_to(PAPER)}  {kind} caption must be {'above' if kind == 'table' else 'below'}")
    return problems


def main():
    files = included(PAPER / "main.tex")
    sections = {path: load(path) for path in sorted((PAPER / "sections").glob("*.tex"))}
    prose = {path: text for path, text in files.items() if path.name != "numbers.tex"}
    checks = {"1 hand-typed numbers": typed_numbers(sections), "2 log": log_problems(), "3 labels and refs": label_problems(files),
              "4 macros": missing_macros(sections), "5 terms": [line for pattern, note in TERMS.items() for line in hits(prose | sections, pattern, note)],
              "6 captions": caption_problems(files)}
    for name, problems in checks.items():
        print(f"{'FAIL' if problems else 'PASS'}  {name}" + (f" ({len(problems)})" if problems else ""))
        for problem in problems:
            print(f"      {problem}")
    sys.exit(any(checks.values()))


if __name__ == "__main__":
    main()
