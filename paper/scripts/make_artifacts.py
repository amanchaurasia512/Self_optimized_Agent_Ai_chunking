"""Paper 1 artifacts (spec/paper_build_spec.md): every table body, figure and inline number, generated from frozen
result files only. Every input is checked against docs/paper_checksums.txt before anything is read; outputs go to
paper/generated/ only and are byte-identical between runs. Refuses to run before the paper-v1.1 tag (the checksum
file must equal the tagged one) unless --no-tag-check, which the tests use on fake data."""
import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from scripts.aq_run import BUDGET, RECALL_RUNS, cohen_kappa
from scripts.golden_check import wilson
from scripts.p3_fixedk import MEASURES, best_sizes
from scripts.p4_analyse import in_scope
from src.eval.stats import RESAMPLES

PROJECT = Path(__file__).resolve().parents[2]
TAG, CHECKSUMS, OUTPUT = "paper-v1.1", "docs/paper_checksums.txt", "paper/generated"
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
    "manual": "paper/data/manual_facts.csv",
}


class Inputs:
    """Read access to the verified inputs by key, relative to a project root."""

    def __init__(self, root):
        self.root = Path(root)

    def path(self, key):
        return self.root / INPUTS[key]

    def csv(self, key, **options):
        return pd.read_csv(self.path(key), **options)

    def json(self, key):
        return json.loads(self.path(key).read_text(encoding="utf-8"))

    def jsonl(self, key):
        return pd.DataFrame([json.loads(line) for line in self.path(key).read_text(encoding="utf-8").splitlines()])


# --- checks -------------------------------------------------------------------------------------------------------

def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def listed_checksums(text):
    """path -> SHA-256 from a sha256sum file; comment and blank lines skipped."""
    entries = [line.split(maxsplit=1) for line in text.splitlines() if line.strip() and not line.startswith("#")]
    return {path.lstrip("*").strip(): digest for digest, path in entries}


def verify(root, keys):
    """Exit with every problem listed if an input is not in the checksum file, is missing, or differs from it."""
    listed = listed_checksums((Path(root) / CHECKSUMS).read_text(encoding="utf-8"))
    problems = []
    for key in sorted(keys):
        relative = INPUTS[key]
        path = Path(root) / relative
        if relative not in listed:
            problems.append(f"not in {CHECKSUMS}: {relative}")
        elif not path.exists():
            problems.append(f"missing: {relative}")
        elif (actual := sha256(path)) != listed[relative]:
            problems.append(f"checksum mismatch: {relative}\n  listed {listed[relative]}\n  actual {actual}")
    if problems:
        raise SystemExit("inputs failed verification; nothing written:\n" + "\n".join(problems))


def check_tag(root):
    """The checksum file must equal its version at the paper-v1.1 tag (results frozen at the tag)."""
    try:
        tagged = subprocess.run(["git", "-C", str(root), "show", f"{TAG}:{CHECKSUMS}"], capture_output=True, check=True).stdout
    except subprocess.CalledProcessError:
        raise SystemExit(f"tag {TAG} (with {CHECKSUMS}) not found: results are not frozen yet; nothing run")
    if tagged != (Path(root) / CHECKSUMS).read_bytes():
        raise SystemExit(f"{CHECKSUMS} differs from its version at {TAG}; nothing run")


# --- formatting ---------------------------------------------------------------------------------------------------

def fixed(value, places=3):
    text = f"{value:.{places}f}"
    return f"$-${text[1:]}" if text.startswith("-") else text


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


def letters(text):
    """A LaTeX-safe macro part: digits spelled out, other characters dropped, words capitalised."""
    words = re.split(r"[^A-Za-z0-9]+", "".join(f" {DIGITS[char]} " if char.isdigit() else char for char in str(text)))
    return "".join(word[:1].upper() + word[1:] for word in words if word)


def macro(name, value, source=""):
    if not re.fullmatch(r"[A-Za-z]+", name):
        raise ValueError(f"macro name must be letters only: {name}")
    return f"\\newcommand{{\\{name}}}{{{value}}}" + (f"  % {source}" if source else "")


def tabular(columns, header, rows):
    lines = [f"\\begin{{tabular}}{{{columns}}}", r"\toprule", " & ".join(header) + r" \\", r"\midrule"]
    lines += [" & ".join(str(cell) for cell in row) + r" \\" for row in rows]
    return "\n".join(lines + [r"\bottomrule", r"\end{tabular}", ""])


