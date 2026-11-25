"""Paper 1 artifacts for the IEEE paper (paper_ieee/): numbers.tex (one macro per number) and one IEEE float per table,
generated from locked result files only (data/results/, runs/, and the manual facts as tagged); nothing is re-run.
Based on the paper-v1.2 generator (paper/scripts/make_artifacts.py). Inputs frozen at paper-v1.2 are checked against
docs/paper_checksums.txt as tagged; inputs made after the tag (held-out 2, extension, second embedder) are checked
against docs/paper_checksums_v1.3.txt (paper-v1.3 lock). Outputs go to paper_ieee/generated/ only and are byte-identical
between runs. --no-tag-check skips the tag checks (tests on fake data only)."""
import argparse
import hashlib
import io
import json
import math
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from scripts.aq_run import BUDGET, RECALL_RUNS, SHARE as AQ_SHARE, cohen_kappa
from scripts.golden_check import DOCS as GOLDEN_DOCS, wilson
from scripts.p3_fixedk import MEASURES, best_sizes
from scripts.p4_analyse import SPLITS, in_scope
from src.chunk.base import MAX_TOKENS, MIN_TOKENS
from src.chunk.chunkers import CHUNKERS
from src.eval.stats import LEVEL, RESAMPLES

PROJECT = Path(__file__).resolve().parents[2]
TAG, CHECKSUMS, OUTPUT = "paper-v1.2", "docs/paper_checksums.txt", "paper_ieee/generated"
CHECKSUMS_LOCK = "docs/paper_checksums_v1.3.txt"  # paper-v1.3 lock (spec v1.2, 2026-11-24): the inputs made after TAG
KEYS = ["parser", "setting", "doc_id", "question_id"]
DIGITS = dict(zip("0123456789", ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"]))
MARKS = ["*", "square*", "triangle*", "diamond*", "o", "square", "triangle"]
INPUTS = {
    "p4_final": "runs/P4-FINAL-20261106-1.json",
    "p4_primary": "data/results/p4/P4-FINAL-20261106-1_primary_setups.csv",
    "p4_primary_documents": "data/results/p4/P4-FINAL-20261106-1_primary_documents.csv",
    "p4_full": "data/results/p4/P4-FINAL-20261106-1_full_setups.csv",
    "p4_tuning_full": "data/results/p4/P4-LOCAL-20261105-1_full_setups.csv",
    "tuning_p4": "data/results/p4/P4-NOINDIAN-20261114-1_p4.csv",
    "held_out_no_indian": "data/results/p4/P4-FINAL-NOINDIAN-20261114-1_p4.csv",
    "size_tuning": "data/results/p3/size_by_source_P3-LOCAL-20261105-4.csv",
    "size_tuning_summary": "data/results/p3/size_by_source_summary_P3-LOCAL-20261105-4.csv",
    "size_final_summary": "data/results/p3/size_by_source_summary_P3-FINAL-20261106-1.csv",
    "fixedk": "data/results/p3/fixedk_tuning.csv",
    "rq5_chunker": "data/results/rq5/P5-LOCAL-20261110-2_chunker.csv",
    "rq5_digital": "data/results/rq5/P5-LOCAL-20261110-1_digital.csv",
    "rq5_scanned": "data/results/rq5/P5-LOCAL-20261111-1_scanned.csv",
    "aq_held_out": "data/results/aq/analysis_held_out.csv",
    "aq_held_out_vs_best": "data/results/aq/analysis_held_out_vs_best.csv",
    "aq_tuning_vs_best": "data/results/aq/analysis_tuning_vs_best.csv",
    "aq_scanned": "data/results/aq/analysis_scanned.csv",
    "aq_scanned_vs_best": "data/results/aq/analysis_scanned_vs_best.csv",
    "aq_f1": "data/results/aq/answers_f1.csv",
    "aq_judgements": "data/results/aq/judgements.jsonl",
    "judge_check": "data/results/aq/judge_check.csv",
    "judge_check_keys": "data/results/aq/judge_check_keys.csv",
    "scores_tuning": f"data/results/p3/{RECALL_RUNS['tuning']}.csv.gz",
    "scores_held_out": f"data/results/p3/{RECALL_RUNS['held_out']}.csv.gz",
    "gold_drop_tuning": "data/results/p3/gold_drop_tuning.csv",
    "gold_drop_final": "data/results/p3/gold_drop_final.csv",
    "split": "pdfs/split.csv",
    "retrievers": "data/results/supplementary-20261114/retriever_summary.csv",
    "compute": "data/results/supplementary-20261114/compute_summary.csv",
    "golden_labels": "data/results/golden_check/labels.csv",
    "golden_sample": "data/results/golden_check/sample.csv",
    "manual": "paper/data/manual_facts.csv",  # removed from the tree on 2026-11-20: read as tagged (TAGGED_INPUTS)
    "p3_final_record": "runs/P3-FINAL-20261106-1.json",
    "p4_tuning_record": "runs/P4-LOCAL-20261105-1.json",
    "p3_tuning_record": "runs/P3-LOCAL-20261105-4.json",
    "fixedk_record": "runs/P3-FIXEDK-20261112-1.json",
    "docling_record": "runs/P1-RQ5-KN01-20261109-4.json",  # the default variant; same pinned install as P1-KN06 (not checksummed)
    "pdfplumber_record": "runs/P1-LOCAL-20261106-1.json",
    "sanity_log": "runs/tests/test_p3_sanity_floor_damage.txt",
    "github_page1": "data/results/supplementary-20261114/github_activity_page1.json",
    "github_page2": "data/results/supplementary-20261114/github_activity_page2.json",
    "chunking_final_record": "runs/P2-P4-KN01-20261105-1.json",
    "aq_sample": "data/results/aq/sample.csv",
    # made after the tag (spec v1.2 "Extension result", "Robustness embedder result", "Held-out set 2: step 4 results")
    "h2_drop": "runs/P4-H2-20261124-1.json",
    "h2_sensitivity": "runs/P4-H2-20261124-2.json",
    "h2_certain": "runs/P4-H2-20261124-3.json",
    "h2_drop_setups": "data/results/p4/P4-H2-20261124-1_primary_setups.csv",
    "h2_sensitivity_setups": "data/results/p4/P4-H2-20261124-2_primary_setups.csv",
    "h2_certain_setups": "data/results/p4/P4-H2-20261124-3_primary_setups.csv",
    "h2_pooled": "data/results/h2/P4-H2-20261124-6_pooled.csv",
    "h2_rq2": "data/results/h2/P4-H2-20261124-7_rq2.csv",
    "h2_exclusion": "data/results/h2/P4-H2-20261124-5_exclusion.csv",
    "h2_exclusion_record": "runs/P4-H2-20261124-5.json",
    "ext_rq1": "data/results/ext/P4-EXT-20261119-2_rq1.csv",
    "rob_rq1": "data/results/rob/P4-ROB-20261120-1_rq1.csv",
}
TAGGED_INPUTS = {"manual", "split"}  # removed or extended (held-out 2 rows) since the tag: read with git show <TAG>:<path>, checked against the tagged checksum file
AFTER_TAG = {key for key in INPUTS if key.startswith(("h2_", "ext_", "rob_"))}  # checked against CHECKSUMS_LOCK
H2_SETS = {"h2_drop": "Drop rule", "h2_sensitivity": "Sensitivity", "h2_certain": "Certain-only"}  # gold variants, spec v1.2
# The tag freezes the result files (through the checksum file), the checksum file, the spec and the study code the
# generator imports constants from. After the tag, src/ gained new chunkers (extension, agent): additions are allowed,
# but no line of these files may be removed or changed since the tag. Paper code may change without a re-tag.
CODE_AT_TAG = ["src/chunk/base.py", "src/chunk/chunkers.py", "src/eval/stats.py", "scripts/p4_analyse.py", "scripts/aq_run.py",
               "scripts/golden_check.py", "scripts/p3_fixedk.py"]
SPEC = "spec/spec_v1.2.md"  # read as tagged (git show <TAG>:spec/spec_v1.2.md), so its content is fixed by the tag
# Deviations, corrections and disclosures recorded in the spec: each row is anchored to spec lines (a heading is matched as
# the whole line, other anchors as part of one line); the first anchor that carries a date dates the row. The selection
# and the one-line summaries are the paper's; the generator refuses a row whose anchors are not each on exactly one line.
DEVIATIONS = [
    ("deviation", ["Written on 2026-11-03, before any new document is opened.", "Deviation note: 12 of its 13 documents"],
     "Tree structure of most H1 held-out documents seen while designing the tree method (no questions, answers or scores)."),
    ("deviation", ["- A13 (2026-11-04, after the first dev scores"],
     "Line blocks for pdfplumber added to the tree method after the first development scores; the earlier version is kept."),
    ("deviation", ["- S14 floor, result and amendment (2026-11-05)"],
     "Floor test failed under the pre-written rule; rule amended to paired differences; both results reported."),
    ("deviation", ["- S10 amendment (2026-11-05, before any P4 result)"],
     "Tie rule changed to paired per-document differences, before any RQ1 result."),
    ("deviation", ["## Research question added 2026-11-05 (scope and method decided after P3 is complete)"],
     "RQ5 added after the tuning scores were complete."),
    ("deviation", ["## Grid extension after the first official run (2026-11-05)"],
     "Chunk-size grid extended after the tuning results were seen (tuning-only work)."),
    ("deviation", ["## Method 1 v1.2: A9 cap on the whole prefix (2026-11-05)"],
     "Prefix-cap fault in the tree method fixed; prefix settings re-made; the old outputs kept as superseded."),
    ("deviation", ["## P4 analysis rules, amended after the first dev run (2026-11-05)"],
     "RQ1 rules amended after the tuning development run: split-half oracle; cost no longer breaks ties."),
    ("correction", ["- Correction (2026-11-06): H1 = held_out (11) + held_out_hindi (2)."],
     "Held-out H1 count corrected: the Hindi pair is part of it."),
    ("deviation", ["- P4-KN01 (2026-11-06): 49 of 50 settings complete"],
     "Semantic chunker left out of the held-out evaluation (out of GPU memory)."),
    ("deviation", ["## Held-out gold (2026-11-06), made before any held-out scoring", "After scoring, p4_analyse got a --settings option"],
     "An option naming the pre-registered primary choice set added after held-out scoring; analysis functions unchanged."),
    ("deviation", ["- Correction before running (2026-11-08)"],
     "RQ5(a) table-mode variant redefined before running."),
    ("deviation", ["## RQ5(a) result (2026-11-10)", "- replace_broken_text not run"],
     "One planned RQ5(a) parser variant not run: the option does not exist for the default OCR engine."),
    ("deviation", ["## RQ5(b) design, written before the analysis (2026-11-10)", "Specified after the held-out scores existed (disclosed)"],
     "RQ5(b) specified after the RQ1 held-out scores existed: second use of the held-out set."),
    ("deviation", ["## Answer-quality check (AQ), design frozen before running (2026-11-10)", "Uses the held-out set a third time"],
     "Answer-quality check (RQ4) added: third use of the held-out set."),
    ("correction", ["## Correction to RQ5(a) scanned results (2026-11-11)"],
     "Scanned answer lists were stored as characters; the scanned RQ5(a) result withdrawn and recomputed."),
    ("deviation", ["- AQ judge amendment (2026-11-11)"], "Answer judge replaced by an open-weight model."),
    ("deviation", ["- AQ judge amendment (2026-11-11)", "same 40-case human check with the 80% pass mark and kappa."],
     "AQ human check extended from 20 to 40 cases, first in code that judged with the answering model; no note gives a "
     "reason (the 40 cases were drawn as one sample). The judge amendment was first committed with the check's result."),
    ("deviation", ["- AQ judge check (2026-11-12)"],
     "The judge failed its human check; a second, non-blind pass; the judge kept as a secondary measure only."),
    ("deviation", ["## RQ5(a) scanned variants: two variants are copies of the default (correction, 2026-11-12)"],
     "Two scanned OCR variants identical to the default; removed from the comparison family."),
    ("deviation", ["## Scope: Hindi (decision, 2026-11-12)"],
     "Hindi track not evaluated (no question source); no multilingual claim."),
    ("correction", ["## Errata (2026-11-12)"], "Errata: Holm p bounds, a wrong duplicate claim, superseded scanned numbers."),
    ("correction", ["## Errata (2026-11-14)"], "Erratum: the digital sample size in RQ5(a)."),
    ("correction", ["## Errata (2026-11-14, fixed-k)"], "Erratum: the fixed-k winners included superseded settings."),
    ("deviation", ["## Supplementary analyses for the paper (2026-11-14), read-only, descriptive",
                   "The 1,661 earlier answers come from the unpaced code"],
     "Most answer-quality answers were made by an earlier code version and have no run record."),
    ("deviation", ["## GOLDEN_200 validity check stopped after batch 1 (2026-11-14), deviation"],
     "Validity check of the Indian questions stopped after its first batch; planned expansion and reason review not done."),
    ("disclosure", ["## AQ judge check: first-pass labels overwritten in place (reporting, added 2026-11-14)"],
     "First-pass judge-check labels were overwritten; the recorded first-pass agreement cannot be recomputed."),
]
LATER_DISCLOSURES = [  # recorded after the tag: anchored to the working spec, same rules
    ("disclosure", ["## RQ2 on tuning is descriptive (disclosure, 2026-11-25)"],
     "RQ2 on tuning was defined after the tuning scores (2026-11-12) and is descriptive (per source, all in-scope settings, "
     "no test); the confirmatory RQ2 rule (13 primary setups, intervals, every rho negative) was fixed before held-out "
     "set 2 and is tested only there."),
]
SIZE_FAMILIES = {"fixed_token": r"fixed_token_size(\d+)_overlap0_noprefix", "recursive": r"recursive_size(\d+)_overlap0_noprefix",
                 "langchain_recursive": r"langchain_recursive_size(\d+)_overlap0_noprefix", "method1_tree": r"method1_tree_T(\d+)_noprefix"}
IST = timezone(timedelta(hours=5, minutes=30))  # the timeline (Appendix A3) reports Indian Standard Time
SPEC_COMMITS = {"DateSpecVone": ("607d29c", "spec/spec_v1.md"), "DateSpecVoneOne": ("de4aff3", "spec/spec_v1.1.md"),
                "DateSpecVoneTwo": ("b1bd7d1", "spec/spec_v1.2.md")}  # the commit that first adds each spec file
LOCK_TAG = "paper-v1.3.1"  # freezes the files made after TAG
DROP_RULE = "configs/gold_drop_rule.json"
CHEAPEST_TIE_RUN = "runs/tests/dev_p4_v1_cheapest_tie_rule_P4-LOCAL-20261105-1.json"
SCORER_TAG, SCORER_COMMIT = "scorer_v1", "448173c"


class Inputs:
    """Read access to the verified inputs by key, relative to a project root."""

    def __init__(self, root):
        self.root = Path(root)

    def path(self, key):
        return self.root / INPUTS[key]

    def raw(self, key):
        """The input's bytes: from the paper tag for TAGGED_INPUTS, else from the working copy."""
        if key in TAGGED_INPUTS:
            return subprocess.run(["git", "-C", str(self.root), "show", f"{TAG}:{INPUTS[key]}"], capture_output=True, check=True).stdout
        return self.path(key).read_bytes()

    def csv(self, key, **options):
        return pd.read_csv(io.BytesIO(self.raw(key)) if key in TAGGED_INPUTS else self.path(key), **options)

    def text(self, key):
        return self.raw(key).decode("utf-8")

    def json(self, key):
        return json.loads(self.path(key).read_text(encoding="utf-8"))

    def jsonl(self, key):
        return pd.DataFrame([json.loads(line) for line in self.path(key).read_text(encoding="utf-8").splitlines()])

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True, check=True).stdout.strip()

    def commit_time(self, commit):
        """Commit time of a commit (its hash fixes its content, so git is its own checksum)."""
        return datetime.fromisoformat(self.git("show", "-s", "--format=%cI", commit))

    def added_in(self, path):
        """The commit that first added a file."""
        return self.git("log", "--diff-filter=A", "--format=%h", "--", path).splitlines()[-1]

    def tag_commit(self, tag):
        return self.git("rev-parse", "--short", f"{tag}^{{commit}}")

    def tagged_file(self, path):
        """A tracked file as it is at the paper tag."""
        return self.git("show", f"{TAG}:{path}")

    def changed_since_tag(self, paths):
        """Files whose diff against the paper tag removes or changes a line (pure additions are allowed), and paths
        that are missing."""
        diff = self.git("diff", "--unified=0", TAG, "--", *paths)
        edited = [re.search(r"a/(\S+)", part).group(1) for part in diff.split("diff --git ")[1:]
                  if any(line.startswith("-") and not line.startswith("---") for line in part.splitlines())]
        return edited + [f"{path} (missing)" for path in paths if not (self.root / path).exists()]


# --- checks -------------------------------------------------------------------------------------------------------

def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def listed_checksums(text):
    """path -> SHA-256 from a sha256sum file; comment and blank lines skipped."""
    entries = [line.split(maxsplit=1) for line in text.splitlines() if line.strip() and not line.startswith("#")]
    return {path.lstrip("*").strip(): digest for digest, path in entries}


def verify(root, keys, tag_check=True):
    """Exit with every problem listed if an input is not in its checksum file, is missing, or differs from it: inputs
    frozen at TAG against CHECKSUMS as tagged, inputs made after it (AFTER_TAG) against CHECKSUMS_LOCK."""
    read = Inputs(root)
    listing = read.git("show", f"{TAG}:{CHECKSUMS}") if tag_check else (Path(root) / CHECKSUMS).read_text(encoding="utf-8")
    lists = {CHECKSUMS: listed_checksums(listing),
             CHECKSUMS_LOCK: listed_checksums((Path(root) / CHECKSUMS_LOCK).read_text(encoding="utf-8"))}
    problems = []
    for key in sorted(keys):
        relative, checksums = INPUTS[key], CHECKSUMS_LOCK if key in AFTER_TAG else CHECKSUMS
        listed = lists[checksums]
        if relative not in listed:
            problems.append(f"not in {checksums}: {relative}")
        elif not (key in TAGGED_INPUTS or read.path(key).exists()):
            problems.append(f"missing: {relative}")
        elif (actual := hashlib.sha256(read.raw(key)).hexdigest()) != listed[relative]:
            problems.append(f"checksum mismatch: {relative}\n  listed {listed[relative]}\n  actual {actual}")
    if problems:
        raise SystemExit("inputs failed verification; nothing written:\n" + "\n".join(problems))


def check_tag(root):
    """The paper tag (TAG) must exist with its checksum file; every entry listed there must still be listed unchanged
    in the working copy, except files removed from the tree, which are read as tagged (TAGGED_INPUTS)."""
    try:
        tagged = subprocess.run(["git", "-C", str(root), "show", f"{TAG}:{CHECKSUMS}"], capture_output=True, check=True, text=True).stdout
    except subprocess.CalledProcessError:
        raise SystemExit(f"tag {TAG} (with {CHECKSUMS}) not found: results are not frozen yet; nothing run")
    current = listed_checksums((Path(root) / CHECKSUMS).read_text(encoding="utf-8"))
    tagged_only = {INPUTS[key] for key in TAGGED_INPUTS}
    changed = [path for path, digest in listed_checksums(tagged).items() if path not in tagged_only and current.get(path) != digest]
    if changed:
        raise SystemExit(f"{CHECKSUMS} changed since {TAG} for: {changed}; nothing run")


# --- formatting ---------------------------------------------------------------------------------------------------

def fixed(value, places=3):
    text = f"{value:.{places}f}"
    return f"$-${text[1:]}" if text.startswith("-") else text


def signed(value, places=3):
    """A difference or gap with its sign always shown: '+0.001', '$-$0.007'."""
    text = fixed(value, places)
    return text if text.startswith("$-$") else f"+{text}"


def interval(low, high, places=3):
    return f"[{fixed(low, places)}, {fixed(high, places)}]"


def holm_text(holm_p, comparisons):
    """A Holm p of 0 means no resample crossed zero: report the bound 2 / RESAMPLES x comparisons, rounded up."""
    if holm_p > 0:
        return fixed(holm_p)
    return f"$<${math.ceil(2 / RESAMPLES * comparisons * 100) / 100:.2f}"


def escape(text):
    return str(text).replace("\\", r"\textbackslash{}").replace("_", r"\_").replace("%", r"\%").replace("&", r"\&")


def setup_name(setup):
    """'pdfplumber/method1_tree_T384_noprefix' -> 'pdfplumber / method1\\_tree T384' (LaTeX)."""
    parser, setting = setup.split("/", 1) if "/" in setup else ("", setup)
    for old, new in (("_overlap0", ""), ("_noprefix", ""), ("_size", " "), ("_sentences", " "), ("_T", " T"), ("_prefix", " prefix")):
        setting = setting.replace(old, new)
    return escape(f"{parser} / {setting}" if parser else setting)


FAMILIES = [("langchain_recursive", "LC"), ("langchain_default", "LC-def"), ("method1_tree", "M1"), ("fixed_token", "FT"),
            ("recursive", "Rec"), ("sentence", "Sent"), ("semantic", "Sem"), ("llm_regex", "LLM"),
            ("page", "Page")]  # longer names first: langchain_recursive before recursive
PARSERS = {"docling": "D", "pdfplumber": "P"}
DISPLAY = {"held_out": "Held-out", "tuning": "Tuning", "bm25": "BM25", "dense": "Dense", "hybrid": "Hybrid",
           "primary": "Primary", "full": "Full", "original": "Original", "study": "Study runs", "tests": "Test runs",
           "docling": "Docling", "pdfplumber": "pdfplumber"}


def display(code):
    """The label a table shows for a code name (split, retriever, choice set, parser, run group)."""
    return DISPLAY.get(code, escape(code))
KEY = {}  # short code -> (kind, full name); filled while building, written as the appendix key table
KINDS = {"parser": "Parsers", "family": "Chunker families", "setting": "Chunker settings", "docling setting": "Docling settings",
         "pdfplumber setting": "pdfplumber settings", "document": "Documents"}  # key groups, in this order


def register(name, kind, full):
    if KEY.get(name, (kind, full)) != (kind, full):
        raise ValueError(f"short name {name} would stand for both {KEY[name][1]} and {full}")
    KEY[name] = (kind, full)
    return escape(name)


def short(setup):
    """The one short-name scheme of every table and figure: parser letter / setting code, the code being the family
    code and size, '+p' for the heading prefix, 'o<n>' for an overlap: 'pdfplumber/method1_tree_T384_noprefix' ->
    'P/M1-384'. The key lists the parser letters and the setting codes once each."""
    parser, setting = setup.split("/", 1) if "/" in setup else ("", setup)
    family, code = next((family, code) for family, code in FAMILIES if setting.startswith(family))
    rest = setting[len(family):]
    size, overlap, run = (re.search(pattern, rest) for pattern in (r"(?:_size|_T|_sentences)(\d+)", r"_overlap(\d+)", r"_run(\d+)"))
    text = (code + (f"-{size.group(1)}" if size else "") + (f"o{overlap.group(1)}" if overlap and overlap.group(1) != "0" else "")
            + (f"-r{run.group(1)}" if run else "") + ("+p" if rest.endswith("_prefix") else ""))
    code = register(text, "setting", setting)
    return f"{PARSERS[parser]}/{code}" if parser else code


def short_family(family, parser):
    """A chunker family on one parser (RQ5 rows): 'langchain_recursive', 'docling' -> 'D/LC'."""
    return f"{PARSERS[parser]}/{register(dict(FAMILIES)[family], 'family', family)}"


def short_variant(variant):
    """A parser setting (RQ5 rows): 'docling_ocr_off' -> 'D/ocr off'."""
    parser, rest = variant.split("_", 1)
    return f"{PARSERS[parser]}/{register(rest.replace('_', ' '), f'{parser} setting', rest)}"


def short_document(doc):
    """A GOLDEN_200 document by the study's label: 'indian_d3_fundamental_rules' -> 'D3' (scripts.golden_check.DOCS)."""
    return register(GOLDEN_DOCS[doc].split("_")[0], "document", doc)


PLACEHOLDERS = ["n", "m"]


def setting_pattern(code, full):
    """A chunker setting's code and full name with their shared numbers replaced by placeholders, e.g. ('Rec-256o64',
    'recursive_size256_overlap64_noprefix') -> ('Rec-{n}o{m}', 'recursive_size{n}_overlap{m}_noprefix'). Numbers inside the
    family code or name (M1, method1) are not placeholders; the numbers must match in order, or the pattern is refused."""
    family, family_code = next((family, family_code) for family, family_code in FAMILIES if full.startswith(family))
    code_rest, full_rest = code[len(family_code):], full[len(family):]
    values = re.findall(r"\d+", code_rest)
    for placeholder, value in zip(PLACEHOLDERS, values):
        code_rest, found = re.subn(rf"(?<!\d){value}(?!\d)", "{" + placeholder + "}", code_rest, count=1)
        full_rest, matched = re.subn(rf"(?<!\d){value}(?!\d)", "{" + placeholder + "}", full_rest, count=1)
        if not (found and matched):
            raise ValueError(f"short code {code} and full name {full} do not share their numbers")
    return family_code + code_rest, family + full_rest


def with_placeholders(text, code):
    """LaTeX for a pattern: placeholders in math italics, the rest as plain (code=False) or typewriter (code=True) text."""
    pieces = re.split(r"\{([nm])\}", text)
    return "".join(f"${piece}$" if index % 2 else ((r"\texttt{" + escape(piece) + "}") if code and piece else escape(piece))
                   for index, piece in enumerate(pieces))


def key_table():
    """Appendix key: every short name used in a table or figure, grouped by kind, with what it stands for. Chunker
    settings are listed once per naming pattern (n, m: the numbers in the name), since the full grid lists every setting."""
    patterns = sorted({setting_pattern(name, full) for name, (kind, full) in KEY.items() if kind == "setting"})
    named = [(name, (kind, full)) for name, (kind, full) in sorted(KEY.items()) if kind != "setting"]
    rows = {"setting": [[with_placeholders(code, False), with_placeholders(full, True)] for code, full in patterns]}
    entries = [(letter, ("parser", parser)) for parser, letter in PARSERS.items()] + named
    groups = {label: rows.get(each) or [[escape(name), "\\texttt{" + escape(full) + "}"] for name, (kind, full) in entries if kind == each]
              for each, label in KINDS.items()}
    unknown = {kind for name, (kind, full) in entries} - set(KINDS)
    if unknown:
        raise ValueError(f"short-name kinds without a key group: {sorted(unknown)}")
    return grouped_tabular("ll", ["Short", "Full name"], {label: rows for label, rows in groups.items() if rows})


def letters(text):
    """A LaTeX-safe macro part: digits spelled out, other characters dropped, words capitalised."""
    words = re.split(r"[^A-Za-z0-9]+", "".join(f" {DIGITS[char]} " if char.isdigit() else char for char in str(text)))
    return "".join(word[:1].upper() + word[1:] for word in words if word)


def macro(name, value, source=""):
    if not re.fullmatch(r"[A-Za-z]+", name):
        raise ValueError(f"macro name must be letters only: {name}")
    value = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "{,}", str(value))  # 1{,}250: no space after the comma in math mode
    return f"\\newcommand{{\\{name}}}{{{value}}}" + (f"  % {source}" if source else "")


