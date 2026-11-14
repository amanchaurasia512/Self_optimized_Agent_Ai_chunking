"""Source checks for make check (spec/paper_build_spec.md, sections 2 and 4):
- no typed numbers: no digit in sections/*.tex outside comments, except metric and question names (allowlist);
- Limitations adds no results: every macro it uses also appears in another section file;
- fonts: no \\footnotesize, \\scriptsize, \\tiny, \\resizebox or \\scalebox in sections, main.tex or generated files.
Exit status 1 with every hit listed."""
import argparse
import re
from pathlib import Path

PAPER = Path(__file__).resolve().parents[1]
ALLOWED = re.compile(r"\\(?:label|ref|cref|Cref|autoref|input|generated|cite[pt]?|nocite)\{[^}]*\}"  # names, not numbers
                     r"|Recall@[\d,]+|Hit@\d+|R@\d+|RQ[1-5]|BM25|F1\b|95\\%")  # 95\% is the interval level
FORBIDDEN_FONTS = re.compile(r"\\(footnotesize|scriptsize|tiny|resizebox|scalebox)\b")
MACRO = re.compile(r"\\([A-Za-z]+)")


def code_lines(path):
    """(line number, text without the comment) for every line of a .tex file; an escaped \\% is not a comment."""
    return [(number, re.split(r"(?<!\\)%", line, maxsplit=1)[0]) for number, line in
            enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)]


def typed_numbers(sections):
    return [f"{path.name}:{number}: typed number in '{text.strip()}'" for path in sections for number, text in code_lines(path)
            if re.search(r"\d", ALLOWED.sub("", text))]


def limitation_macros(sections, defined):
    limitations = [path for path in sections if path.name == "limitations.tex"]
    others = {name for path in sections if path.name != "limitations.tex" for number, text in code_lines(path) for name in MACRO.findall(text)}
    used = {name for path in limitations for number, text in code_lines(path) for name in MACRO.findall(text)} & defined
    return [f"limitations.tex: \\{name} appears in no other section (Limitations may not add results)" for name in sorted(used - others)]


def fonts(files, paper):
    return [f"{path.relative_to(paper)}:{number}: {match.group(0)}" for path in files for number, text in code_lines(path)
            for match in FORBIDDEN_FONTS.finditer(text)]


def check(paper):
    sections = sorted((paper / "sections").glob("*.tex"))
    numbers_file = paper / "generated" / "tables" / "numbers.tex"
    defined = set(re.findall(r"\\newcommand\{\\([A-Za-z]+)\}", numbers_file.read_text(encoding="utf-8"))) if numbers_file.exists() else set()
    generated = sorted((paper / "generated").rglob("*.tex"))
    return typed_numbers(sections) + limitation_macros(sections, defined) + fonts(sections + [paper / "main.tex"] + generated, paper)


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--paper", type=Path, default=PAPER)
    problems = check(arg_parser.parse_args().paper)
    print("\n".join(problems) if problems else "source checks passed")
    raise SystemExit(1 if problems else 0)


if __name__ == "__main__":
    main()
