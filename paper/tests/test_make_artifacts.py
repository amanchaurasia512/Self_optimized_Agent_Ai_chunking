"""paper/scripts/make_artifacts.py and check_sources.py on fake data in pytest's temporary folder: checksum
verification, the paper-v1.1 tag guard, atomic and deterministic output, formatting, the fixed-k filter (spec Errata
2026-11-14), every builder, and the source checks. One test compares with RESULTS.md on the real files; it is skipped
until the paper-v1.1 tag exists (results are not read before the tag)."""
import gzip
import hashlib
import json
import subprocess

import pandas as pd
import pytest

from paper.scripts import check_sources
from paper.scripts import make_artifacts as artifacts

SETUPS = ["docling/langchain_recursive_size256_overlap0_noprefix", "pdfplumber/method1_tree_T384_noprefix"]


def write(root, key, content):
    path = root / artifacts.INPUTS[key]
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, pd.DataFrame):
        content.to_csv(path, index=path.suffix != ".gz" and content.index.name is not None, compression="infer")
    else:
        path.write_text(content, encoding="utf-8")


def frame(rows, index=None):
    table = pd.DataFrame(rows)
    return table.set_index(index) if index else table


def p4_row(variant, scope):
    return {"variant": variant, "": 0, "scope": scope, "setups": 26, "documents": 17, "questions": 530, "best_single": SETUPS[1],
            "best_recall": 0.772, "tied": 15, "oracle": 0.765, "gap": -0.007, "gap_low": -0.045, "gap_high": 0.023, "go": False}


