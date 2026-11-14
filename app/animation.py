"""Indexing animation for the local app (spec/agent_v1.md, App v1.1): one hand-made SVG loop (about 4 s) while a PDF is
indexed, a progress line with the real step and counts from the progress callback, and a static "✓ N chunks ready"
when done. Plain HTML strings (no Streamlit), so it is testable on its own. The loop and the line are separate blocks:
updating the line never restarts the loop. Under prefers-reduced-motion the loop is hidden and the line shows a plain
progress bar. Colours derive from currentColor (Streamlit's theme text colour), so they follow light and dark themes."""
from html import escape

LOOP_SECONDS = 4
GREEN = "#21c354"  # Streamlit's success green, readable on light and dark backgrounds
STEPS = {"scan_check": "Scan check", "load_index": "Cache lookup", "parse": "Parse", "chunk": "Chunk", "embed": "Embed",
         "load_vectors": "Load vectors"}  # every step open_index logs
ORDER = ("scan_check", "parse", "chunk", "embed")  # the bar's stages; cache lookup and load vectors count with their neighbours
BAR_STAGE = {"scan_check": 0, "load_index": 0, "parse": 1, "chunk": 2, "embed": 3, "load_vectors": 4}

# Page geometry and the jagged seams that cut it into 8 pieces (2 columns x 4 rows). Neighbouring pieces share seams,
# so together they tile the page exactly.
LEFT, RIGHT, ROWS = 70, 170, (30, 65, 100, 135, 170)
MIDS = (120, 126, 114, 124, 118)  # where each row seam meets the vertical seam
JAGS = ((0, 0), (5, -4), (-4, 5), (4, -5), (0, 0))  # row seam bumps, left and right of the middle
VERTICAL_JAGS = (-5, 6, -6, 5)  # vertical seam bumps, one per row band
TEXT_ROWS = range(40, 165, 11)  # grey text lines across the page


def row_seam(row):
    """(left half from the page edge to the middle, right half from the middle to the edge) of a row seam."""
    y, mid, (left_jag, right_jag) = ROWS[row], MIDS[row], JAGS[row]
    return [(LEFT, y), (95, y + left_jag), (mid, y)], [(mid, y), (145, y + right_jag), (RIGHT, y)]


def pieces():
    """The 8 polygons, row band by row band, left then right."""
    shapes = []
    for band in range(len(ROWS) - 1):
        (top_left, top_right), (bottom_left, bottom_right) = row_seam(band), row_seam(band + 1)
        middle = ((MIDS[band] + MIDS[band + 1]) / 2 + VERTICAL_JAGS[band], (ROWS[band] + ROWS[band + 1]) / 2)
        shapes.append(top_left + [middle] + bottom_left[::-1])
        shapes.append(top_right + bottom_right[::-1] + [middle])
    return shapes


def points(shape):
    return " ".join(f"{x:g},{y:g}" for x, y in shape)


def flight(shape, number):
    """Outward direction (from the page centre through the piece's centre) and a rotation, alternating in sign."""
    cx, cy = sum(x for x, y in shape) / len(shape), sum(y for x, y in shape) / len(shape)
    return 1.6 * (cx - 120), 1.6 * (cy - 100), (25 + 7 * number) * (1 if number % 2 else -1)


