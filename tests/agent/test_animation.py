"""Indexing animation (spec/agent_v1.md, App v1.1): the running loop and the done state are valid SVG/HTML, the
progress line shows only the values passed in, reduced motion falls back to the plain bar, and every step
open_index logs has a name. No model and no API call."""
import re
import xml.etree.ElementTree as ElementTree

from app import animation
from src.agent.ask import ProgressLogger, open_index
from tests.agent.conftest import fake_embed
from tests.agent.test_app import pdf_path

SVG = "{http://www.w3.org/2000/svg}"


def body(block):
    """The markup after the shared <style>, parsed as XML (raises on anything malformed)."""
    assert block.startswith("<style>") and block.count("</style>") == 1
    return ElementTree.fromstring(block.split("</style>", 1)[1])


def test_running_is_a_valid_looping_svg():
    root = body(animation.render_running())
    assert root.get("data-state") == "running"
    svg = root.find(f"{SVG}svg")
    assert svg is not None and svg.get("viewBox") == "0 0 240 200"
    pieces = [group for group in svg.iter(f"{SVG}g") if group.get("class") == "piece"]
    assert len(pieces) == 8 and all(piece.find(f"{SVG}polygon") is not None for piece in pieces)
    assert len([line for line in svg.iter(f"{SVG}line") if "cut" in line.get("class")]) == 2
    assert f"{animation.LOOP_SECONDS}s" in animation.STYLE and "infinite" in animation.STYLE


def test_pieces_tile_the_page():
    """Shoelace areas of the 8 pieces add up to the page (shared seams, no gaps or overlaps)."""
    area = lambda shape: abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(shape, shape[1:] + shape[:1]))) / 2
    page = (animation.RIGHT - animation.LEFT) * (animation.ROWS[-1] - animation.ROWS[0])
    assert abs(sum(area(shape) for shape in animation.pieces()) - page) < 1e-6


def test_done_is_static():
    block = animation.render_done(42)
    root = body(block)
    assert root.get("data-state") == "done" and "✓" in root.findtext("span") and "42 chunks ready" in "".join(root.itertext())
    assert "<svg" not in block and "class=\"ixa\"" not in block  # the loop is gone


def test_progress_line_shows_only_real_values():
    assert "".join(body(animation.progress_line("scan_check", {})).itertext()) == "Scan check"
    facts = {"pages": 6, "pages_without_text": 0}
    assert "".join(body(animation.progress_line("parse", facts)).itertext()) == "Parse · 6 pages, 0 without text"
    assert "OCR · 6 pages, 2 without text" in animation.progress_line("parse", {"pages": 6, "pages_without_text": 2})
    embed = animation.progress_line("embed", {**facts, "chunks": 40, "embedded": 20})
    assert "embedded 20 / 40 chunks" in embed and "width:88%" in embed  # (3 + 20/40) of 4 stages
    numbers = set(re.findall(r"\d+", "".join(body(embed).itertext())))
    assert numbers == {"6", "0", "20", "40"}  # nothing else appears


def test_reduced_motion_shows_the_plain_bar_instead():
    rule = re.search(r"@media \(prefers-reduced-motion:reduce\)\{(.*)\}", animation.STYLE).group(1)
    assert ".ixa{display:none}" in rule and ".ixp .track{display:block}" in rule
    assert ".ixp .track{display:none" in animation.STYLE  # hidden while motion is allowed
    assert 'class="track"' in animation.progress_line("chunk", {})


def test_every_logged_step_has_a_name(tmp_path):
    seen = []
    logger = ProgressLogger(lambda name, state, record: seen.append(name))
    open_index(pdf_path(), logger, "A-LOCAL-test", fast=True, cache_root=tmp_path, embed=fake_embed)
    open_index(pdf_path(), logger, "A-LOCAL-test", fast=True, cache_root=tmp_path, embed=fake_embed)  # cache hit
    assert set(seen) == set(animation.STEPS) == set(animation.BAR_STAGE)


def test_step_records_carry_the_counts(tmp_path):
    records = {}
    logger = ProgressLogger(lambda name, state, record: records.update({name: dict(record)}) if state == "done" else None)
    session = open_index(pdf_path(), logger, "A-LOCAL-test", fast=True, cache_root=tmp_path, embed=fake_embed)
    assert records["scan_check"]["pages"] == session["planned"]["page_count"]
    assert records["scan_check"]["pages_without_text"] == len(session["planned"]["empty_pages"])
    assert records["chunk"]["chunks"] == len(session["chunks"])