@pytest.fixture
def root(tmp_path):
    summary = {scope: {"setups": 26, "documents": 17, "questions": 530, "best_single": SETUPS[1], "best_single_recall": 0.7715,
                       "tied_with_best": 15, "oracle": 0.765, "gap": gap, "gap_interval": [low, high]}
               for scope, gap, low, high in (("primary", -0.007, -0.045, 0.023), ("full", -0.056, -0.108, -0.010), ("original", -0.042, -0.084, 0.002))}
    write(tmp_path, "p4_final", json.dumps({"stack": {"summary": summary}}))
    write(tmp_path, "p4_primary", frame([{"setup": SETUPS[1], "recall": 0.772, "tied_with_best": True},
                                         {"setup": SETUPS[0], "recall": 0.715, "tied_with_best": True}], "setup"))
    write(tmp_path, "tuning_p4", frame([p4_row(variant, scope) | ({"best_single": SETUPS[0]} if variant == "all tuning" else {})
                                        for variant in ("all tuning", "without Indian") for scope in ("full", "original", "primary")]))
    write(tmp_path, "held_out_no_indian", frame([p4_row(variant, "primary") for variant in ("all held-out", "without Indian")]))
    write(tmp_path, "size_tuning", frame([{"parser": parser, "budget": 1250, "source": source, "setting": f"fixed_token_size{size}_overlap0_noprefix",
                                           "chunk_size": size * 0.98, "recall": 0.9 - size / 2000}
                                          for parser in ("docling", "pdfplumber") for source in ("CUAD", "OHR-Bench") for size in (256, 1024)]))
    summary_rows = [{"parser": "docling", "budget": 1250, "source": source, "documents": 3, "best_setting": "x", "best_size": size, "best_recall": 0.8,
                     "spearman_size_recall": rho} for source, size, rho in (("CUAD", 209, -0.61), ("OHR-Bench", 439, -0.97))]
    write(tmp_path, "size_tuning_summary", frame(summary_rows))
    write(tmp_path, "size_final_summary", frame(summary_rows))
    settings = {"fixed_token_size256_overlap0_noprefix": 256, "fixed_token_size1024_overlap0_noprefix": 1024,
                "method1_tree_T384_prefix_v11": 384, "sanity_random_cut_size512_noprefix": 512}
    write(tmp_path, "fixedk", frame([{"parser": parser, "setting": setting, "doc_id": doc, "question_id": f"{doc}-q", "source": "CUAD",
                                      "chunk_tokens": size, "recall5": size / 1100, "recall10": size / 1050, "hit1": 0.6 if size == 384 else 0.5,
                                      "mrr": 0.7, "recall4000": 1 - size / 3000}
                                     for parser in ("docling", "pdfplumber") for setting, size in settings.items() for doc in ("d1", "d2")]))
    write(tmp_path, "rq5_chunker", frame([{"family": family, "parser": parser, "default": "d", "tuned": "t", "documents": 17, "default_recall": 0.61,
                                           "tuned_recall": 0.733, "difference": 0.123, "low": 0.057, "high": 0.196, "p": 0.0, "holm_p": 0.0,
                                           "beats_default": True} for family in ("langchain_recursive", "method1_tree") for parser in ("docling", "pdfplumber")]))
    write(tmp_path, "rq5_digital", frame([{"variant": "docling_headings", "default": "docling", "documents": 5, "questions": 306, "default_recall": 0.827,
                                           "variant_recall": 0.825, "difference": -0.002, "low": -0.006, "high": 0.0, "p": 0.6, "holm_p": 0.29,
                                           "beats_default": False}]))
    write(tmp_path, "rq5_scanned", frame([{"variant": "docling_ocr_tesseract", "default": "docling", "documents": 8, "questions": 34, "default_recall": 0.765,
                                           "variant_recall": 0.786, "difference": 0.02, "low": -0.05, "high": 0.08, "p": 0.5, "holm_p": 0.5, "beats_default": False}]))
    write(tmp_path, "aq_held_out", frame([{"parser": "docling", "setting": "method1_tree_T256_noprefix", "f1": 0.393},
                                          {"parser": "docling", "setting": "fixed_token_size1024_overlap0_noprefix", "f1": 0.27}]))
    write(tmp_path, "aq_held_out_vs_best", frame([{"parser": "docling", "setting": "fixed_token_size1024_overlap0_noprefix", "documents": 17,
                                                   "difference": 0.1235, "low": 0.05, "high": 0.2102, "p": 0.0, "holm_p": 0.0}]))
    write(tmp_path, "aq_tuning_vs_best", frame([{"parser": "docling", "setting": "x", "documents": 19, "difference": 0.07, "low": -0.03,
                                                 "high": 0.17, "p": 0.17, "holm_p": 1.0}]))
    answers = [{"set": split, "parser": "docling", "setting": f"s{index}", "doc_id": "d1", "question_id": f"q{question}", "f1": index / 10 + question / 100}
               for split in ("tuning", "held_out") for index in range(4) for question in range(3)]
    write(tmp_path, "aq_f1", frame(answers))
    judgements = [{key: row[key] for key in artifacts.KEYS} | {"score": row["f1"]} for row in answers]
    write(tmp_path, "aq_judgements", "\n".join(json.dumps(row) for row in judgements))
    for key in ("scores_tuning", "scores_held_out"):
        write(tmp_path, key, frame([{**{k: row[k] for k in artifacts.KEYS}, "retriever": "hybrid", "budget": 1250, "recall": row["f1"]} for row in answers]))
    write(tmp_path, "judge_check", frame([{"case": case, "question": "q", "reference": "r", "answer": "a", "human": judgements[case]["score"]}
                                          for case in range(4)]))
    write(tmp_path, "judge_check_keys", frame([{"case": case, **{key: judgements[case][key] for key in artifacts.KEYS}} for case in range(4)]))
    drop = [{"gold_file": parser, "split": split, "source": source, "kept": 90, "page_level": 2, "placed_not_certain": 7, "not_placed": 1, "total": 100,
             "drop_rate": 0.08} for parser in ("docling", "pdfplumber") for split in ("tuning", "held_out") for source in ("CUAD", "QASPER")]
    write(tmp_path, "gold_drop_tuning", frame(drop))
    write(tmp_path, "gold_drop_final", frame(drop))
    write(tmp_path, "split", frame([{"doc_id": f"h{index}", "source_dataset": "QASPER" if index < 2 else "CUAD", "split": "held_out", "set": "x"}
                                    for index in range(5)] + [{"doc_id": "t1", "source_dataset": "CUAD", "split": "tuning", "set": "x"}]))
    write(tmp_path, "p4_primary_documents", frame([{"doc_id": f"h{index}"} for index in range(2, 5)]))
    setups = frame([{"setup": f"{parser}/{setting}", "recall": 0.78, "index_tokens": 35789.0, "chunks": 121.2}
                    for parser in ("docling", "pdfplumber") for setting in ("method1_tree_T384_noprefix", "recursive_size384_overlap0_noprefix",
                                                                            "langchain_recursive_size384_overlap0_noprefix")], "setup")
    write(tmp_path, "p4_tuning_full", setups)
    write(tmp_path, "p4_full", setups)
    write(tmp_path, "retrievers", frame([{"split": split, "retriever": retriever, "scope": "primary", "best_single": SETUPS[0], "best_recall": 0.8,
                                          "tied": 20, "gap": -0.001, "gap_low": -0.032, "gap_high": 0.03, "go": False}
                                         for split in ("tuning", "held_out") for retriever in ("bm25", "hybrid")]))
    write(tmp_path, "compute", frame([{"group": group, "phase": "A", "machine": "kaggle", "gpu_hours": 1.25, "cpu_hours": 2.5, "chunker_llm_calls": 3,
                                       "aq_answer_calls": 4, "agent_answer_calls": 5, "input_tokens": 0, "output_tokens": 0, "paid_credits": 6.0,
                                       "records": 1} for group in ("study", "tests")]))
    write(tmp_path, "golden_labels", frame([{"doc_id": "indian_d1", "question_id": f"Q{index}", "label": ["valid", "invalid", "unsure"][index % 3],
                                             "note": "", "labelled_at": "t"} for index in range(6)]))
    write(tmp_path, "golden_sample", frame([{"doc_id": "indian_d1", "question_id": f"Q{index}", "batch": 1, "certain": True} for index in range(6)]))
    write(tmp_path, "manual", "key,value,unit,section,source_file,source_commit,note\njudge_first_pass_kappa,0.48,kappa,5,spec,a6278ca,n\n")
    checksums = [f"{hashlib.sha256((tmp_path / path).read_bytes()).hexdigest()}  {path}" for path in artifacts.INPUTS.values()]
    (tmp_path / "docs").mkdir()
    (tmp_path / artifacts.CHECKSUMS).write_text("# fake\n\n" + "\n".join(checksums) + "\n", encoding="utf-8")
    return tmp_path