def coordinates(points, x_places=1, y_places=3):
    return " ".join(f"({x:.{x_places}f},{y:.{y_places}f})" if not isinstance(x, str) else f"({x},{y:.{y_places}f})"
                    for x, y in points)


# --- builders: each returns ({generated path: text}, {macro name: (value, source)}) --------------------------------

def rq1(read):
    record = read.json("p4_final")["stack"]["summary"]
    setups = read.csv("p4_primary", index_col=0)
    tuning = read.csv("tuning_p4")
    winner = tuning[(tuning["variant"] == "all tuning") & (tuning["scope"] == "primary")]["best_single"].iloc[0]
    rank = setups["recall"].rank(ascending=False, method="min")
    rows, numbers = [], {}
    for scope in ("primary", "full", "original"):
        summary = record[scope]
        low, high = summary["gap_interval"]
        rows.append([scope, summary["setups"], summary["documents"], summary["questions"], setup_name(summary["best_single"]),
                     fixed(summary["best_single_recall"]), summary["tied_with_best"], fixed(summary["oracle"]),
                     f"{fixed(summary['gap'])} {interval(low, high)}", "GO" if low > 0 else "NO-GO"])
        name = letters(scope)
        numbers |= {f"RQone{name}Gap": (fixed(summary["gap"]), INPUTS["p4_final"]),
                    f"RQone{name}GapCI": (interval(low, high), INPUTS["p4_final"])}
    primary = record["primary"]
    numbers |= {name: (value, INPUTS["p4_final"]) for name, value in {
        "RQoneSetups": primary["setups"], "RQoneDocuments": primary["documents"], "RQoneQuestions": primary["questions"],
        "RQoneBest": setup_name(primary["best_single"]), "RQoneBestRecall": fixed(primary["best_single_recall"]),
        "RQoneTied": primary["tied_with_best"], "RQoneOracle": fixed(primary["oracle"]),
        "RQoneDecision": "GO" if primary["gap_interval"][0] > 0 else "NO-GO"}.items()}
    numbers |= {"RQoneTuningWinner": (setup_name(winner), INPUTS["tuning_p4"]),
                "RQoneTuningWinnerRecall": (fixed(setups.loc[winner, "recall"]), INPUTS["p4_primary"]),
                "RQoneTuningWinnerRank": (int(rank[winner]), INPUTS["p4_primary"]),
                "RQoneTuningWinnerTied": ("tied" if setups.loc[winner, "tied_with_best"] else "not tied", INPUTS["p4_primary"])}
    header = ["Choice set", "Setups", "Docs", "Questions", "Best single", "Recall", "Tied", "Oracle", r"Gap [95\%]", "Rule"]
    return {"tables/rq1.tex": tabular("lrrrlrrrll", header, rows)}, numbers


def rq2(read):
    size = read.csv("size_tuning")
    size = size[size["budget"] == 1250]
    plots = []
    for parser in ("docling", "pdfplumber"):
        part = size[size["parser"] == parser]
        plots.append(f"\\nextgroupplot[title={{{parser.capitalize()}}}]")
        for index, (source, group) in enumerate(part.groupby("source")):
            points = group.sort_values(["chunk_size", "setting"])[["chunk_size", "recall"]].itertuples(index=False)
            plots.append(f"\\addplot+[only marks, mark={MARKS[index % len(MARKS)]}] coordinates {{{coordinates(points)}}};")
            if parser == "docling":
                plots.append(f"\\addlegendentry{{{escape(source)}}}")
    figure = "\n".join([r"\begin{tikzpicture}",
                        r"\begin{groupplot}[group style={group size=2 by 1, horizontal sep=1.8cm}, width=0.5\textwidth,"
                        r" height=5.5cm, xlabel={Mean chunk size (tokens)}, ylabel={Recall@1,250},"
                        r" legend style={at={(0.02,0.02)}, anchor=south west}]", *plots, r"\end{groupplot}", r"\end{tikzpicture}", ""])
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
    plots, numbers = [], {"RQthreeSettingsKept": (len(kept), INPUTS["fixedk"]),
                          "RQthreeSettingsLeftOut": (frame["setting"].nunique() - len(kept), INPUTS["fixedk"])}
    for index, (parser, table) in enumerate(fixedk_tables(frame[frame["setting"].isin(kept)]).items()):
        sizes, details = best_sizes(table)
        details = details.rename(columns={"best setting": "best", "chunk tokens": "tokens"})
        points = [(labels[measure], sizes.loc["all settings", measure]) for measure in MEASURES]
        plots += [f"\\addplot+[mark={MARKS[index]}] coordinates {{{coordinates(points, y_places=0)}}};", f"\\addlegendentry{{{parser.capitalize()}}}"]
        for row in details[details["scope"] == "all settings"].itertuples(index=False):
            name = f"RQthree{letters(parser)}{letters(row.measure)}"
            numbers |= {f"{name}Best": (setup_name(row.best), INPUTS["fixedk"]), f"{name}Score": (fixed(row.score), INPUTS["fixedk"]),
                        f"{name}Size": (row.tokens, INPUTS["fixedk"])}
    figure = "\n".join([r"\begin{tikzpicture}",
                        f"\\begin{{axis}}[width=\\columnwidth, height=5.5cm, symbolic x coords={{{','.join(labels[m] for m in MEASURES)}}},"
                        r" xtick=data, ylabel={Best chunk size (tokens)}, legend style={at={(0.98,0.98)}, anchor=north east}]",
                        *plots, r"\end{axis}", r"\end{tikzpicture}", ""])
    return {"figures/rq3.tex": figure}, numbers