def tabular(columns, header, rows):
    lines = [f"\\begin{{tabular}}{{{columns}}}", r"\toprule", " & ".join(header) + r" \\", r"\midrule"]
    lines += [" & ".join(str(cell) for cell in row) + r" \\" for row in rows]
    return "\n".join(lines + [r"\bottomrule", r"\end{tabular}", ""])


def grouped_tabular(columns, header, groups):
    """A table whose rows sit under group subheadings (an italic row across all columns) instead of a group column."""
    width = len(header)
    lines = [f"\\begin{{tabular}}{{{columns}}}", r"\toprule", " & ".join(header) + r" \\"]
    for group, rows in groups.items():
        lines += [r"\midrule", f"\\multicolumn{{{width}}}{{l}}{{\\emph{{{group}}}}}" + r" \\"]
        lines += [" & ".join(str(cell) for cell in row) + r" \\" for row in rows]
    return "\n".join(lines + [r"\bottomrule", r"\end{tabular}", ""])


def coordinates(points, x_places=1, y_places=3):
    return " ".join(f"({x:.{x_places}f},{y:.{y_places}f})" if not isinstance(x, str) else f"({x},{y:.{y_places}f})"
                    for x, y in points)


# --- builders: each returns ({generated path: text}, {macro name: (value, source)}) --------------------------------