def test_full_build_is_deterministic_and_lists_its_inputs(root):
    first = artifacts.build(root, root / "out1")
    artifacts.build(root, root / "out2")
    assert first == artifacts.build(root, root / "out1")  # rebuilding in place works
    for path in first:
        assert (root / "out1" / path).read_bytes() == (root / "out2" / path).read_bytes()
    assert {"tables/rq1.tex", "tables/rq4.tex", "figures/rq2.tex", "figures/rq3.tex", "figures/rq5.tex", "tables/numbers.tex",
            "tables/a1_index_cost.tex", "tables/a7_golden.tex", "MANIFEST.txt"} <= set(first)
    manifest = (root / "out1" / "MANIFEST.txt").read_text()
    assert all(path in manifest for path in artifacts.INPUTS.values())
    assert not list(root.glob(".generated-*"))  # no staging folder left behind


def test_numbers_come_out_formatted(root):
    artifacts.build(root, root / "out")
    numbers = (root / "out" / "tables" / "numbers.tex").read_text()
    for expected in [r"\newcommand{\RQonePrimaryGap}{$-$0.007}", r"\newcommand{\RQonePrimaryGapCI}{[$-$0.045, 0.023]}",
                     r"\newcommand{\RQoneDecision}{NO-GO}", r"\newcommand{\RQoneTuningWinnerRank}{2}",
                     r"\newcommand{\RQfiveBLangchainRecursiveDoclingHolm}{$<$0.01}", r"\newcommand{\RQtwoRhoRange}{$-$0.61 to $-$0.97}",
                     r"\newcommand{\CoverageTuningDoclingLost}{8}", r"\newcommand{\CoverageTuningDoclingTotal}{98}",
                     r"\newcommand{\AccountingHeldOut}{5}", r"\newcommand{\AccountingRemovedQASPER}{2}",
                     r"\newcommand{\GoldenOverallInvalid}{2}", r"\newcommand{\ManualJudgeFirstPassKappa}{0.48}",
                     r"\newcommand{\JudgeSecondAgreement}{100\%}", r"\newcommand{\RQfourSpearmanHeldOutFOne}{1.00}"]:
        assert expected in numbers, expected
    assert "  % data/results" in numbers  # every macro names its source


def test_fixedk_figure_leaves_out_superseded_and_sanity_settings(root):
    artifacts.build(root, root / "out")
    numbers = (root / "out" / "tables" / "numbers.tex").read_text()
    assert r"\newcommand{\RQthreeSettingsKept}{2}" in numbers and r"\newcommand{\RQthreeSettingsLeftOut}{2}" in numbers
    assert "v11" not in numbers and "sanity" not in numbers  # the v11 setting would win Hit@1 if it were kept
    assert "R@4000" in (root / "out" / "figures" / "rq3.tex").read_text()


def test_checksum_mismatch_stops_before_writing(root):
    (root / "out").mkdir()
    (root / "out" / "old.tex").write_text("old")
    (root / artifacts.INPUTS["rq5_chunker"]).write_text("changed")
    with pytest.raises(SystemExit, match="checksum mismatch: data/results/rq5"):
        artifacts.build(root, root / "out")
    assert (root / "out" / "old.tex").read_text() == "old"  # old outputs kept