def interval_plot(rows, title, ylabel_width):
    """One axis of differences with asymmetric 95% intervals, one row per comparison; filled marks pass Holm."""
    names = [name for name, *rest in rows]
    lines = [f"\\nextgroupplot[title={{{title}}}, symbolic y coords={{{','.join(names)}}}, ytick=data,"
             f" y tick label style={{text width={ylabel_width}, align=right}}]",
             r"\draw[dashed] (axis cs:0,\pgfkeysvalueof{/pgfplots/ymin}) -- (axis cs:0,\pgfkeysvalueof{/pgfplots/ymax});"]
    for passed in (True, False):
        chosen = [(name, difference, low, high) for name, difference, low, high, passes in rows if passes == passed]
        if chosen:
            points = " ".join(f"({difference:.3f},{name}) -= ({difference - low:.3f},0) += ({high - difference:.3f},0)"
                              for name, difference, low, high in chosen)
            lines.append(f"\\addplot+[only marks, mark={'*' if passed else 'o'}, error bars/.cd, x dir=both, x explicit]"
                         f" coordinates {{{points}}};")
    return lines


def rq5(read):
    chunker, digital, scanned = read.csv("rq5_chunker"), read.csv("rq5_digital"), read.csv("rq5_scanned")
    chunker_rows = [(f"{escape(row.family)} ({row.parser})", row.difference, row.low, row.high, bool(row.beats_default))
                    for row in chunker.sort_values(["family", "parser"]).itertuples(index=False)]
    digital_rows = [(escape(row.variant), row.difference, row.low, row.high, bool(row.beats_default))
                    for row in digital.sort_values("variant").itertuples(index=False)]
    figure = "\n".join([r"\begin{tikzpicture}",
                        r"\begin{groupplot}[group style={group size=2 by 1, horizontal sep=4.2cm}, width=0.36\textwidth,"
                        r" height=6cm, xlabel={Recall difference (tuned $-$ default)}]",
                        *interval_plot(chunker_rows, "(b) Chunk size", "3.6cm"),
                        *interval_plot(digital_rows, "(a) Parser settings, digital", "3.6cm"),
                        r"\end{groupplot}", r"\end{tikzpicture}", ""])
    numbers = {}
    for row in chunker.itertuples(index=False):
        name = f"RQfiveB{letters(row.family)}{letters(row.parser)}"
        numbers |= {f"{name}Default": (fixed(row.default_recall), INPUTS["rq5_chunker"]), f"{name}Tuned": (fixed(row.tuned_recall), INPUTS["rq5_chunker"]),
                    f"{name}Diff": (fixed(row.difference), INPUTS["rq5_chunker"]), f"{name}CI": (interval(row.low, row.high), INPUTS["rq5_chunker"]),
                    f"{name}Holm": (holm_text(row.holm_p, len(chunker)), INPUTS["rq5_chunker"])}
    scan = scanned.iloc[0]
    numbers |= {"RQfiveBComparisons": (len(chunker), INPUTS["rq5_chunker"]),
                "RQfiveADigitalMaxAbsDiff": (fixed(digital["difference"].abs().max()), INPUTS["rq5_digital"]),
                "RQfiveADigitalMinHolm": (fixed(digital["holm_p"].min(), 2), INPUTS["rq5_digital"]),
                "RQfiveADigitalQuestions": (f"{digital['questions'].min()}--{digital['questions'].max()}", INPUTS["rq5_digital"]),
                "RQfiveAScannedDiff": (fixed(scan["difference"], 2), INPUTS["rq5_scanned"]),
                "RQfiveAScannedCI": (interval(scan["low"], scan["high"], 2), INPUTS["rq5_scanned"]),
                "RQfiveAScannedHolm": (fixed(scan["holm_p"], 2), INPUTS["rq5_scanned"])}
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