def primary_choice_set(setups):
    """RQ1's primary choice set from its setup names (parser/setting): the number of settings, which must be the same
    on every parser, the sizes of the size-based settings, and the sentence-window length."""
    by_parser = pd.Series(list(setups)).str.split("/", expand=True).groupby(0)[1].apply(frozenset)
    if by_parser.nunique() != 1:
        raise ValueError("the primary choice set differs between parsers")
    settings = sorted(by_parser.iloc[0])
    sizes = sorted({int(size) for name in settings for size in re.findall(r"(?:size|_T)(\d+)", name)})
    windows = sorted({int(window) for name in settings for window in re.findall(r"sentences(\d+)", name)})
    if len(windows) != 1:
        raise ValueError("the primary choice set should hold exactly one sentence-window length")
    source = INPUTS["p4_primary"]
    return {"RQonePrimarySettings": (len(settings), source),
            "RQonePrimarySizes": (", ".join(map(str, sizes[:-1])) + f" and {sizes[-1]}", source),
            "RQonePrimarySentenceWindow": (windows[0], source)}


def rq1(read):
    record = read.json("p4_final")["stack"]["summary"]
    setups = read.csv("p4_primary", index_col=0)
    tuning = read.csv("tuning_p4")
    winner = tuning[(tuning["variant"] == "all tuning") & (tuning["scope"] == "primary")]["best_single"].iloc[0]
    rank = setups["recall"].rank(ascending=False, method="min")
    rows, numbers = [], primary_choice_set(setups.index)
    if record["primary"]["setups"] != len(setups):
        raise ValueError("P4 record and primary setup table disagree on the number of setups")
    for scope in ("primary", "full", "original"):
        summary = record[scope]
        low, high = summary["gap_interval"]
        if (summary["documents"], summary["questions"]) != (record["primary"]["documents"], record["primary"]["questions"]):
            raise ValueError("RQ1 table assumes the same documents and questions in every choice set (shown in the caption)")
        rows.append([display(scope), summary["setups"], short(summary["best_single"]),
                     fixed(summary["best_single_recall"]), summary["tied_with_best"], fixed(summary["oracle"]),
                     f"{signed(summary['gap'])} {interval(low, high)}", "GO" if low > 0 else "NO-GO"])
        name = letters(scope)
        numbers |= {f"RQone{name}Gap": (signed(summary["gap"]), INPUTS["p4_final"]),
                    f"RQone{name}GapCI": (interval(low, high), INPUTS["p4_final"])}
    primary = record["primary"]
    numbers |= {name: (value, INPUTS["p4_final"]) for name, value in {
        "RQoneSetups": primary["setups"], "RQoneDocuments": primary["documents"], "RQoneQuestions": primary["questions"],
        "RQoneBest": setup_name(primary["best_single"]), "RQoneBestRecall": fixed(primary["best_single_recall"]),
        "RQoneTied": primary["tied_with_best"], "RQoneOracle": fixed(primary["oracle"]), "RQoneRawGap": signed(primary["raw_gap"]),
        "RQoneDecision": "GO" if primary["gap_interval"][0] > 0 else "NO-GO"}.items()}
    numbers |= {"RQoneTuningWinner": (setup_name(winner), INPUTS["tuning_p4"]),
                "RQoneTuningWinnerRecall": (fixed(setups.loc[winner, "recall"]), INPUTS["p4_primary"]),
                "RQoneTuningWinnerRank": (int(rank[winner]), INPUTS["p4_primary"]),
                "RQoneTuningWinnerTied": ("tied" if setups.loc[winner, "tied_with_best"] else "not tied", INPUTS["p4_primary"])}
    h2_rows, h2_numbers = rq1_held_out_2(read, winner)
    header = ["Choice set", "Setups", "Best single", "Recall", "Tied", "Oracle", r"Gap [95\%]", "Rule"]
    groups = {f"Held-out set~1: {primary['documents']} documents, {primary['questions']} questions": rows} | h2_rows
    return {"tables/rq1.tex": grouped_tabular("lrlrrrll", header, groups)}, numbers | h2_numbers


def rq1_held_out_2(read, winner):
    """Held-out 2 rows of the RQ1 table (primary choice set, one row per gold variant, from the p4_analyse records)
    and the pooled secondary row (oracle minus the tuning winner, h2_analyse), with their macros."""
    rows, numbers = [], {}
    for key, label in H2_SETS.items():
        summary, source = read.json(key)["stack"]["summary"]["primary"], INPUTS[key]
        setups = read.csv(f"{key}_setups", index_col=0)
        if summary["setups"] != len(setups):
            raise ValueError(f"{key}: record and primary setup table disagree on the number of setups")
        low, high = summary["gap_interval"]
        rows.append([f"{label}, {summary['documents']} / {summary['questions']}", summary["setups"], short(summary["best_single"]),
                     fixed(summary["best_single_recall"]), summary["tied_with_best"], fixed(summary["oracle"]),
                     f"{signed(summary['gap'])} {interval(low, high)}", "GO" if low > 0 else "NO-GO"])
        rank = setups["recall"].rank(ascending=False, method="min")
        name = f"RQoneHTwo{letters(label)}"
        numbers |= {f"{name}{part}": (value, source) for part, value in {
            "Documents": summary["documents"], "Questions": summary["questions"], "Best": setup_name(summary["best_single"]),
            "BestRecall": fixed(summary["best_single_recall"]), "Tied": summary["tied_with_best"],
            "Oracle": fixed(summary["oracle"]), "Gap": signed(summary["gap"]), "GapCI": interval(low, high),
            "Decision": "GO" if low > 0 else "NO-GO"}.items()}
        numbers |= {f"{name}TuningWinnerRecall": (fixed(setups.loc[winner, "recall"]), INPUTS[f"{key}_setups"]),
                    f"{name}TuningWinnerRank": (int(rank[winner]), INPUTS[f"{key}_setups"]),
                    f"{name}TuningWinnerTied": ("tied" if setups.loc[winner, "tied_with_best"] else "not tied", INPUTS[f"{key}_setups"])}
    pooled, source = read.csv("h2_pooled").iloc[0], INPUTS["h2_pooled"]
    decision = "GO" if pooled["gap_low"] > 0 else "NO-GO"
    if decision != pooled["decision_secondary"]:
        raise ValueError("pooled decision disagrees with its interval")
    pooled_row = [f"Pooled$^\\dagger$, {pooled['documents']} / {pooled['questions']}", len(read.csv("h2_drop_setups")),
                  f"{short(winner)} (fixed)", fixed(pooled["tuning_winner"]), "--", fixed(pooled["oracle"]),
                  f"{signed(pooled['gap_oracle_minus_tuning_winner'])} {interval(pooled['gap_low'], pooled['gap_high'])}",
                  f"{decision}$^\\dagger$"]
    numbers |= {f"RQonePooled{part}": (value, source) for part, value in {
        "Documents": pooled["documents"], "Questions": pooled["questions"], "TuningWinnerRecall": fixed(pooled["tuning_winner"]),
        "Oracle": fixed(pooled["oracle"]), "Gap": signed(pooled["gap_oracle_minus_tuning_winner"]),
        "GapCI": interval(pooled["gap_low"], pooled["gap_high"]), "Decision": decision}.items()}
    return {"Held-out set~2 (ViDoRe V3), primary choice set": rows, "Pooled, secondary": [pooled_row]}, numbers


def hr_check(read):
    """Held-out 2 HR-page check (drop-rule primary gold, the step's own bootstrap): the gap with all questions and
    without the common-set questions on the HR pages whose image and PDF page shapes differ (h2_analyse exclusion)."""
    stack, frame = read.json("h2_exclusion_record")["stack"], read.csv("h2_exclusion").set_index("questions_set")
    if stack["scores_run"] != read.json("h2_drop")["stack"]["scores_run"] or len(frame) != 2:
        raise ValueError("HR check is not the two-row check on the drop-rule primary scores")
    source, record = INPUTS["h2_exclusion"], INPUTS["h2_exclusion_record"]
    numbers = {"RQoneHRCheckPages": (stack["pages_over_limit"], record),
               "RQoneHRCheckExcludedQuestions": (stack["common_set_questions_excluded"], record)}
    for label, row in zip(("With", "Without"), (frame.loc["all"], frame.drop("all").iloc[0])):
        numbers |= {f"RQoneHRCheck{label}{part}": (value, source) for part, value in {
            "Questions": row["questions"], "Gap": signed(row["gap"]), "GapCI": interval(row["gap_low"], row["gap_high"]),
            "Decision": row["decision"]}.items()}
    if numbers["RQoneHRCheckWithQuestions"][0] - numbers["RQoneHRCheckWithoutQuestions"][0] != stack["common_set_questions_excluded"]:
        raise ValueError("HR check: excluded question count disagrees with the two rows")
    return {}, numbers


