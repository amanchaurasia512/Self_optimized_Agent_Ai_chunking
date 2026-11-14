"""Chunking strategy shown in the app (spec/agent_v1.md, App v1.1): the chunker line comes from the run record, and
every number in "Why these settings?" appears in RESULTS.md."""
import re

from app import explain
from src.common.paths import PROJECT_ROOT

RESULTS = (PROJECT_ROOT / "RESULTS.md").read_text(encoding="utf-8")


def record(name="method1_tree", tokens=384, prefix=False, parser="docling"):
    return {"stack": {"chunker": {"name": name, "settings": {"T": tokens, "heading_prefix": prefix}},
                      "parser": {"name": parser}}}


def test_chunker_line_is_read_from_the_run_record():
    assert explain.chunker_line(record()) == "Chunker: method1_tree (structure-tree), 384 tokens, no prefix · parser: Docling"
    assert (explain.chunker_line(record("fixed_token", 256, True, "pdfplumber"))
            == "Chunker: fixed_token, 256 tokens, heading prefix · parser: pdfplumber")


def test_every_number_in_the_reasons_is_in_results():
    plain = lambda text: text.replace("−", "-").replace(",", "")  # thousands commas and minus signs vary
    results = plain(RESULTS)
    numbers = {number for point in explain.WHY for number in re.findall(r"-?\d+(?:\.\d+)?", plain(point))}
    assert {"0.772", "0.752", "15", "26", "0.123", "0.065", "0.10", "0.12", "-0.007", "-0.045", "0.023", "1250"} <= numbers
    assert not [number for number in numbers if number not in results]
    assert "−0.007 [−0.045, 0.023]" in RESULTS and "15 of 26" in RESULTS


def test_link_goes_to_the_research_questions_section():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "\n## Research questions\n" in readme and explain.README_QUESTIONS.endswith("#research-questions")