def rq4(read):
    setups, versus = read.csv("aq_held_out"), read.csv("aq_held_out_vs_best")
    best = setups.loc[setups["f1"].idxmax()]
    rows = [[setup_name(f"{row.parser}/{row.setting}"), fixed(row.difference), interval(row.low, row.high), holm_text(row.holm_p, len(versus))]
            for row in versus.sort_values("difference", ascending=False).itertuples(index=False)]
    tuning = read.csv("aq_tuning_vs_best")
    numbers = {"RQfourBest": (setup_name(f"{best.parser}/{best.setting}"), INPUTS["aq_held_out"]),
               "RQfourBestFOne": (fixed(best.f1), INPUTS["aq_held_out"]),
               "RQfourComparisons": (len(versus), INPUTS["aq_held_out_vs_best"]),
               "RQfourTuningMinHolm": (fixed(tuning["holm_p"].min(), 2), INPUTS["aq_tuning_vs_best"])}
    for split, key in (("tuning", "scores_tuning"), ("held_out", "scores_held_out")):
        spearman = aq_spearman(read, split, key)
        numbers |= {f"RQfourSpearman{letters(split)}FOne": (fixed(spearman["f1"], 2), f"{INPUTS['aq_f1']}, {INPUTS[key]}"),
                    f"RQfourSpearman{letters(split)}Judge": (fixed(spearman["judge_secondary"], 2), f"{INPUTS['aq_judgements']}, {INPUTS[key]}")}
    agreement, kappa, cases = judge_second_pass(read)
    numbers |= {"JudgeSecondAgreement": (f"{agreement:.0%}".replace("%", r"\%"), INPUTS["judge_check"]),
                "JudgeSecondKappa": (fixed(kappa, 2), INPUTS["judge_check"]), "JudgeCases": (cases, INPUTS["judge_check"])}
    header = ["Setup (against the best)", "F1 difference", r"95\% interval", "Holm $p$"]
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
                rows.append([split, parser, setup_name(setting), fixed(row["chunks"], 1), f"{row['index_tokens']:,.0f}",
                             f"{row['index_tokens'] / row['chunks']:.0f}", fixed(row["recall"])])
    header = ["Split", "Parser", "Setting", "Chunks", "Index tokens", "Tokens / chunk", "Recall"]
    return {"tables/a1_index_cost.tex": tabular("lllrrrr", header, rows)}, {}


def a2_retrievers(read):
    summary = read.csv("retrievers")
    primary = summary[summary["scope"] == "primary"].sort_values(["split", "retriever"], ascending=[False, True])
    rows = [[escape(row.split), row.retriever, setup_name(row.best_single), fixed(row.best_recall), row.tied,
             f"{fixed(row.gap)} {interval(row.gap_low, row.gap_high)}", "GO" if row.go else "NO-GO"] for row in primary.itertuples(index=False)]
    header = ["Split", "Retriever", "Best single", "Recall", "Tied", r"Gap [95\%]", "Rule"]
    return {"tables/a2_retrievers.tex": tabular("lllrrll", header, rows)}, {}


def a5_compute(read):
    compute = read.csv("compute").groupby("group")[["gpu_hours", "cpu_hours", "chunker_llm_calls", "aq_answer_calls", "agent_answer_calls", "paid_credits"]].sum()
    labels = {"gpu_hours": "GPU hours", "cpu_hours": "CPU hours", "chunker_llm_calls": "LLM calls, chunkers",
              "aq_answer_calls": "LLM calls, AQ answers (recorded)", "agent_answer_calls": "LLM calls, agent", "paid_credits": "LlamaParse credits"}
    groups = sorted(compute.index)
    rows = [[label] + [fixed(compute.loc[group, column], 1) if "hours" in column else f"{compute.loc[group, column]:,.0f}" for group in groups]
            for column, label in labels.items()]
    return {"tables/a5_compute.tex": tabular("l" + "r" * len(groups), [""] + [escape(group) for group in groups], rows)}, {}