def rq2_held_out_2(read):
    """RQ2 on held-out 2: Spearman of measured size against recall per gold variant, parser and budget (all corpora
    together), with the document-bootstrap interval; the gold variant of each scores run comes from its P4 record."""
    frame = read.csv("h2_rq2")
    frame = frame[frame["corpus"] == "all"]
    variants = {read.json(key)["stack"]["scores_run"]: label for key, label in H2_SETS.items()}
    if set(frame["scores_run"]) != set(variants):
        raise ValueError("RQ2 held-out 2 scores runs differ from the P4 records")
    budgets = sorted(frame["budget"].unique())
    cell = {(row.scores_run, row.parser, row.budget): row for row in frame.itertuples(index=False)}
    rows, numbers, source = [], {}, INPUTS["h2_rq2"]
    for run, label in variants.items():
        for index, parser in enumerate(sorted(frame["parser"].unique())):
            values = [cell[(run, parser, budget)] for budget in budgets]
            rows.append([label if index == 0 else "", PARSERS[parser]]
                        + [f"{fixed(value.spearman)} {interval(value.low, value.high)}" for value in values])
            numbers |= {f"RQtwoHTwo{letters(label)}{letters(parser)}{letters(budget)}": (fixed(value.spearman), source) for budget, value in zip(budgets, values)}
    largest = frame[frame["budget"] == budgets[-1]]
    numbers |= {"RQtwoHTwoNegative": (int((frame["spearman"] < 0).sum()), source), "RQtwoHTwoValues": (len(frame), source),
                "RQtwoHTwoLargestBudgetIncludeZero": (int(((largest["low"] <= 0) & (largest["high"] >= 0)).sum()), source),
                "RQtwoHTwoLargestBudgetValues": (len(largest), source), "RQtwoHTwoSetupsPerParser": (int(frame["setups"].iloc[0]), source)}
    header = ["Gold", "Parser"] + [f"{budget:,}" for budget in budgets]
    return {"tables/rq2_h2.tex": tabular("ll" + "l" * len(budgets), header, rows)}, numbers


def robustness(read):
    """RQ1 robustness rows: held-out 1 with one retriever only and without the Indian documents, and the tuning-only
    extension (32 setups) and second-embedder (nomic) checks; each row's gap is oracle minus best single."""
    retrievers = read.csv("retrievers").query("split == 'held_out' and scope == 'primary'").set_index("retriever")
    no_indian = read.csv("held_out_no_indian").query("variant == 'without Indian' and scope == 'primary'").iloc[0]
    extension = read.csv("ext_rq1").query("variant == 'all' and scope == 'primary + new'").iloc[0]
    nomic = read.csv("rob_rq1").query("embedder == 'nomic'").set_index(["variant", "retriever"])
    cases = [(f"{display(name)} only", "held-out 1", retrievers.loc[name], "retrievers") for name in ("bm25", "dense")]
    cases += [("Without Indian", "held-out 1", no_indian, "held_out_no_indian"),
              (f"Grid + 6 chunkers ({extension['setups']})", "tuning", extension, "ext_rq1")]
    cases += [(f"nomic, {retriever}" + (", w/o Indian" if variant == "without Indian" else ""), "tuning",
               nomic.loc[(variant, retriever)], "rob_rq1")
              for variant, retriever in (("all tuning", "hybrid"), ("all tuning", "dense"), ("without Indian", "hybrid"))]
    rows, numbers = [], {}
    for label, split, row, key in cases:
        rows.append([label, split.replace("held-out 1", "held-out set 1"), f"{signed(row['gap'])} {interval(row['gap_low'], row['gap_high'])}",
                     "GO" if row["gap_low"] > 0 else "NO-GO"])
        name = f"Rob{letters(label)}{letters(split)}"
        numbers |= {f"{name}Gap": (signed(row["gap"]), INPUTS[key]), f"{name}GapCI": (interval(row["gap_low"], row["gap_high"]), INPUTS[key])}
    return {"tables/ext_rob.tex": tabular("llll", ["Check", "Split", r"Gap [95\%]", "Rule"], rows)}, numbers


def rq2(read):
    size = read.csv("size_tuning")
    size = size[size["budget"] == 1250]
    plots = []
    for parser in ("docling", "pdfplumber"):
        part = size[size["parser"] == parser]
        plots.append(f"\\nextgroupplot[title={{{parser.capitalize()} ({PARSERS[parser]})}}]")
        for index, (source, group) in enumerate(part.groupby("source")):
            points = group.sort_values(["chunk_size", "setting"])[["chunk_size", "recall"]].itertuples(index=False)
            plots.append(f"\\addplot+[only marks, mark={MARKS[index % len(MARKS)]}] coordinates {{{coordinates(points)}}};")
            if parser == "pdfplumber":  # the legend sits under the lower panel
                plots.append(f"\\addlegendentry{{{escape(source)}}}")
    figure = "\n".join([r"\begin{tikzpicture}",
                        r"\begin{groupplot}[group style={group size=1 by 2, vertical sep=2.2cm}, scale only axis,"
                        r" width=\columnwidth-2.6cm, height=4cm, xlabel={Mean chunk size (tokens)}, ylabel={Recall@1,250},"
                        r" legend style={at={(0.5,-0.42)}, anchor=north, legend columns=-1,"
                        r" /tikz/every even column/.append style={column sep=0.3cm}}]", *plots, r"\end{groupplot}", r"\end{tikzpicture}", ""])
    tuning, final = read.csv("size_tuning_summary"), read.csv("size_final_summary")
    ohr = final[final["source"] == "OHR-Bench"]
    numbers = {"RQtwoRhoRange": (f"{fixed(tuning['spearman_size_recall'].max(), 2)} to {fixed(tuning['spearman_size_recall'].min(), 2)}", INPUTS["size_tuning_summary"]),
               "RQtwoBestSizes": (f"{tuning['best_size'].min()}--{tuning['best_size'].max()}", INPUTS["size_tuning_summary"]),
               "RQtwoHeldOutOHRRhoRange": (f"{fixed(ohr['spearman_size_recall'].max(), 2)} to {fixed(ohr['spearman_size_recall'].min(), 2)}", INPUTS["size_final_summary"]),
               "RQtwoHeldOutOHRBestSizes": (f"{ohr['best_size'].min()}--{ohr['best_size'].max()}", INPUTS["size_final_summary"])}
    return {"figures/rq2.tex": figure}, numbers


def fixedk_tables(frame):
    """Per parser: settings x (chunk tokens, measures), document means then setting means, as p3_fixedk prints."""
    return {parser: part.groupby(["setting", "doc_id"])[["chunk_tokens"] + MEASURES].mean().astype(float).groupby("setting").mean()
            for parser, part in frame.groupby("parser")}


def rq3(read):
    frame = read.csv("fixedk", usecols=["parser", "setting", "doc_id", "chunk_tokens"] + MEASURES)
    kept = in_scope(frame["setting"].unique())  # spec Errata 2026-11-14 (fixed-k): superseded *_vNN and sanity left out
    labels = {"recall5": "R@5", "recall10": "R@10", "hit1": "Hit@1", "mrr": "MRR", MEASURES[-1]: f"R@{MEASURES[-1][6:]}"}
    numbers = {"RQthreeSettingsKept": (len(kept), INPUTS["fixedk"]),
               "RQthreeSettingsLeftOut": (frame["setting"].nunique() - len(kept), INPUTS["fixedk"])}
    for parser, table in fixedk_tables(frame[frame["setting"].isin(kept)]).items():
        details = best_sizes(table)[1]
        details = details.rename(columns={"best setting": "best", "chunk tokens": "tokens"})
        for row in details[details["scope"] == "all settings"].itertuples(index=False):
            name = f"RQthree{letters(parser)}{letters(row.measure)}"
            numbers |= {f"{name}Best": (setup_name(row.best), INPUTS["fixedk"]), f"{name}Score": (fixed(row.score), INPUTS["fixedk"]),
                        f"{name}Size": (row.tokens, INPUTS["fixedk"])}
    return {"figures/rq3.tex": rq3_figure(read, kept), "tables/rq3_erratum.tex": fixedk_erratum(frame, kept, labels)}, numbers


def trend(sizes, scores):
    """End points of the least-squares line over the measured size range."""
    slope = sizes.cov(scores) / sizes.var()
    return [(size, scores.mean() + slope * (size - sizes.mean())) for size in (sizes.min(), sizes.max())]


def rq3_figure(read, kept):
    """Settings on the same questions: Recall@10 and hybrid Recall@1,250 against mean chunk size, one panel per parser."""
    frame = read.csv("fixedk", usecols=KEYS + ["chunk_tokens", "recall10"], dtype={"question_id": str})
    scores = read.csv("scores_tuning", usecols=KEYS + ["retriever", "budget", "recall"], dtype={"question_id": str})
    scores = scores[(scores["retriever"] == "hybrid") & (scores["budget"] == 1250)]
    frame = frame[frame["setting"].isin(kept)].merge(scores[KEYS + ["recall"]], on=KEYS, how="left", validate="one_to_one")
    if frame["recall"].isna().any():
        raise ValueError("rq3: fixed-k rows without a Recall@1,250 score")
    series = {"recall10": ("*", "solid", "Recall@10 (fixed number of chunks)"), "recall": ("o", "dashed", "Recall@1,250 (fixed token budget)")}
    values, plots = ["chunk_tokens", *series], []
    for parser, part in frame.groupby("parser"):
        table = part.groupby(["setting", "doc_id"])[values].mean().groupby("setting").mean()  # question, then document means
        plots.append(f"\\nextgroupplot[title={{{display(parser)}}}]")
        for column, (mark, line, name) in series.items():
            plots.append(f"\\addplot[black, only marks, mark={mark}, mark size=1.3pt] coordinates {{{coordinates(table[['chunk_tokens', column]].itertuples(index=False))}}};")
            if parser == "pdfplumber":  # one legend, centred under both panels
                plots.append(f"\\addlegendentry{{{name}}}")
            plots.append(f"\\addplot[black, thick, {line}, forget plot] coordinates {{{coordinates(trend(table['chunk_tokens'], table[column]))}}};")
    return "\n".join([r"\begin{tikzpicture}",
                      r"\begin{groupplot}[group style={group size=2 by 1, horizontal sep=0.4cm, ylabels at=edge left, yticklabels at=edge left},"
                      r" scale only axis, width=0.5\columnwidth-0.9cm, height=4cm, xmin=0, ymin=0, ymax=1, label style={font=\footnotesize},"
                      r" tick label style={font=\footnotesize}, title style={font=\footnotesize}, xlabel={Mean chunk size (tokens)}, ylabel={Recall},"
                      r" /pgf/number format/1000 sep={,}, legend cell align=left, legend style={at={(-0.06,-0.32)}, anchor=north, font=\footnotesize}]",
                      *plots, r"\end{groupplot}", r"\end{tikzpicture}", ""])


def fixedk_erratum(frame, kept, labels):
    """Best setting per parser and measure with the superseded and sanity settings left out (as reported) and with
    them (as first reported); only the measures where the two differ (spec Errata 2026-11-14, fixed-k)."""
    def best(part):
        return {parser: best_sizes(table)[1].query("scope == 'all settings'").set_index("measure")
                for parser, table in fixedk_tables(part).items()}
    corrected, first = best(frame[frame["setting"].isin(kept)]), best(frame)
    rows = [[display(parser), labels[measure], f"{setup_name(first[parser].loc[measure, 'best setting'])} ({fixed(first[parser].loc[measure, 'score'])})",
             f"{setup_name(corrected[parser].loc[measure, 'best setting'])} ({fixed(corrected[parser].loc[measure, 'score'])})"]
            for parser in sorted(corrected) for measure in MEASURES
            if first[parser].loc[measure, "best setting"] != corrected[parser].loc[measure, "best setting"]]
    return tabular("llll", ["Parser", "Measure", "First reported (all settings)", "Corrected (in scope)"], rows)


def tick_step(rows, most=4):
    """The smallest of a few round steps that gives at most `most` x ticks over the rows' intervals."""
    span = max(high for *rest, high, passes in rows) - min(low for *rest, low, high, passes in rows)
    return next(step for step in (0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5) if span / step <= most)


