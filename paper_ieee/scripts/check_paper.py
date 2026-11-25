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
    r"\bset~\d",  # held-out set~1
    r"held-out-\d",
    r"[A-Za-z][\w-]*\d\w*(?:[.-]\w+)*",  # RQ2, F1, BM25, Qwen3-8B, v1.2
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


def typed_numbers(sections):
    """Math holding a letter ($k=60$, $B$) is left out; purely numeric math is still reported."""
    bare = {}
    for path, text in sections.items():
        text = blank(r"\\(?:ref|label|cite|input|eqref)\{[^}]*\}", text)
        text = blank(r"\$[^$]*[A-Za-z][^$]*\$", text)
        text = blank(r"\\[A-Za-z]+(?:\[[^\]]*\])?", text)
        for name in NAMES:
            text = blank(name, text)
        bare[path] = text
    return hits(bare, r"\d(?:[\d.,]|\{,\})*")


def log_problems(files):
    log = PAPER / "main.log"
    if not log.exists():
        return ["main.log missing: build first"]
    stale = [f"main.log is older than {path.relative_to(PAPER)}: build again" for path in files if path.stat().st_mtime > log.stat().st_mtime]
    text = re.sub(r"(?m)^(.{79})\n", r"\1", log.read_text(encoding="utf-8", errors="replace"))  # TeX wraps log lines at 79
    found = re.findall(r"(?m)^(?:!.*|LaTeX Warning: (?:Reference|Citation) .*undefined.*|Overfull \\[hv]box.*)", text)
    return stale + list(dict.fromkeys(line.replace("LaTeX Warning: ", "") for line in found))


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
    checks = {"1 hand-typed numbers": typed_numbers(sections), "2 log": log_problems(files), "3 labels and refs": label_problems(files),
              "4 macros": missing_macros(sections), "5 terms": [line for pattern, note in TERMS.items() for line in hits(prose | sections, pattern, note)],
              "6 captions": caption_problems(files)}
    for name, problems in checks.items():
        print(f"{'FAIL' if problems else 'PASS'}  {name}" + (f" ({len(problems)})" if problems else ""))
        for problem in problems:
            print(f"      {problem}")
    sys.exit(any(checks.values()))


if __name__ == "__main__":
    main()