def a6_no_indian(read):
    rows = []
    for split, key in (("Tuning", "tuning_p4"), ("Held-out", "held_out_no_indian")):
        for row in read.csv(key).itertuples(index=False):
            rows.append([split, escape(row.variant), row.scope, f"{row.documents} / {row.questions}", setup_name(row.best_single),
                         fixed(row.best_recall), row.tied, f"{fixed(row.gap)} {interval(row.gap_low, row.gap_high)}", "GO" if row.go else "NO-GO"])
    header = ["Split", "Documents", "Scope", "Docs / q.", "Best single", "Recall", "Tied", r"Gap [95\%]", "Rule"]
    return {"tables/a6_no_indian.tex": tabular("lllrlrrll", header, rows)}, {}


def a7_golden(read):
    labels = read.csv("golden_labels", dtype=str, keep_default_na=False).merge(read.csv("golden_sample", dtype={"question_id": str}), on=["doc_id", "question_id"])
    rows, numbers = [], {}
    for doc, group in [*sorted(labels.groupby("doc_id")), ("Overall", labels)]:
        total, invalid, unsure = len(group), int((group["label"] == "invalid").sum()), int((group["label"] == "unsure").sum())
        rows.append([escape(doc), total, invalid, f"{fixed(invalid / total)} {interval(*wilson(invalid, total))}", unsure,
                     f"{fixed((invalid + unsure) / total)} {interval(*wilson(invalid + unsure, total))}"])
        name = f"Golden{letters(doc)}"
        numbers |= {f"{name}Invalid": (invalid, INPUTS["golden_labels"]), f"{name}Labelled": (total, INPUTS["golden_labels"]),
                    f"{name}Rate": (fixed(invalid / total), INPUTS["golden_labels"]), f"{name}RateCI": (interval(*wilson(invalid, total)), INPUTS["golden_labels"]),
                    f"{name}Unsure": (unsure, INPUTS["golden_labels"])}
    header = ["Document", "Labelled", "Invalid", r"Rate [95\%]", "Unsure", r"Invalid or unsure [95\%]"]
    return {"tables/a7_golden.tex": tabular("lrrlrl", header, rows)}, numbers


def manual(read):
    """Typed numbers that cannot be recomputed (spec/paper_build_spec.md, section 6), each with its source."""
    facts = read.csv("manual", dtype=str, keep_default_na=False)
    return {}, {f"Manual{letters(row.key)}": (escape(row.value), f"{row.source_file} @ {row.source_commit}") for row in facts.itertuples(index=False)}


BUILDERS = {
    rq1: {"p4_final", "p4_primary", "tuning_p4"},
    rq2: {"size_tuning", "size_tuning_summary", "size_final_summary"},
    rq3: {"fixedk"},
    rq4: {"aq_held_out", "aq_held_out_vs_best", "aq_tuning_vs_best", "aq_f1", "aq_judgements", "scores_tuning", "scores_held_out",
          "judge_check", "judge_check_keys"},
    rq5: {"rq5_chunker", "rq5_digital", "rq5_scanned"},
    coverage: {"gold_drop_tuning", "gold_drop_final", "split", "p4_primary_documents"},
    a1_index_cost: {"p4_tuning_full", "p4_full"},
    a2_retrievers: {"retrievers"},
    a5_compute: {"compute"},
    a6_no_indian: {"tuning_p4", "held_out_no_indian"},
    a7_golden: {"golden_labels", "golden_sample"},
    manual: {"manual"},
}


# --- build --------------------------------------------------------------------------------------------------------

def build(root, out, builders=BUILDERS):
    """Verify every input of the chosen builders, build in a temporary folder, then replace out in one step."""
    root, out = Path(root), Path(out)
    keys = set().union(*builders.values())
    verify(root, keys)
    read, files, numbers = Inputs(root), {}, {}
    for builder in builders:
        built, named = builder(read)
        clashes = (set(files) & set(built)) | (set(numbers) & set(named))
        if clashes:
            raise ValueError(f"{builder.__name__}: duplicate outputs {sorted(clashes)}")
        files, numbers = files | built, numbers | named
    files["tables/numbers.tex"] = "\n".join(["% Generated by paper/scripts/make_artifacts.py; do not edit."]
                                            + [macro(name, value, source) for name, (value, source) in sorted(numbers.items())]) + "\n"
    manifest = [f"{hashlib.sha256(text.encode('utf-8')).hexdigest()}  {path}" for path, text in sorted(files.items())]
    manifest += ["", "inputs:"] + [f"{sha256(root / INPUTS[key])}  {INPUTS[key]}" for key in sorted(keys)]
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
    written = build(args.root, args.out or args.root / OUTPUT)
    print(f"{len(written)} files written to {args.out or args.root / OUTPUT}")


if __name__ == "__main__":
    main()