def interval_plot(rows, title, xlabel, row_height=0.55):
    """One axis of differences with asymmetric 95% intervals, one row per comparison, labels on one line; filled
    black circles pass Holm, open circles do not."""
    # pgfplots cannot parse ( ) or , inside a symbolic coordinate: letters-only keys, readable names as tick labels
    keys = {name: letters(name) for name, *rest in rows}
    lines = [f"\\nextgroupplot[title={{{title}}}, xlabel={{{xlabel}}}, height={len(rows) * row_height:.2f}cm, symbolic y coords={{{','.join(keys.values())}}},"
             f" ytick={{{','.join(keys.values())}}}, yticklabels={{{','.join(f'{{{name}}}' for name in keys)}}},"
             f" xtick distance={tick_step(rows)},"
             r" extra x ticks={0}, extra x tick labels={}, extra x tick style={grid=major, major grid style={dashed}}]"]
    for passed in (True, False):
        chosen = [(keys[name], difference, low, high) for name, difference, low, high, passes in rows if passes == passed]
        if chosen:
            points = " ".join(f"({difference:.3f},{name}) -= ({difference - low:.3f},0) += ({high - difference:.3f},0)"
                              for name, difference, low, high in chosen)
            lines.append(f"\\addplot+[black, only marks, mark={'*' if passed else 'o'}, mark options={{black}}, error bars/.cd, x dir=both, x explicit]"
                         f" coordinates {{{points}}};")
    return lines


def rq5(read):
    chunker, digital, scanned = read.csv("rq5_chunker"), read.csv("rq5_digital"), read.csv("rq5_scanned")
    chunker_rows = [(short_family(row.family, row.parser), row.difference, row.low, row.high, bool(row.beats_default))
                    for row in chunker.sort_values(["family", "parser"]).itertuples(index=False)]
    digital_rows = [(short_variant(row.variant), row.difference, row.low, row.high, bool(row.beats_default))
                    for row in digital.sort_values("variant").itertuples(index=False)]
    figure = "\n".join([r"\begin{tikzpicture}",
                        r"\begin{groupplot}[group style={group size=1 by 2, vertical sep=2.2cm}, scale only axis,"
                        r" width=\columnwidth-3.6cm, scaled x ticks=false,"
                        r" x tick label style={/pgf/number format/fixed}]",
                        *interval_plot(digital_rows, "(a) Parser settings, digital", r"Recall difference (variant $-$ default)"),
                        *interval_plot(chunker_rows, "(b) Chunk size", r"Recall difference (tuned $-$ default)"),
                        r"\end{groupplot}", r"\end{tikzpicture}", ""])
    numbers = {}
    for row in chunker.itertuples(index=False):
        name = f"RQfiveB{letters(row.family)}{letters(row.parser)}"
        numbers |= {f"{name}Default": (fixed(row.default_recall), INPUTS["rq5_chunker"]), f"{name}Tuned": (fixed(row.tuned_recall), INPUTS["rq5_chunker"]),
                    f"{name}Diff": (signed(row.difference), INPUTS["rq5_chunker"]), f"{name}CI": (interval(row.low, row.high), INPUTS["rq5_chunker"]),
                    f"{name}Holm": (holm_text(row.holm_p, len(chunker)), INPUTS["rq5_chunker"])}
    scan = scanned.iloc[0]
    numbers |= {"RQfiveBComparisons": (len(chunker), INPUTS["rq5_chunker"]),
                "RQfiveADigitalMaxAbsDiff": (fixed(digital["difference"].abs().max()), INPUTS["rq5_digital"]),
                "RQfiveADigitalMinHolm": (fixed(digital["holm_p"].min(), 2), INPUTS["rq5_digital"]),
                "RQfiveADigitalQuestions": (f"{digital['questions'].min()}--{digital['questions'].max()}", INPUTS["rq5_digital"]),
                "RQfiveAScannedDiff": (signed(scan["difference"], 2), INPUTS["rq5_scanned"]),
                "RQfiveAScannedCI": (interval(scan["low"], scan["high"], 2), INPUTS["rq5_scanned"]),
                "RQfiveAScannedHolm": (fixed(scan["holm_p"], 2), INPUTS["rq5_scanned"]),
                "RQfiveAScannedDocuments": (int(scan["documents"]), INPUTS["rq5_scanned"]),
                "RQfiveAScannedQuestions": (int(scan["questions"]), INPUTS["rq5_scanned"])}
    for parser, recall in digital.groupby("default")["default_recall"]:  # one default, several shared-question samples
        low, high = fixed(recall.min()), fixed(recall.max())
        numbers[f"RQfiveADigital{letters(parser)}Recall"] = (low if low == high else f"{low}--{high}", INPUTS["rq5_digital"])
    return {"figures/rq5.tex": figure}, numbers


def aq_spearman(read, name, scores_key):
    """Spearman with Recall@BUDGET across setups on the answers that have a Recall score, as aq_run --stage analyse
    computes it (scripts/aq_run.py, analyse; no function returns it, so the same steps are repeated here)."""
    answers = read.csv("aq_f1", dtype={"question_id": str})
    judged = read.jsonl("aq_judgements").rename(columns={"score": "judge_secondary"})
    answers = answers.merge(judged[KEYS + ["judge_secondary"]], on=KEYS, how="left")
    recall = read.csv(scores_key, usecols=KEYS + ["retriever", "budget", "recall"], dtype={"question_id": str})
    recall = recall[(recall["retriever"] == "hybrid") & (recall["budget"] == BUDGET)]
    scored = answers[answers["set"] == name].merge(recall[KEYS + ["recall"]], on=KEYS, how="left").dropna(subset=["recall"])
    setups = scored.groupby(["parser", "setting", "doc_id"])[["f1", "judge_secondary", "recall"]].mean().groupby(["parser", "setting"]).mean()
    return setups.corr(method="spearman").loc["recall"]


def judge_second_pass(read):
    """Agreement and Cohen's kappa of the judge against the human labels, as aq_run --stage judge-check-score."""
    cases = read.csv("judge_check", index_col="case").join(read.csv("judge_check_keys", index_col="case"))
    compared = cases.reset_index().merge(read.jsonl("aq_judgements"), on=KEYS)
    human, judge = compared["human"].astype(float).tolist(), compared["score"].astype(float).tolist()
    return sum(one == two for one, two in zip(human, judge)) / len(human), cohen_kappa(human, judge), len(human)


def setting_part(parser, setting):
    """A macro part for parser and setting, without the parts every setting shares (no overlap, no prefix)."""
    return letters(parser) + letters(re.sub(r"_overlap0|_noprefix", "", setting))


def comparison_macros(prefix, versus, source):
    """Difference, interval and Holm p of every comparison against the best setup, one macro set per setup."""
    numbers = {}
    for row in versus.itertuples(index=False):
        name = prefix + setting_part(row.parser, row.setting)
        numbers |= {f"{name}Setup": (setup_name(f"{row.parser}/{row.setting}"), source),
                    f"{name}Diff": (signed(row.difference), source), f"{name}CI": (interval(row.low, row.high), source),
                    f"{name}Holm": (holm_text(row.holm_p, len(versus)), source)}
    return numbers


def aq_scanned(read):
    """Scanned answer quality: the best setup, how many comparisons it wins per parser, how many are significant after
    Holm (p < 0.05), and the largest difference."""
    setups, versus, source = read.csv("aq_scanned"), read.csv("aq_scanned_vs_best"), INPUTS["aq_scanned_vs_best"]
    best, top = setups.loc[setups["f1"].idxmax()], versus.loc[versus["difference"].idxmax()]
    numbers = {"RQfourScannedBest": (setup_name(f"{best.parser}/{best.setting}"), INPUTS["aq_scanned"]),
               "RQfourScannedBestFOne": (fixed(best.f1), INPUTS["aq_scanned"]),
               "RQfourScannedComparisons": (len(versus), source),
               "RQfourScannedSignificant": (int((versus["holm_p"] < 0.05).sum()), source),
               "RQfourScannedTopSetup": (setup_name(f"{top.parser}/{top.setting}"), source),
               "RQfourScannedTopDiff": (signed(top.difference), source), "RQfourScannedTopCI": (interval(top.low, top.high), source),
               "RQfourScannedTopHolm": (holm_text(top.holm_p, len(versus)), source)}
    for parser, group in versus.groupby("parser"):
        numbers |= {f"RQfourScannedAbove{letters(parser)}": (int((group["difference"] > 0).sum()), source),
                    f"RQfourScannedCount{letters(parser)}": (len(group), source)}
    return numbers


def rq4(read):
    setups, versus = read.csv("aq_held_out"), read.csv("aq_held_out_vs_best")
    best = setups.loc[setups["f1"].idxmax()]
    rows = [[short(f"{row.parser}/{row.setting}"), signed(row.difference), interval(row.low, row.high), holm_text(row.holm_p, len(versus))]
            for row in versus.sort_values("difference", ascending=False).itertuples(index=False)]
    tuning = read.csv("aq_tuning_vs_best")
    numbers = {"RQfourBest": (setup_name(f"{best.parser}/{best.setting}"), INPUTS["aq_held_out"]),
               "RQfourBestFOne": (fixed(best.f1), INPUTS["aq_held_out"]),
               "RQfourComparisons": (len(versus), INPUTS["aq_held_out_vs_best"]),
               "RQfourTuningMinHolm": (fixed(tuning["holm_p"].min(), 2), INPUTS["aq_tuning_vs_best"])}
    numbers |= comparison_macros("RQfour", versus, INPUTS["aq_held_out_vs_best"])
    numbers |= aq_scanned(read)
    for split, key in (("tuning", "scores_tuning"), ("held_out", "scores_held_out")):
        spearman = aq_spearman(read, split, key)
        numbers |= {f"RQfourSpearman{letters(split)}FOne": (fixed(spearman["f1"], 2), f"{INPUTS['aq_f1']}, {INPUTS[key]}"),
                    f"RQfourSpearman{letters(split)}Judge": (fixed(spearman["judge_secondary"], 2), f"{INPUTS['aq_judgements']}, {INPUTS[key]}")}
    agreement, kappa, cases = judge_second_pass(read)
    numbers |= {"JudgeSecondAgreement": (f"{agreement * 100:.0f}", f"{INPUTS['judge_check']} (percent)"),
                "JudgeSecondKappa": (fixed(kappa, 2), INPUTS["judge_check"]), "JudgeCases": (cases, INPUTS["judge_check"])}
    header = ["Setup", "F1 difference", r"95\% interval", "Holm $p$"]
    return {"tables/rq4.tex": tabular("lrrr", header, rows)}, numbers


def coverage(read):
    """Questions lost from the gold (not placed or not certain) over main questions (QASPER, UniDoc and page-level
    gold excluded), and the held-out document accounting from the split file and the P4 documents."""
    numbers = {}
    for name, key, splits in (("Tuning", "gold_drop_tuning", {"tuning"}), ("HeldOut", "gold_drop_final", {"held_out", "held_out_c", "held_out_ood"})):
        drop = read.csv(key)
        main = drop[drop["split"].isin(splits) & ~drop["source"].isin(["QASPER", "UniDoc"]) & drop["gold_file"].isin(["docling", "pdfplumber"])]
        for parser, group in main.groupby("gold_file"):
            lost, total = int(group["placed_not_certain"].sum() + group["not_placed"].sum()), int(group["total"].sum() - group["page_level"].sum())
            numbers |= {f"Coverage{name}{letters(parser)}Lost": (lost, INPUTS[key]), f"Coverage{name}{letters(parser)}Total": (total, INPUTS[key]),
                        f"Coverage{name}{letters(parser)}Share": (f"{lost / total:.1%}".replace("%", r"\%"), INPUTS[key])}
        if name == "HeldOut":  # where the held-out loss comes from: each split and source, per parser
            for (part, source, parser), group in main.groupby(["split", "source", "gold_file"]):
                lost, total = int(group["placed_not_certain"].sum() + group["not_placed"].sum()), int(group["total"].sum() - group["page_level"].sum())
                if total:
                    numbers[f"CoverageBySource{letters(part)}{letters(source)}{letters(parser)}"] = (f"{lost / total:.0%}".replace("%", r"\%"), INPUTS[key])
    split = read.csv("split")
    held = split[split["split"].str.startswith("held_out")]
    kept = set(read.csv("p4_primary_documents")["doc_id"])
    removed = held[~held["doc_id"].isin(kept)].groupby("source_dataset").size()
    numbers |= {"AccountingHeldOut": (len(held), INPUTS["split"]), "AccountingMain": (len(kept), INPUTS["p4_primary_documents"])}
    numbers |= {f"AccountingRemoved{letters(source)}": (int(count), INPUTS["split"]) for source, count in removed.items()}
    return {}, numbers