def test_input_not_listed_or_missing_stops(root):
    listed = (root / artifacts.CHECKSUMS).read_text()
    (root / artifacts.CHECKSUMS).write_text("\n".join(line for line in listed.splitlines() if "golden_check/labels" not in line))
    with pytest.raises(SystemExit, match="not in docs/paper_checksums.txt: data/results/golden_check/labels.csv"):
        artifacts.build(root, root / "out")
    (root / artifacts.CHECKSUMS).write_text(listed)
    (root / artifacts.INPUTS["split"]).unlink()
    with pytest.raises(SystemExit, match="missing: pdfs/split.csv"):
        artifacts.build(root, root / "out")


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_tag_guard(root):
    git(root, "init", "-q")
    with pytest.raises(SystemExit, match="tag paper-v1.1"):
        artifacts.check_tag(root)
    git(root, "add", artifacts.CHECKSUMS)
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "c")
    git(root, "tag", artifacts.TAG)
    artifacts.check_tag(root)  # equal to the tagged file: allowed
    with open(root / artifacts.CHECKSUMS, "a") as handle:
        handle.write("0" * 64 + "  extra\n")
    with pytest.raises(SystemExit, match="differs from its version"):
        artifacts.check_tag(root)


def test_formatting_helpers():
    assert artifacts.fixed(-0.0071) == "$-$0.007" and artifacts.fixed(0.5, 1) == "0.5"
    assert artifacts.holm_text(0.0, 8) == "$<$0.01" and artifacts.holm_text(0.036, 6) == "0.036"
    assert artifacts.setup_name("pdfplumber/method1_tree_T384_noprefix") == r"pdfplumber / method1\_tree T384"
    assert artifacts.setup_name("docling/langchain_recursive_size256_overlap0_noprefix") == r"docling / langchain\_recursive 256"
    assert artifacts.letters("indian_d1") == "IndianDOne" and artifacts.letters("held_out") == "HeldOut"
    with pytest.raises(ValueError):
        artifacts.macro("RQ1Gap", "x")


def test_real_inputs_exist():
    missing = [path for path in artifacts.INPUTS.values() if not (artifacts.PROJECT / path).exists()]
    assert not missing, missing


def paper_tree(tmp_path, sections):
    (tmp_path / "sections").mkdir(parents=True)
    (tmp_path / "generated" / "tables").mkdir(parents=True)
    (tmp_path / "main.tex").write_text("")
    (tmp_path / "generated" / "tables" / "numbers.tex").write_text("\\newcommand{\\RQoneGap}{x}\n\\newcommand{\\OnlyHere}{y}\n")
    for name, text in sections.items():
        (tmp_path / "sections" / name).write_text(text)
    return tmp_path


def test_source_checks(tmp_path):
    clean = paper_tree(tmp_path / "clean", {"results.tex": "Gap \\RQoneGap at Recall@1,250 (RQ1, \\label{sec:rq1}). % 0.007 in a comment\n",
                                            "limitations.tex": "Only \\RQoneGap documents.\n"})
    assert check_sources.check(clean) == []
    bad = paper_tree(tmp_path / "bad", {"results.tex": "The gap is 0.007 and 70\\% agree.\n\\footnotesize\n",
                                        "limitations.tex": "New: \\OnlyHere.\n"})
    problems = "\n".join(check_sources.check(bad))
    assert "typed number" in problems and "\\OnlyHere appears in no other section" in problems and "\\footnotesize" in problems


def tag_exists():
    return subprocess.run(["git", "-C", str(artifacts.PROJECT), "rev-parse", "-q", "--verify", f"refs/tags/{artifacts.TAG}"],
                          capture_output=True).returncode == 0


@pytest.mark.skipif(not tag_exists(), reason="real results are read only after the paper-v1.1 tag")
def test_real_numbers_match_results_md(tmp_path):
    artifacts.check_tag(artifacts.PROJECT)
    artifacts.build(artifacts.PROJECT, tmp_path / "generated")
    numbers = (tmp_path / "generated" / "tables" / "numbers.tex").read_text()
    for name, value in {"RQoneBestRecall": "0.772", "RQoneTied": "15", "RQonePrimaryGap": "$-$0.007", "RQonePrimaryGapCI": "[$-$0.045, 0.023]",
                        "RQoneFullGap": "$-$0.056", "RQoneTuningWinnerRank": "20", "RQfourBestFOne": "0.393",
                        "RQfourSpearmanTuningFOne": "0.75", "RQfourSpearmanHeldOutFOne": "0.43", "RQfourSpearmanTuningJudge": "0.75",
                        "RQfourSpearmanHeldOutJudge": "0.64", "JudgeSecondAgreement": "95\\%", "JudgeSecondKappa": "0.86",
                        "CoverageTuningDoclingLost": "84", "CoverageTuningDoclingTotal": "970", "CoverageHeldOutPdfplumberLost": "205",
                        "AccountingHeldOut": "31", "AccountingMain": "17", "RQthreeDoclingHitOneScore": "0.622",
                        "RQthreeDoclingMrrScore": "0.742", "GoldenOverallInvalid": "20", "RQthreeSettingsKept": "50"}.items():
        assert f"\\newcommand{{\\{name}}}{{{value}}}" in numbers, name