STYLE = f"""<style>
.ixa{{color:inherit;max-width:360px;margin:0 auto}}
.ixa svg{{width:100%;height:auto;display:block;overflow:visible}}
.ixa .page{{fill:color-mix(in srgb,currentColor 6%,transparent);stroke:color-mix(in srgb,currentColor 35%,transparent);stroke-width:1}}
.ixa .text{{fill:color-mix(in srgb,currentColor 30%,transparent)}}
.ixa .whole{{animation:ixa-whole {LOOP_SECONDS}s ease-in-out infinite}}
.ixa .piece{{transform-box:fill-box;transform-origin:center;animation:ixa-fly {LOOP_SECONDS}s cubic-bezier(.2,.7,.3,1) infinite}}
.ixa .cut{{stroke:{GREEN};stroke-width:2.5;stroke-linecap:round;fill:none;stroke-dasharray:1;stroke-dashoffset:1}}
.ixa .cut.one{{animation:ixa-cut-one {LOOP_SECONDS}s linear infinite}}
.ixa .cut.two{{animation:ixa-cut-two {LOOP_SECONDS}s linear infinite}}
.ixa .blade{{fill:color-mix(in srgb,currentColor 75%,transparent);opacity:0;animation:ixa-blade {LOOP_SECONDS}s ease-in infinite}}
@keyframes ixa-whole{{0%{{opacity:0;transform:translateY(8px)}}10%,45%{{opacity:1;transform:none}}47%{{transform:translate(-3px,1px)}}
 49%{{transform:translate(3px,-1px)}}51%{{transform:translate(-2px,1px)}}53%{{transform:translate(2px,0)}}55%,100%{{opacity:1;transform:none}}}}
@keyframes ixa-fly{{0%,55%{{opacity:1;transform:none}}88%,100%{{opacity:0;transform:translate(var(--tx),var(--ty)) rotate(var(--rot))}}}}
@keyframes ixa-cut-one{{0%,16%{{stroke-dashoffset:1;opacity:1}}23%,55%{{stroke-dashoffset:0;opacity:1}}62%,100%{{stroke-dashoffset:0;opacity:0}}}}
@keyframes ixa-cut-two{{0%,31%{{stroke-dashoffset:1;opacity:1}}38%,55%{{stroke-dashoffset:0;opacity:1}}62%,100%{{stroke-dashoffset:0;opacity:0}}}}
@keyframes ixa-blade{{0%,13%{{opacity:0;transform:translate(60px,25px) rotate(50deg)}}15%{{opacity:1;transform:translate(70px,40px) rotate(50deg)}}
 24%{{opacity:1;transform:translate(170px,160px) rotate(50deg)}}26%,28%{{opacity:0;transform:translate(170px,160px) rotate(50deg)}}
 29%{{opacity:0;transform:translate(178px,40px) rotate(132deg)}}30%{{opacity:1;transform:translate(178px,40px) rotate(132deg)}}
 39%{{opacity:1;transform:translate(70px,160px) rotate(132deg)}}41%,100%{{opacity:0;transform:translate(70px,160px) rotate(132deg)}}}}
.ixp{{color:inherit;font-size:0.9rem}}
.ixp p{{margin:0.3rem 0;text-align:center}}
.ixp .track{{display:none;height:8px;border-radius:4px;background:color-mix(in srgb,currentColor 15%,transparent);overflow:hidden}}
.ixp .fill{{height:100%;background:{GREEN}}}
.ixd{{color:inherit;text-align:center;font-size:1.05rem;margin:0.5rem 0}}
.ixd .tick{{color:{GREEN};font-weight:700}}
@media (prefers-reduced-motion:reduce){{.ixa{{display:none}}.ixp .track{{display:block}}}}
</style>"""


def render_running():
    """The looping scene: page appears, two diagonal slashes leave green cuts, the page shakes and breaks apart."""
    text = "".join(f'<rect class="text" x="{LEFT + 10}" y="{y}" width="{80 - 14 * (row % 3)}" height="3.5" rx="1.5"/>'
                   for row, y in enumerate(TEXT_ROWS))
    body = []
    for number, shape in enumerate(pieces()):
        tx, ty, rot = flight(shape, number)
        body.append(f'<g class="piece" style="--tx:{tx:.0f}px;--ty:{ty:.0f}px;--rot:{rot}deg">'
                    f'<clipPath id="ixa-piece-{number}"><polygon points="{points(shape)}"/></clipPath>'
                    f'<polygon class="page" points="{points(shape)}"/><g clip-path="url(#ixa-piece-{number})">{text}</g></g>')
    cuts = ('<line class="cut one" pathLength="1" x1="98" y1="72" x2="142" y2="125"/>'
            '<line class="cut two" pathLength="1" x1="146" y1="74" x2="100" y2="126"/>')
    blade = '<g class="blade"><polygon points="-6,-3 34,0 -6,3"/><rect x="-18" y="-3.5" width="12" height="7" rx="2"/></g>'
    return (f'{STYLE}<div class="ixa" data-state="running"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 200" '
            f'role="img" aria-label="Indexing the PDF"><g class="whole">{"".join(body)}{cuts}</g>{blade}</svg></div>')


def step_name(step, facts):
    """The step's name; parse is called OCR when pages have no text layer (Docling then reads them in either mode,
    src/agent/pipeline.choose_parser)."""
    if step == "parse" and facts.get("pages_without_text"):
        return "OCR"
    return STEPS[step]


def progress_line(step, facts):
    """One line from the callback's real values only, plus the plain bar shown instead of the loop under reduced motion."""
    parts = [step_name(step, facts)]
    if facts.get("pages") is not None:
        parts.append(f"{facts['pages']} pages, {facts['pages_without_text']} without text")
    if step == "embed" and facts.get("chunks"):
        parts.append(f"embedded {facts.get('embedded', 0)} / {facts['chunks']} chunks")
    inside = facts.get("embedded", 0) / facts["chunks"] if step == "embed" and facts.get("chunks") else 0
    share = min(1.0, (BAR_STAGE[step] + inside) / len(ORDER))
    return (f'{STYLE}<div class="ixp" data-step="{step}"><p>{escape(" · ".join(parts))}</p>'
            f'<div class="track"><div class="fill" style="width:{100 * share:.0f}%"></div></div></div>')


def render_done(chunks):
    """Static, no animation: the loop has stopped."""
    return f'{STYLE}<div class="ixd" data-state="done"><span class="tick">✓</span> {chunks} chunks ready</div>'