def a1_index_cost(read):
    chosen = ["method1_tree_T384_noprefix", "recursive_size384_overlap0_noprefix", "langchain_recursive_size384_overlap0_noprefix"]
    rows = []
    for split, key in (("Tuning", "p4_tuning_full"), ("Held-out", "p4_full")):
        setups = read.csv(key, index_col=0)
        for parser in ("docling", "pdfplumber"):
            for setting in chosen:
                row = setups.loc[f"{parser}/{setting}"]
                rows.append([split, short(f"{parser}/{setting}"), fixed(row["chunks"], 1), f"{row['index_tokens']:,.0f}",
                             f"{row['index_tokens'] / row['chunks']:.0f}", fixed(row["recall"])])
    header = ["Split", "Setup", "Chunks", "Index tokens", "Tokens / chunk", "Recall"]
    return {"tables/a1_index_cost.tex": tabular("llrrrr", header, rows)}, {}


def a2_retrievers(read):
    summary = read.csv("retrievers")
    primary = summary[summary["scope"] == "primary"].sort_values(["split", "retriever"], ascending=[False, True])
    rows = [[display(row.split), display(row.retriever), short(row.best_single), fixed(row.best_recall), row.tied,
             f"{signed(row.gap)} {interval(row.gap_low, row.gap_high)}", "GO" if row.go else "NO-GO"] for row in primary.itertuples(index=False)]
    header = ["Split", "Retriever", "Best single", "Recall", "Tied", r"Gap [95\%]", "Rule"]
    return {"tables/a2_retrievers.tex": tabular("lllrrll", header, rows)}, {}


def a5_compute(read):
    compute = read.csv("compute").groupby("group")[["gpu_hours", "cpu_hours", "chunker_llm_calls", "aq_answer_calls", "agent_answer_calls", "paid_credits"]].sum()
    labels = {"gpu_hours": "GPU hours", "cpu_hours": "CPU hours", "chunker_llm_calls": "LLM calls: chunkers",
              "aq_answer_calls": "LLM calls: AQ", "agent_answer_calls": "LLM calls: agent", "paid_credits": "LlamaParse credits"}
    groups = sorted(compute.index)
    rows = [[label] + [fixed(compute.loc[group, column], 1) if "hours" in column else f"{compute.loc[group, column]:,.0f}" for group in groups]
            for column, label in labels.items()]
    return {"tables/a5_compute.tex": tabular("l" + "r" * len(groups), [""] + [display(group) for group in groups], rows)}, {}


def a6_no_indian(read):
    groups = {}
    for split, key in (("Tuning", "tuning_p4"), ("Held-out", "held_out_no_indian")):
        table = read.csv(key).assign(documents_set=lambda frame: frame["variant"].map(lambda variant: "all" if variant.startswith("all") else "no Indian"))
        counts = table.drop_duplicates("documents_set")  # documents and questions are the same in every choice set of a group
        if len(table.drop_duplicates(["documents_set", "documents", "questions"])) != len(counts):
            raise ValueError(f"{key}: documents or questions differ between choice sets")
        label = f"{split}: " + ", ".join(f"{row.documents_set} {row.documents} / {row.questions}" for row in counts.itertuples(index=False)) + " (documents / questions)"
        rows = groups.setdefault(label, [])
        for row in table.itertuples(index=False):
            rows.append([row.documents_set, display(row.scope), short(row.best_single),
                         fixed(row.best_recall), row.tied, f"{signed(row.gap)} {interval(row.gap_low, row.gap_high)}", "GO" if row.go else "NO-GO"])
    header = ["Documents", "Choice set", "Best single", "Recall", "Tied", r"Gap [95\%]", "Rule"]
    return {"tables/a6_no_indian.tex": grouped_tabular("lllrrll", header, groups)}, {}


def a7_golden(read):
    labels = read.csv("golden_labels", dtype=str, keep_default_na=False).merge(read.csv("golden_sample", dtype={"question_id": str}), on=["doc_id", "question_id"])
    rows, numbers = [], {}
    for doc, group in [*sorted(labels.groupby("doc_id")), ("Overall", labels)]:
        total, invalid, unsure = len(group), int((group["label"] == "invalid").sum()), int((group["label"] == "unsure").sum())
        rows.append([short_document(doc) if doc != "Overall" else doc, total, invalid, f"{fixed(invalid / total)} {interval(*wilson(invalid, total))}", unsure,
                     f"{fixed((invalid + unsure) / total)} {interval(*wilson(invalid + unsure, total))}"])
        name = f"Golden{letters(doc)}"
        numbers |= {f"{name}Invalid": (invalid, INPUTS["golden_labels"]), f"{name}Labelled": (total, INPUTS["golden_labels"]),
                    f"{name}Rate": (fixed(invalid / total), INPUTS["golden_labels"]), f"{name}RateCI": (interval(*wilson(invalid, total)), INPUTS["golden_labels"]),
                    f"{name}Unsure": (unsure, INPUTS["golden_labels"])}
    header = ["Document", "Labelled", "Invalid", r"Rate [95\%]", "Unsure", r"Invalid or unsure [95\%]"]
    return {"tables/a7_golden.tex": tabular("lrrlrl", header, rows)}, numbers


FLOOR = re.compile(r"^\s+(PASS|FAIL) (\w+)\s+(\w+)\s+random ([\d.]+) \[[^]]*\] vs best (\S+) ([\d.]+)", re.M)
DAMAGE_HEADER = re.compile(r"table questions on Docling: (\d+) \(documents: (\d+)\)")
DAMAGE = re.compile(r"^\s+(PASS|FAIL) (\w+)\s+table questions: split ([\d.]+) vs method 1 ([\d.]+) \| other questions: split ([\d.]+) vs method 1 ([\d.]+)", re.M)


def sanity(read):
    """Scorer sanity tests from their log: the floor test (random cuts against the best setting, under the rule
    written before the run) and the damage test (every table split, table questions against the others)."""
    log = read.text("sanity_log")
    floor, damage, header = FLOOR.findall(log), DAMAGE.findall(log), DAMAGE_HEADER.search(log)
    if not floor or not damage or not header:
        raise ValueError("sanity log: floor, damage or the damage header not found")
    lower = [float(best) - float(random) for verdict, parser, retriever, random, setting, best in floor]
    drops = [float(intact) - float(split) for verdict, retriever, split, intact, other_split, other_intact in damage]
    others = [abs(float(other_intact) - float(other_split)) for *rest, other_split, other_intact in damage]
    source = INPUTS["sanity_log"]
    return {}, {"SanityFloorCases": (len(floor), source),
                "SanityFloorFailedOriginal": (sum(verdict == "FAIL" for verdict, *rest in floor), source),
                "SanityFloorLower": (f"{fixed(min(lower), 2)}--{fixed(max(lower), 2)}", source),
                "SanityDamageQuestions": (int(header.group(1)), source), "SanityDamageDocuments": (int(header.group(2)), source),
                "SanityDamageCases": (len(damage), source), "SanityDamagePassed": (sum(verdict == "PASS" for verdict, *rest in damage), source),
                "SanityDamageDrop": (f"{fixed(min(drops), 2)}--{fixed(max(drops), 2)}", source),
                "SanityDamageOtherMax": (fixed(max(others), 2), source)}


# Appendix A3: the events of RESULTS.md 8.3 whose evidence is checksummed or content-addressed (commits, the tag)
TIMELINE = [("Specification v1", "commit", "607d29c"), ("Specification v1.1: chunker pool, oracle, gap", "commit", "de4aff3"),
            ("Method 1 defined before any retrieval result", "commit", "a4c30f7"), ("Specification v1.2: Method 1 rules", "commit", "4584c8f"),
            ("Method 1 rules added", "commit", "5503874"), ("Method 1 amendment: line blocks", "commit", "f92ba8c"),
            ("Amendment: floor test and tie rule", "commit", "a89b9ff"), ("RQ5 added (after the tuning scores)", "commit", "e59c69c"),
            (r"scorer\_v1 frozen", "commit", "448173c"), ("Grid extension after the first official run", "commit", "6032033"),
            ("Method 1 v1.2 (prefix cap)", "commit", "93d7e16"), ("P4 v2 on the tuning set", "commit", "a781ff7"),
            ("Held-out plan frozen", "commit", "305da55"), ("Held-out extraction (pdfplumber)", "run", "pdfplumber_record"),
            ("Held-out chunking", "run", "chunking_final_record"), ("Held-out gold", "commit", "a2c87c6"),
            ("Held-out scoring", "run", "p3_final_record"), ("Held-out analysis", "run", "p4_final"),
            ("Held-out result", "commit", "0d42cd0"), ("RQ5(a) design frozen", "commit", "8116310"),
            ("Answer-quality design frozen", "commit", "479a55c"), ("Answer-quality code", "commit", "e5a924a"),
            ("Correction (MP-DocVQA answers); judge-check code", "commit", "3d5407e"), ("Answer-quality result", "commit", "a6278ca"),
            ("Held-out gold-drop and size-by-source reports", "commit", "5a6b52d"), ("Errata", "commit", "3b9ecd6"),
            ("Errata", "commit", "56bd9ae"), ("Result files tracked (paper tag)", "tag", TAG)]
ZERO = "0" * 40


def first_pushes(read):
    """Full commit hash -> time of the first push to main that brought it, from GitHub's activity pages."""
    events = sorted((event for key in ("github_page1", "github_page2") for event in read.json(key)), key=lambda event: event["timestamp"])
    pushed = {}
    for event in events:
        span = event["after"] if event["before"] == ZERO else f"{event['before']}..{event['after']}"
        moment = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
        for commit in read.git("rev-list", span).split():
            pushed.setdefault(commit, moment)
    return pushed


def timeline(read):
    """Commit times from git (content-addressed), first push times from the activity pages, run times from the run
    records' created_at, the paper tag's commit time from git; Indian Standard Time."""
    pushed, rows = first_pushes(read), []
    shown = lambda moment: f"{moment.astimezone(IST):%m-%d %H:%M:%S}"
    for label, kind, ref in TIMELINE:
        if kind == "run":
            rows.append([label, f"\\texttt{{{escape(read.json(ref)['run_id'])}}}", shown(datetime.fromisoformat(read.json(ref)["created_at"])), "--"])
            continue
        commit = read.git("rev-parse", f"{ref}^{{commit}}")
        made, first = read.commit_time(commit), pushed.get(commit)
        if first and first < made:
            raise ValueError(f"{ref}: pushed before it was committed")
        rows.append([label, f"\\texttt{{{escape(ref) if kind == 'tag' else commit[:7]}}}", shown(made), shown(first) if first else "--"])
    return {"tables/a3_timeline.tex": tabular(r"p{4.2cm}lll", ["Event", "Commit / run / tag", "Made (IST)", "First pushed (IST)"], rows)}, {}


def long_date(moment):
    return f"{moment.astimezone(IST).day} {moment.astimezone(IST):%B %Y}"


def design(read):
    """Method facts: specification and freeze dates from git (the commit that first adds each spec file, the
    scorer_v1 tag) and the held-out scoring time from its run record; document and question counts of the tuning set
    from the split file, the P3 tuning scores and the P4 tuning record."""
    numbers = {}
    for name, (commit, path) in SPEC_COMMITS.items():
        if not read.added_in(path).startswith(commit):
            raise ValueError(f"{path} was first added in {read.added_in(path)}, not {commit}")
        numbers[name] = (long_date(read.commit_time(commit)), f"git {commit}, first adds {path}")
    if not read.tag_commit(SCORER_TAG).startswith(SCORER_COMMIT):
        raise ValueError(f"tag {SCORER_TAG} points to {read.tag_commit(SCORER_TAG)}, not {SCORER_COMMIT}")
    numbers["DateScorerFrozen"] = (long_date(read.commit_time(SCORER_COMMIT)), f"git {SCORER_COMMIT}, tag {SCORER_TAG}")
    numbers["DateHeldOutScored"] = (long_date(datetime.fromisoformat(read.json("p3_final_record")["created_at"])),
                                    f"{INPUTS['p3_final_record']} created_at")
    split = read.csv("split")
    tuning = set(split[split["split"] == "tuning"]["doc_id"])
    scores = read.csv("scores_tuning", usecols=["doc_id", "retriever", "budget"])
    scored = tuning & set(scores[(scores["retriever"] == "hybrid") & (scores["budget"] == BUDGET)]["doc_id"])
    main = read.json("p4_tuning_record")["stack"]["summary"]["full"]
    numbers |= {"TuningDocuments": (len(tuning), INPUTS["split"]),
                "TuningScoredDocuments": (len(scored), f"{INPUTS['scores_tuning']} (hybrid, Recall@{BUDGET})"),
                "TuningMainDocuments": (main["documents"], INPUTS["p4_tuning_record"]),
                "TuningMainQuestions": (main["questions"], INPUTS["p4_tuning_record"])}
    return {}, numbers


def method_facts(read):
    """Method numbers: the held-out 2 documents from the split file and the gold drop threshold, the first (cheapest-tie)
    tuning run and the answer temperature as tagged; the top tuning setup and the scanned questions from locked inputs."""
    corpora = pd.read_csv(io.StringIO(read.git("show", f"{LOCK_TAG}:{INPUTS['split']}")))
    corpora = corpora[corpora["split"] == "held_out_2"]["doc_id"].str.split("_").str[1].value_counts()
    threshold, first = (json.loads(read.tagged_file(path)) for path in (DROP_RULE, CHEAPEST_TIE_RUN))
    temperature = re.search(r"temperature=(\d+)", read.tagged_file("src/chunk/llm.py")).group(1)
    drop = read.csv("gold_drop_final")
    scanned = drop[(drop["split"] == "scanned_rq5") & (drop["gold_file"] == "docling")]
    split = f"{INPUTS['split']} at {LOCK_TAG}"
    numbers = {f"HTwoSelected{letters(corpus)}": (int(count), split) for corpus, count in corpora.items()}
    return {}, numbers | {"HTwoSelectedDocuments": (int(corpora.sum()), split),
                          "GoldDropThreshold": (threshold["threshold"], f"{DROP_RULE} at {TAG}"),
                          "CheapestTieBestRecall": (fixed(first["stack"]["summary"]["full"]["best_single_recall"]), f"{CHEAPEST_TIE_RUN} at {TAG}"),
                          "TuningTopRecall": (fixed(read.json("p4_tuning_record")["stack"]["summary"]["full"]["best_single_recall"]), INPUTS["p4_tuning_record"]),
                          "ScannedQuestions": (int(scanned["total"].sum()), INPUTS["gold_drop_final"]),
                          "AnswerTemperature": (temperature, f"src/chunk/llm.py at {TAG}")}


def setups_scoring(read):
    """Method facts on parsers, chunkers, retrieval and scoring: versions and scorer settings from the run records,
    the size grid from the tuning setup table, setup counts from the P4 records, and the shared post-processing and
    prefix cap from the code, which must be unchanged since the paper tag."""
    changed = read.changed_since_tag(CODE_AT_TAG)
    if changed:
        raise ValueError(f"code changed since {TAG}, constants would not be the frozen ones: {changed}")
    docling = read.json("docling_record")["stack"]["parser"]
    if docling["settings"].get("variant") or not docling["settings"]["do_ocr"] or docling["settings"]["ocr_engine"] != "OcrAutoOptions":
        raise ValueError("the Docling record is not the default automatic-OCR setup")
    scoring, fixedk = read.json("p3_tuning_record")["stack"], read.json("fixedk_record")["stack"]
    budgets = sorted(scoring["budgets"])
    settings = read.csv("p4_tuning_full", index_col=0).index.str.split("/").str[1].unique()
    sizes = {family: {int(match.group(1)) for setting in settings if (match := re.fullmatch(pattern, setting))}
             for family, pattern in SIZE_FAMILIES.items()}
    shared = sorted(set.intersection(*sizes.values()))
    steps = {later - earlier for earlier, later in zip(shared, shared[1:])}
    if len(steps) != 1:
        raise ValueError(f"the shared size grid is not evenly spaced: {shared}")
    extra = {family: sorted(found - set(shared)) for family, found in sizes.items() if found - set(shared)}
    full = lambda key: read.json(key)["stack"]["summary"]["full"]["setups"]
    record, code = INPUTS["p3_tuning_record"], f"{' and '.join(CODE_AT_TAG)} at {TAG}"
    rows = [[r"\texttt{" + escape(name) + "}", r"\texttt{" + escape(json.dumps(value).strip('"')) + "}"]
            for name, value in docling["settings"].items()]  # every setting the record lists, as recorded
    settings_table = tabular("ll", ["Setting", "Value"], rows)
    return {"tables/docling_settings.tex": settings_table}, {"DoclingVersion": (docling["version"], INPUTS["docling_record"]),
                "PdfplumberVersion": (read.json("pdfplumber_record")["stack"]["parser"]["version"], INPUTS["pdfplumber_record"]),
                "BMKone": (scoring["scorer"]["bm25"]["k1"], record), "BMb": (scoring["scorer"]["bm25"]["b"], record),
                "RRFk": (scoring["scorer"]["hybrid"]["k"], record), "EmbedDim": (f"{scoring['embedder']['dimension']:,}", record),
                "BudgetLow": (f"{budgets[0]:,}", record), "BudgetMain": (f"{budgets[1]:,}", record), "BudgetHigh": (f"{budgets[2]:,}", record),
                "TopKSmall": (min(fixedk["ks"]), INPUTS["fixedk_record"]), "TopKLarge": (max(fixedk["ks"]), INPUTS["fixedk_record"]),
                "FixedKBudget": (f"{fixedk['budget']:,}", INPUTS["fixedk_record"]),
                "TuningSetups": (full("p4_tuning_record"), INPUTS["p4_tuning_record"]), "HeldOutSetups": (full("p4_final"), INPUTS["p4_final"]),
                "SizeMin": (f"{shared[0]:,}", f"{INPUTS['p4_tuning_full']}; sizes shared by {', '.join(SIZE_FAMILIES)}; also {extra or 'none'}"),
                "SizeMax": (f"{shared[-1]:,}", INPUTS["p4_tuning_full"]), "SizeStep": (steps.pop(), INPUTS["p4_tuning_full"]),
                "ChunkMin": (MIN_TOKENS, code), "ChunkMax": (f"{MAX_TOKENS:,}", code),
                "PrefixCap": (f"{CHUNKERS['method1_tree']['prefix_share']:.0%}".replace("%", r"\%"), code)}


def first_pass_reconstruction(read):
    """Cohen's kappa of every first-pass table consistent with the spec note: the judge scores are fixed; the 28
    first-pass agreements are unchanged; 11 of the 12 disagreements are human 0.5 against judge 1; the 12th is the
    judge-0.5 case, whose first-pass human label was 0 or 1 (it is 1 now, and a disagreement cannot be 0.5).
    Returns the lowest and highest kappa and the number of disagreements the reconstruction rests on."""
    facts = read.csv("manual", dtype=str, keep_default_na=False).set_index("key")["value"]
    disagreements, long_correct = int(facts["judge_first_pass_disagreements"]), int(facts["judge_first_pass_long_correct"])
    cases = read.csv("judge_check", index_col="case").join(read.csv("judge_check_keys", index_col="case"))
    judge = cases.reset_index().merge(read.jsonl("aq_judgements"), on=KEYS)["score"].astype(float).tolist()
    zeros, halves, ones = (judge.count(value) for value in (0.0, 0.5, 1.0))
    if halves != disagreements - long_correct or zeros + halves + ones != len(judge):
        raise ValueError("the judge scores do not fit the reconstruction's assumptions")
    judged = [0.0] * zeros + [1.0] * ones + [0.5] * halves
    kappas = [cohen_kappa([0.0] * zeros + [1.0] * (ones - long_correct) + [0.5] * long_correct + [twelfth] * halves, judged)
              for twelfth in (0.0, 1.0)]
    return min(kappas), max(kappas), disagreements


def statistics_aq(read):
    """Statistics settings from the P4 records (checked against the tagged code), the answer-quality sample from
    its file and share, the judge first-pass reconstruction, and the size of the GOLDEN_200 check."""
    changed = read.changed_since_tag(CODE_AT_TAG)
    if changed:
        raise ValueError(f"code changed since {TAG}, constants would not be the frozen ones: {changed}")
    stack = read.json("p4_final")["stack"]
    if (stack["resamples"], stack["level"], stack["splits"]) != (RESAMPLES, LEVEL, SPLITS):
        raise ValueError("P4 record and tagged code disagree on resamples, level or splits")
    sample = read.csv("aq_sample").groupby("set")["question_id"].nunique()
    low, high, disagreements = first_pass_reconstruction(read)
    recon = "reconstruction from judge_check.csv, judgements.jsonl, manual_facts.csv"
    labels = read.csv("golden_labels", dtype=str, keep_default_na=False)
    record, aq = INPUTS["p4_final"], INPUTS["aq_sample"]
    return {}, {"CILevel": (f"{stack['level'] * 100:.0f}", record), "Resamples": (f"{stack['resamples']:,}", record),
                "SplitHalfReps": (stack["splits"], record), "AQSampleShare": (f"{AQ_SHARE:.0%}".replace("%", r"\%"), f"scripts/aq_run.py at {TAG}"),
                "AQTuningQuestions": (int(sample["tuning"]), aq), "AQHeldOutQuestions": (int(sample["held_out"]), aq),
                "AQScannedQuestions": (int(sample["scanned"]), aq),
                "JudgeReconKappaLow": (fixed(low, 2), recon), "JudgeReconKappaHigh": (fixed(high, 2), recon),
                "JudgeDisagreements": (disagreements, recon),
                "GoldenSampled": (len(labels), INPUTS["golden_labels"]),
                "GoldenInvalid": (int((labels["label"] == "invalid").sum()), INPUTS["golden_labels"]),
                "GoldenUnsure": (int((labels["label"] == "unsure").sum()), INPUTS["golden_labels"])}


def grid(read):
    """The full chunker grid of the tuning setup table, one row per family, primary choice set in bold."""
    settings = sorted(read.csv("p4_tuning_full", index_col=0).index.str.split("/").str[1].unique())
    primary = set(read.csv("p4_primary", index_col=0).index.str.split("/").str[1])
    order = lambda setting: [int(number) for number in re.findall(r"\d+", setting)] + [setting.endswith("_prefix")]
    rows = []
    for family, code in FAMILIES:
        members = sorted((setting for setting in settings if next(f for f, c in FAMILIES if setting.startswith(f)) == family), key=order)
        if members:
            names = [(r"\textbf{" + short(setting) + "}") if setting in primary else short(setting) for setting in members]
            rows.append([r"\texttt{" + escape(family) + "}", ", ".join(names)])
    unplaced = set(settings) - {setting for setting in settings if any(setting.startswith(family) for family, code in FAMILIES)}
    if unplaced:
        raise ValueError(f"settings without a family: {sorted(unplaced)}")
    return {"tables/grid.tex": tabular(r"lp{10.5cm}", ["Chunker", "Settings (bold: primary choice set of RQ1)"], rows)}, {}


def anchor_lines(text, anchor):
    lines = text.splitlines()
    return [line for line in lines if (line == anchor if anchor.startswith("#") else anchor in line)]


def deviations(read):
    """The deviations table and its count, from the spec as tagged (rows anchored to its lines, see DEVIATIONS),
    and the disclosures added to the spec after the tag (LATER_DISCLOSURES)."""
    tagged, working, rows = read.tagged_file(SPEC), (read.root / SPEC).read_text(encoding="utf-8"), []
    for text, (kind, anchors, summary) in [(tagged, row) for row in DEVIATIONS] + [(working, row) for row in LATER_DISCLOSURES]:
        found = [anchor_lines(text, anchor) for anchor in anchors]
        if any(len(lines) != 1 for lines in found):
            raise ValueError(f"spec anchor not on exactly one line: {[anchor for anchor, lines in zip(anchors, found) if len(lines) != 1]}")
        date = next(match.group(0) for lines in found if (match := re.search(r"\d{4}-\d{2}-\d{2}", lines[0])))
        rows.append([date, kind, escape(summary)])
    counts = {kind: sum(each == kind for each, anchors, summary in DEVIATIONS) for kind in ("deviation", "correction")}
    source = f"{SPEC} at {TAG}, rows of kind {{}} in tables/deviations.tex"
    return ({"tables/deviations.tex": tabular(r"llp{11cm}", ["Date", "Kind", "What"], rows)},
            {"DeviationCount": (counts["deviation"], source.format("deviation")),
             "CorrectionCount": (counts["correction"], source.format("correction"))})


MANUAL_SHOWN_ELSEWHERE = {"judge_first_pass_disagreements": "JudgeDisagreements"}  # one macro per number


def manual(read):
    """Typed numbers that cannot be recomputed (spec/paper_build_spec.md, section 6), each with its source. A fact that
    another builder already publishes under its own macro (MANUAL_SHOWN_ELSEWHERE) gets no Manual macro."""
    facts = read.csv("manual", dtype=str, keep_default_na=False)
    facts = facts[~facts["key"].isin(MANUAL_SHOWN_ELSEWHERE)]
    def shown(row):  # a proportion is written as a percent number (the text adds the percent sign)
        return f"{float(row.value) * 100:.0f}" if row.unit.startswith("proportion") else escape(row.value)
    return {}, {f"Manual{letters(row.key)}": (shown(row), f"{row.source_file} @ {row.source_commit}"
                                              + (" (percent)" if row.unit.startswith("proportion") else "")) for row in facts.itertuples(index=False)}


BUILDERS = {
    rq1: {"p4_final", "p4_primary", "tuning_p4", "h2_pooled"} | {key + part for key in H2_SETS for part in ("", "_setups")},
    rq2_held_out_2: {"h2_rq2"} | set(H2_SETS),
    hr_check: {"h2_exclusion", "h2_exclusion_record", "h2_drop"},
    robustness: {"retrievers", "held_out_no_indian", "ext_rq1", "rob_rq1"},
    rq2: {"size_tuning", "size_tuning_summary", "size_final_summary"},
    rq3: {"fixedk", "scores_tuning"},
    rq4: {"aq_held_out", "aq_held_out_vs_best", "aq_tuning_vs_best", "aq_scanned", "aq_scanned_vs_best", "aq_f1", "aq_judgements", "scores_tuning", "scores_held_out",
          "judge_check", "judge_check_keys"},
    rq5: {"rq5_chunker", "rq5_digital", "rq5_scanned"},
    coverage: {"gold_drop_tuning", "gold_drop_final", "split", "p4_primary_documents"},
    a1_index_cost: {"p4_tuning_full", "p4_full"},
    a2_retrievers: {"retrievers"},
    a5_compute: {"compute"},
    a6_no_indian: {"tuning_p4", "held_out_no_indian"},
    a7_golden: {"golden_labels", "golden_sample"},
    manual: {"manual"},
    design: {"split", "scores_tuning", "p3_final_record", "p4_tuning_record"},
    method_facts: {"gold_drop_final", "p4_tuning_record"},
    setups_scoring: {"docling_record", "pdfplumber_record", "p3_tuning_record", "fixedk_record", "p4_tuning_full", "p4_tuning_record", "p4_final"},
    statistics_aq: {"p4_final", "aq_sample", "manual", "judge_check", "judge_check_keys", "aq_judgements", "golden_labels"},
    grid: {"p4_tuning_full", "p4_primary"},
    deviations: set(),
    sanity: {"sanity_log"},
    timeline: {"github_page1", "github_page2", "pdfplumber_record", "chunking_final_record", "p3_final_record", "p4_final"},
}


# --- IEEE floats: caption above the table, booktabs, table* for wide tables -------------------------------------------

FLOATS = {  # table body -> (label, caption, wide)
    "rq1": ("tab:rq1", r"RQ1: hybrid Recall@1,250, primary choice set unless named. Held-out set~2 rows give documents / "
            r"questions. $^\dagger$Secondary: oracle minus the tuning winner, not the per-set gap; bootstrap stratified by set.", True),
    "rq2_h2": ("tab:rq2h2", r"RQ2 on held-out set~2: Spearman's $\rho$ of chunk size against Recall@$B$ per parser, with 95\% "
               r"document bootstrap intervals.", True),
    "ext_rob": ("tab:robust", "Robustness of RQ1 (hybrid Recall@1,250 unless named; 26 setups unless named).", True),
    "rq4": ("tab:rq4", "RQ4 on held-out set~1: token F1 of the best setup minus each setup.", False),
    "rq3_erratum": ("tab:rq3err", "RQ3 erratum: superseded settings removed.", True),
    "a1_index_cost": ("tab:cost", "Index cost at 384 tokens (mean per document).", True),
    "a2_retrievers": ("tab:retrievers", "RQ1 by retriever (primary choice set).", True),
    "a3_timeline": ("tab:timeline", "Pre-registration timeline (IST).", True),
    "a5_compute": ("tab:compute", "Compute.", False),
    "a6_no_indian": ("tab:noindian", "RQ1 with and without the Indian documents.", True),
    "a7_golden": ("tab:golden", "Indian-question validity check (batch 1).", True),
    "docling_settings": ("tab:docling", "Docling settings.", False),
    "grid": ("tab:chunkers", "Chunker grid (bold: primary choice set of RQ1).", True),
    "deviations": ("tab:deviations", "Deviations, corrections and disclosures recorded in the specification.", True),
    "key": ("tab:key", "Short names used in the tables.", True),
}


FIGURES = {  # figure body -> (label, caption, wide); the caption sits below the figure (IEEE)
    "rq2": ("fig:rq2", "RQ2 on tuning: Recall@1,250 against mean chunk size, per source.", False),
    "rq3": ("fig:rq3", "RQ3 on tuning: the same settings scored with a fixed number of chunks and with a fixed token budget. "
            "Both series use the same questions (QASPER included), so Recall@1,250 here differs slightly (up to 0.029) from the "
            "tuning per-setting means that exclude QASPER; trend lines are least-squares fits for display only. "
            r"Recall@4,000, a pre-registered RQ3 measure outside the main budgets, also favours small chunks: best setups "
            r"\RQthreeDoclingRecallFourZeroZeroZeroBest{} (\RQthreeDoclingRecallFourZeroZeroZeroSize{} tokens) on Docling and "
            r"\RQthreePdfplumberRecallFourZeroZeroZeroBest{} (\RQthreePdfplumberRecallFourZeroZeroZeroSize{} tokens) on pdfplumber.", False),
    "rq5": ("fig:rq5", "RQ5: (a) parser variants minus default, digital PDFs; (b) tuned size minus default, held-out set~1. "
            r"Bars: 95\% document bootstrap intervals. Filled marks are significant after Holm correction.", False),
}
FIGURE_ROOT = "generated/figures"  # the bodies' folder as main.tex (in paper_ieee/) inputs them


def figure_float(name):
    """An IEEE figure environment that inputs the generated body, caption below."""
    label, caption, wide = FIGURES[name]
    environment = "figure*" if wide else "figure"
    return "\n".join(["% Generated by paper_ieee/scripts/make_artifacts.py; do not edit.", f"\\begin{{{environment}}}[!t]",
                      r"\centering", f"\\input{{{FIGURE_ROOT}/{name}.tex}}", f"\\caption{{{caption}}}", f"\\label{{{label}}}",
                      f"\\end{{{environment}}}", ""])


def ieee_float(name, body):
    """A table body as an IEEE float; an unknown table name is an error, so every table has a label and caption."""
    label, caption, wide = FLOATS[name]
    environment = "table*" if wide else "table"
    return "\n".join([f"% Generated by paper_ieee/scripts/make_artifacts.py; do not edit.", f"\\begin{{{environment}}}[!t]",
                      r"\centering", f"\\caption{{{caption}}}", f"\\label{{{label}}}", r"\footnotesize",
                      body.rstrip("\n"), f"\\end{{{environment}}}", ""])


def layout(files):
    """paper_ieee/generated layout: one file per table (tables/<name>.tex -> <name>.tex, wrapped as a float), figures
    kept under figures/, numbers.tex at the top."""
    tables = {path: text for path, text in files.items() if path.startswith("tables/")}
    figures = {Path(path).stem for path in files if path.startswith("figures/")}
    if figures != set(FIGURES):
        raise ValueError(f"figures and FIGURES differ: {sorted(figures ^ set(FIGURES))}")
    unknown = {Path(path).stem for path in tables} - set(FLOATS) - {"numbers"}
    if unknown:
        raise ValueError(f"tables without a label and caption in FLOATS: {sorted(unknown)}")
    return {path: text for path, text in files.items() if path not in tables} | {
        f"figures/{name}_fig.tex": figure_float(name) for name in FIGURES} | {
        Path(path).name: text if Path(path).stem == "numbers" else ieee_float(Path(path).stem, text) for path, text in tables.items()}


# --- macro sheet for writing the Results section --------------------------------------------------------------------

def winner_rank(name):
    return "TuningWinner" in name and not name.startswith("RQonePooled")


SHEET = [  # (heading, macro filter); a heading without a filter has no generated input yet
    ("RQ1: held-out 1", lambda name: name.startswith("RQone") and not name.startswith(("RQoneHTwo", "RQonePooled", "RQoneHRCheck"))
     and not winner_rank(name)),
    ("RQ1: held-out 2 variants", lambda name: name.startswith("RQoneHTwo") and not winner_rank(name)),
    ("RQ1: pooled (secondary)", lambda name: name.startswith("RQonePooled")),
    ("RQ1: HR-pages check (drop-rule primary gold, its own bootstrap)", lambda name: name.startswith("RQoneHRCheck")),
    ("RQ1: tuning-winner rank", lambda name: name.startswith("RQone") and winner_rank(name)),
    ("RQ2", lambda name: name.startswith("RQtwo")),
    ("RQ3", lambda name: name.startswith("RQthree")),
    ("RQ4 (answer quality)", lambda name: name.startswith(("RQfour", "Judge", "AQ"))),
    ("RQ5", lambda name: name.startswith("RQfive")),
    ("Extension / robustness", lambda name: name.startswith("Rob")),
    ("Released tool", None),
]


def macro_sheet(numbers):
    """MACROS_RESULTS.md: the macros the Results section uses, grouped by question, then the tables."""
    lines = ["# Macros for the Results section", "",
             "Generated by paper_ieee/scripts/make_artifacts.py from numbers.tex and the table files. Values as typeset.", ""]
    for heading, keep in SHEET:
        names = [name for name in sorted(numbers) if keep and keep(name)]
        lines += [f"## {heading}"] + ([f"\\{name} = {numbers[name][0]}" for name in names] or ["(no macro yet: not in the generated inputs)"]) + [""]
    lines += ["## Tables", ""] + [f"{label} | {name}.tex | {caption}" for name, (label, caption, wide) in FLOATS.items()]
    return "\n".join(lines) + "\n"


# --- build --------------------------------------------------------------------------------------------------------

def build(root, out, builders=BUILDERS, tag_check=True):
    """Verify every input of the chosen builders, build in a temporary folder, then replace out in one step."""
    root, out = Path(root), Path(out)
    keys = set().union(*builders.values())
    verify(root, keys, tag_check)
    read, files, numbers = Inputs(root), {}, {}
    KEY.clear()
    for builder in builders:
        built, named = builder(read)
        clashes = (set(files) & set(built)) | (set(numbers) & set(named))
        if clashes:
            raise ValueError(f"{builder.__name__}: duplicate outputs {sorted(clashes)}")
        files, numbers = files | built, numbers | named
    files["tables/key.tex"] = key_table()
    files["tables/numbers.tex"] = "\n".join(["% Generated by paper_ieee/scripts/make_artifacts.py; do not edit."]
                                            + [macro(name, value, source) for name, (value, source) in sorted(numbers.items())]) + "\n"
    files = layout(files)
    files["MACROS_RESULTS.md"] = macro_sheet({name: (re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "{,}", str(value)), source)
                                              for name, (value, source) in numbers.items()})
    manifest = [f"{hashlib.sha256(text.encode('utf-8')).hexdigest()}  {path}" for path, text in sorted(files.items())]
    manifest += ["", "inputs:"] + [f"{hashlib.sha256(read.raw(key)).hexdigest()}  {INPUTS[key]}" + (f" (as tagged {TAG})" if key in TAGGED_INPUTS else "")
                                    + (f" ({CHECKSUMS_LOCK})" if key in AFTER_TAG else "") for key in sorted(keys)]
    files["MANIFEST.txt"] = "\n".join(manifest) + "\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".generated-", dir=out.parent))
    try:
        for path, text in files.items():
            (staging / path).parent.mkdir(parents=True, exist_ok=True)
            (staging / path).write_text(text, encoding="utf-8", newline="\n")
        if out.exists():
            shutil.rmtree(out)
        staging.rename(out)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return sorted(files)


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--root", type=Path, default=PROJECT, help="project root holding the inputs and the checksum file")
    arg_parser.add_argument("--out", type=Path, help=f"output folder (default: <root>/{OUTPUT})")
    arg_parser.add_argument("--no-tag-check", action="store_true", help=f"skip the {TAG} check (tests on fake data only)")
    args = arg_parser.parse_args()
    if not args.no_tag_check:
        check_tag(args.root)
    written = build(args.root, args.out or args.root / OUTPUT, tag_check=not args.no_tag_check)
    print(f"{len(written)} files written to {args.out or args.root / OUTPUT}")


if __name__ == "__main__":
    main()
