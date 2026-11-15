"""paper/scripts/make_artifacts.py and check_sources.py on fake data in pytest's temporary folder: checksum
verification, the paper tag guard, atomic and deterministic output, formatting, the fixed-k filter (spec Errata
2026-11-14), every builder, and the source checks. One test compares with RESULTS.md on the real files; it is skipped
until the paper tag (artifacts.TAG) exists (results are not read before the tag)."""
import gzip
import hashlib
import json
import re
import subprocess

import pandas as pd
import pytest

from paper.scripts import check_sources
from paper.scripts import make_artifacts as artifacts

SETUPS = ["docling/langchain_recursive_size256_overlap0_noprefix", "pdfplumber/method1_tree_T384_noprefix"]
# without the paper tag the deviations builder reads this instead of the tagged spec: each anchor as its own line
REAL_SPEC_STAND_IN = "\n".join(dict.fromkeys(anchor for kind, anchors, summary in artifacts.DEVIATIONS for anchor in anchors))  # two rows may share an anchor


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


COMMITS = {"607d29c": "2026-10-26T21:57:51+05:30", "de4aff3": "2026-11-01T18:49:27+05:30", "b1bd7d1": "2026-11-03T14:54:33+05:30",
           "448173c": "2026-11-05T11:21:57+05:30"}
ADDED = {"spec/spec_v1.md": "607d29c", "spec/spec_v1.1.md": "de4aff3", "spec/spec_v1.2.md": "b1bd7d1"}


def fake_git(self, *args):
    """rev-parse: a ref padded to a full hash (a tag name becomes a fixed hash); rev-list: the pushed commit only."""
    if args[0] == "rev-parse":
        ref = args[1].split("^")[0]
        return (ref if all(char in "0123456789abcdef" for char in ref) else "abcdef1").ljust(40, "0")
    if args[0] == "rev-list":
        return args[1].split("..")[-1]
    raise AssertionError(f"unexpected git call in the fake folder: {args}")


SANITY_LOG = """TEST 1 floor: random cut vs the best setting (Recall@1,250, mean [95% interval])
  FAIL docling    bm25   random 0.635 [0.540-0.731] vs best sentence_sentences5_noprefix 0.790 [0.706-0.863]
  FAIL pdfplumber hybrid random 0.636 [0.543-0.727] vs best fixed_token_size256_overlap0_noprefix 0.781 [0.695-0.864]

TEST 2 damage: table questions on Docling: 112 (documents: 11)
  PASS bm25   table questions: split 0.703 vs method 1 0.786 | other questions: split 0.822 vs method 1 0.821
  PASS hybrid table questions: split 0.707 vs method 1 0.804 | other questions: split 0.849 vs method 1 0.841
"""


@pytest.fixture
def root(tmp_path, monkeypatch):
    # the fake folder is no git repository: commit times, first-add commits and the scorer tag come from these tables
    monkeypatch.setattr(artifacts.Inputs, "commit_time",
                        lambda self, commit: artifacts.datetime.fromisoformat(COMMITS.get(commit[:7], "2026-11-15T10:00:00+05:30")))
    monkeypatch.setattr(artifacts.Inputs, "git", fake_git)
    monkeypatch.setattr(artifacts.Inputs, "added_in", lambda self, path: ADDED[path])
    monkeypatch.setattr(artifacts.Inputs, "tag_commit", lambda self, tag: "448173c")
    monkeypatch.setattr(artifacts.Inputs, "changed_since_tag", lambda self, paths: [])
    # the deviations table reads the real spec at the paper tag (read-only); skipped tests below need no tag
    tagged = artifacts.Inputs.tagged_file  # the real method, kept before patching
    monkeypatch.setattr(artifacts.Inputs, "tagged_file", lambda self, path: tagged(artifacts.Inputs(artifacts.PROJECT), path)
                        if tag_exists() else REAL_SPEC_STAND_IN)
    summary = {scope: {"setups": 26, "documents": 17, "questions": 530, "best_single": SETUPS[1], "best_single_recall": 0.7715,
                       "tied_with_best": 15, "oracle": 0.765, "gap": gap, "gap_interval": [low, high], "raw_gap": 0.058}
               for scope, gap, low, high in (("primary", -0.007, -0.045, 0.023), ("full", -0.056, -0.108, -0.010), ("original", -0.042, -0.084, 0.002))}
    write(tmp_path, "p4_final", json.dumps({"run_id": "P4-FINAL-20261106-1", "created_at": "2026-11-06T09:59:07+00:00",
                                            "stack": {"summary": summary, "resamples": 2000, "level": 0.95, "splits": 200}}))
    write(tmp_path, "sanity_log", SANITY_LOG)
    write(tmp_path, "chunking_final_record", json.dumps({"run_id": "P2-P4-KN01-20261105-1", "created_at": "2026-11-05T19:14:05+00:00"}))
    push = {"activity_type": "push", "ref": "refs/heads/main", "before": artifacts.ZERO, "after": "607d29c".ljust(40, "0"),
            "timestamp": "2026-10-26T16:28:16Z"}
    write(tmp_path, "github_page1", json.dumps([push]))
    write(tmp_path, "github_page2", json.dumps([]))
    others = [f"{parser}/{setting}" for parser, setting in [("docling", "method1_tree_T384_noprefix"),
              ("pdfplumber", "langchain_recursive_size256_overlap0_noprefix"), ("docling", "sentence_sentences5_noprefix"),
              ("pdfplumber", "sentence_sentences5_noprefix")]]
    write(tmp_path, "p4_primary", frame([{"setup": SETUPS[1], "recall": 0.772, "tied_with_best": True},
                                         {"setup": SETUPS[0], "recall": 0.715, "tied_with_best": True}]
                                        + [{"setup": setup, "recall": 0.70 - index / 100, "tied_with_best": False}
                                           for index, setup in enumerate(others)], "setup"))
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
                                           "beats_default": False}]
                                         + [{"variant": variant, "default": "pdfplumber", "documents": 5, "questions": questions,
                                             "default_recall": recall, "variant_recall": 0.79, "difference": -0.007, "low": -0.019,
                                             "high": 0.002, "p": 0.2, "holm_p": 0.29, "beats_default": False}
                                            for variant, questions, recall in (("pdfplumber_layout", 307, 0.7977), ("pdfplumber_tolerance_wide", 308, 0.7971))]))
    write(tmp_path, "rq5_scanned", frame([{"variant": "docling_ocr_tesseract", "default": "docling", "documents": 8, "questions": 34, "default_recall": 0.765,
                                           "variant_recall": 0.786, "difference": 0.02, "low": -0.05, "high": 0.08, "p": 0.5, "holm_p": 0.5, "beats_default": False}]))
    write(tmp_path, "aq_held_out", frame([{"parser": "docling", "setting": "method1_tree_T256_noprefix", "f1": 0.393},
                                          {"parser": "docling", "setting": "fixed_token_size1024_overlap0_noprefix", "f1": 0.27}]))
    write(tmp_path, "aq_held_out_vs_best", frame([{"parser": "docling", "setting": "fixed_token_size1024_overlap0_noprefix", "documents": 17,
                                                   "difference": 0.1235, "low": 0.05, "high": 0.2102, "p": 0.0, "holm_p": 0.0}]))
    write(tmp_path, "aq_scanned", frame([{"parser": "docling", "setting": "recursive_size256_overlap0_noprefix", "f1": 0.5},
                                         {"parser": "docling_ocr_tesseract", "setting": "fixed_token_size256_overlap0_noprefix", "f1": 0.26}]))
    write(tmp_path, "aq_scanned_vs_best", frame([{"parser": parser, "setting": "fixed_token_size256_overlap0_noprefix", "documents": 10,
                                                  "difference": difference, "low": low, "high": high, "p": 0.004, "holm_p": holm}
                                                 for parser, difference, low, high, holm in (("docling_ocr_tesseract", 0.2431, 0.0648, 0.4205, 0.036),
                                                                                           ("docling", -0.01, -0.09, 0.07, 1.0))]))
    write(tmp_path, "aq_tuning_vs_best", frame([{"parser": "docling", "setting": "x", "documents": 19, "difference": 0.07, "low": -0.03,
                                                 "high": 0.17, "p": 0.17, "holm_p": 1.0}]))
    answers = [{"set": split, "parser": "docling", "setting": f"s{index}", "doc_id": f"d-{split}", "question_id": f"q{question}",
                "f1": index / 10 + question / 100}
               for split in ("tuning", "held_out") for index in range(4) for question in range(3)]
    write(tmp_path, "aq_f1", frame(answers))
    judgements = [{key: row[key] for key in artifacts.KEYS} | {"score": row["f1"]} for row in answers]
    for row, score in zip(judgements, (0.0, 1.0, 1.0, 0.5)):  # the judge-check cases: scores that fit the reconstruction
        row["score"] = score
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
    grid = [f"{family}{size}{suffix}" for size in (256, 384, 512) for family, suffix in
            (("fixed_token_size", "_overlap0_noprefix"), ("recursive_size", "_overlap0_noprefix"),
             ("langchain_recursive_size", "_overlap0_noprefix"), ("method1_tree_T", "_noprefix"))] + ["recursive_size600_overlap0_noprefix"]
    setups = frame([{"setup": f"{parser}/{setting}", "recall": 0.78, "index_tokens": 35789.0, "chunks": 121.2}
                    for parser in ("docling", "pdfplumber") for setting in grid], "setup")
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
    write(tmp_path, "p3_final_record", json.dumps({"run_id": "P3-FINAL-20261106-1", "created_at": "2026-11-06T08:57:20+00:00"}))
    write(tmp_path, "p4_tuning_record", json.dumps({"stack": {"summary": {"full": {"documents": 19, "questions": 860, "setups": 100}}}}))
    write(tmp_path, "p3_tuning_record", json.dumps({"stack": {"scorer": {"bm25": {"k1": 1.5, "b": 0.75}, "hybrid": {"k": 60}},
                                                              "embedder": {"dimension": 1024}, "budgets": [750, 1250, 2000]}}))
    write(tmp_path, "fixedk_record", json.dumps({"stack": {"ks": [5, 10], "budget": 4000}}))
    write(tmp_path, "docling_record", json.dumps({"stack": {"parser": {"version": "2.143.0", "settings": {
        "do_ocr": True, "ocr_engine": "OcrAutoOptions"}}}}))
    write(tmp_path, "pdfplumber_record", json.dumps({"run_id": "P1-LOCAL-20261106-1", "created_at": "2026-11-05T19:00:39+00:00",
                                                     "stack": {"parser": {"version": "0.11.10"}}}))
    write(tmp_path, "manual", "key,value,unit,section,source_file,source_commit,note\njudge_first_pass_kappa,0.48,kappa,5,spec,a6278ca,n\n"
                              "judge_first_pass_agreement,0.70,proportion of 4 cases,5,spec,a6278ca,n\n"
                              "judge_first_pass_disagreements,2,cases,5,spec,a6278ca,n\njudge_first_pass_long_correct,1,of the 2,5,spec,a6278ca,n\n")
    write(tmp_path, "aq_sample", frame([{"set": split, "doc_id": "d1", "question_id": f"q{index}", "source": "CUAD", "question": "q",
                                         "reference": "r"} for split, count in (("tuning", 3), ("held_out", 2), ("scanned", 1)) for index in range(count)]))
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
                     r"\newcommand{\JudgeSecondAgreement}{100}", r"\newcommand{\RQfourSpearmanHeldOutFOne}{1.00}",
                     r"\newcommand{\RQonePrimarySettings}{3}", r"\newcommand{\RQonePrimarySizes}{256 and 384}",
                     r"\newcommand{\RQonePrimarySentenceWindow}{5}", r"\newcommand{\RQoneRawGap}{0.058}",
                     r"\newcommand{\RQfourDoclingFixedTokenSizeOneZeroTwoFourCI}{[0.050, 0.210]}",
                     r"\newcommand{\RQfourDoclingFixedTokenSizeOneZeroTwoFourHolm}{$<$0.01}",
                     r"\newcommand{\RQfourDoclingFixedTokenSizeOneZeroTwoFourSetup}{docling / fixed\_token 1024}",
                     r"\newcommand{\RQfourScannedTopDiff}{0.243}", r"\newcommand{\RQfourScannedTopHolm}{0.036}",
                     r"\newcommand{\RQfourScannedSignificant}{1}", r"\newcommand{\RQfourScannedAboveDoclingOcrTesseract}{1}",
                     r"\newcommand{\RQfourScannedAboveDocling}{0}", r"\newcommand{\RQfourScannedBestFOne}{0.500}",
                     r"\newcommand{\RQfiveADigitalDoclingRecall}{0.827}", r"\newcommand{\RQfiveADigitalPdfplumberRecall}{0.797--0.798}",
                     r"\newcommand{\RQfiveAScannedDocuments}{8}", r"\newcommand{\RQfiveAScannedQuestions}{34}",
                     r"\newcommand{\CoverageBySourceHeldOutCUADDocling}{8\%}"]:
        assert expected in numbers, expected
    assert "  % data/results" in numbers  # every macro names its source


def test_tag_freezes_study_code_and_refuses_untracked(tmp_path):
    assert artifacts.CODE_AT_TAG == ["src/", "scripts/p4_analyse.py", "scripts/aq_run.py"]  # paper/ may change freely
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("A = 1\n")
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "src/a.py")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "c")
    git(tmp_path, "tag", artifacts.TAG)
    inputs = artifacts.Inputs(tmp_path)
    assert inputs.changed_since_tag(["src/"]) == []
    (tmp_path / "src" / "b.py").write_text("B = 2\n")
    (tmp_path / "src" / "a.py").write_text("A = 3\n")
    assert inputs.changed_since_tag(["src/"]) == ["src/a.py", "src/b.py (untracked)"]


def test_sanity_timeline_erratum_and_labels(root):
    artifacts.build(root, root / "out")
    numbers = (root / "out" / "tables" / "numbers.tex").read_text()
    for expected in [r"\newcommand{\SanityFloorCases}{2}", r"\newcommand{\SanityFloorFailedOriginal}{2}",
                     r"\newcommand{\SanityFloorLower}{0.15--0.16}", r"\newcommand{\SanityDamageQuestions}{112}",
                     r"\newcommand{\SanityDamageDrop}{0.08--0.10}", r"\newcommand{\SanityDamageOtherMax}{0.01}",
                     r"\newcommand{\Resamples}{2{,}000}"]:
        assert expected in numbers, expected
    timeline = (root / "out" / "tables" / "a3_timeline.tex").read_text()
    assert "Specification v1 & \\texttt{607d29c} & 10-26 21:57:51 & 10-26 21:58:16" in timeline  # IST, first push from the page
    assert f"\\texttt{{{artifacts.TAG}}}" in timeline and "P3-FINAL-20261106-1" in timeline
    assert "held_out" not in (root / "out" / "tables" / "rq1.tex").read_text()
    assert "\\begin{tabular}" in (root / "out" / "tables" / "rq3_erratum.tex").read_text()


def test_thousands_comma_is_math_safe():
    assert artifacts.macro("X", "1,250") == r"\newcommand{\X}{1{,}250}"
    assert artifacts.macro("X", "256, 384 and 512") == r"\newcommand{\X}{256, 384 and 512}"
    assert artifacts.macro("X", "[0.050, 0.210]") == r"\newcommand{\X}{[0.050, 0.210]}"


def test_primary_choice_set_must_match_across_parsers():
    with pytest.raises(ValueError, match="differs between parsers"):
        artifacts.primary_choice_set(["docling/sentence_sentences5_noprefix", "pdfplumber/method1_tree_T384_noprefix"])


def test_design_dates_and_counts(root, monkeypatch):
    artifacts.build(root, root / "out")
    numbers = (root / "out" / "tables" / "numbers.tex").read_text()
    for expected in [r"\newcommand{\DateSpecVone}{26 October 2026}", r"\newcommand{\DateSpecVoneTwo}{3 November 2026}",
                     r"\newcommand{\DateScorerFrozen}{5 November 2026}", r"\newcommand{\DateHeldOutScored}{6 November 2026}",
                     r"\newcommand{\TuningDocuments}{1}", r"\newcommand{\TuningMainQuestions}{860}"]:
        assert expected in numbers, expected
    monkeypatch.setattr(artifacts.Inputs, "added_in", lambda self, path: "fffffff")
    with pytest.raises(ValueError, match="first added in fffffff"):
        artifacts.build(root, root / "out2")


def test_setups_and_scoring_facts(root, monkeypatch):
    artifacts.build(root, root / "out")
    numbers = (root / "out" / "tables" / "numbers.tex").read_text()
    for expected in [r"\newcommand{\DoclingVersion}{2.143.0}", r"\newcommand{\BMKone}{1.5}", r"\newcommand{\RRFk}{60}",
                     r"\newcommand{\BudgetMain}{1{,}250}", r"\newcommand{\FixedKBudget}{4{,}000}", r"\newcommand{\TopKLarge}{10}",
                     r"\newcommand{\SizeMin}{256}", r"\newcommand{\SizeStep}{128}", r"\newcommand{\ChunkMax}{1{,}024}",
                     r"\newcommand{\PrefixCap}{10\%}", "also {'recursive': [600]}"]:
        assert expected in numbers, expected
    settings = (root / "out" / "tables" / "docling_settings.tex").read_text()
    assert r"\texttt{do\_ocr} & \texttt{true}" in settings and r"\texttt{ocr\_engine} & \texttt{OcrAutoOptions}" in settings
    monkeypatch.setattr(artifacts.Inputs, "changed_since_tag", lambda self, paths: ["src/chunk/base.py"])
    with pytest.raises(ValueError, match=f"code changed since {artifacts.TAG}"):
        artifacts.build(root, root / "out2")


def test_docling_record_must_be_the_default_setup(root):
    path = root / artifacts.INPUTS["docling_record"]
    path.write_text(json.dumps({"stack": {"parser": {"version": "2.143.0", "settings": {"variant": "ocr_off", "do_ocr": False,
                                                                                         "ocr_engine": "OcrAutoOptions"}}}}))
    listed = (root / artifacts.CHECKSUMS).read_text().splitlines()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (root / artifacts.CHECKSUMS).write_text("\n".join(f"{digest}  {artifacts.INPUTS['docling_record']}" if line.endswith(artifacts.INPUTS["docling_record"])
                                                      else line for line in listed) + "\n")
    with pytest.raises(ValueError, match="not the default automatic-OCR setup"):
        artifacts.build(root, root / "out")


def test_statistics_aq_grid_and_deviations(root):
    artifacts.build(root, root / "out")
    numbers = (root / "out" / "tables" / "numbers.tex").read_text()
    for expected in [r"\newcommand{\CILevel}{95}", r"\newcommand{\Resamples}{2{,}000}", r"\newcommand{\SplitHalfReps}{200}",
                     r"\newcommand{\AQSampleShare}{20\%}", r"\newcommand{\AQTuningQuestions}{3}", r"\newcommand{\AQScannedQuestions}{1}",
                     r"\newcommand{\GoldenSampled}{6}", r"\newcommand{\GoldenInvalid}{2}", r"\newcommand{\GoldenUnsure}{2}", r"\newcommand{\ManualJudgeFirstPassAgreement}{70}"]:
        assert expected in numbers, expected
    low = float(re.search(r"JudgeReconKappaLow\}\{([0-9.]+)", numbers).group(1))
    high = float(re.search(r"JudgeReconKappaHigh\}\{([0-9.]+)", numbers).group(1))
    assert low <= high
    assert r"\newcommand{\JudgeDisagreements}{2}" in numbers and "ManualJudgeFirstPassDisagreements" not in numbers
    grid =(root / "out" / "tables" / "grid.tex").read_text()
    assert r"\textbf{LC-256}" in grid and "Rec-600" in grid and r"\textbf{M1-384}" in grid
    deviations = (root / "out" / "tables" / "deviations.tex").read_text()
    assert deviations.count(" & deviation & ") == int(re.search(r"DeviationCount\}\{(\d+)", numbers).group(1))
    assert deviations.count(" & correction & ") == int(re.search(r"CorrectionCount\}\{(\d+)", numbers).group(1))


def test_deviation_anchor_must_exist(root, monkeypatch):
    monkeypatch.setattr(artifacts, "DEVIATIONS", artifacts.DEVIATIONS + [("deviation", ["## No such note (2026-01-01)"], "x")])
    with pytest.raises(ValueError, match="spec anchor not on exactly one line"):
        artifacts.build(root, root / "out")


def test_fixedk_figure_leaves_out_superseded_and_sanity_settings(root):
    artifacts.build(root, root / "out")
    numbers = (root / "out" / "tables" / "numbers.tex").read_text()
    assert r"\newcommand{\RQthreeSettingsKept}{2}" in numbers and r"\newcommand{\RQthreeSettingsLeftOut}{2}" in numbers
    rq3 = "\n".join(line for line in numbers.splitlines() if line.startswith(r"\newcommand{\RQthree"))
    assert "v11" not in rq3 and "sanity" not in rq3  # the v11 setting would win Hit@1 if it were kept
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
    with pytest.raises(SystemExit, match=f"tag {artifacts.TAG}"):
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
                                            "limitations.tex": "Only \\RQoneGap documents.\n",
                                            "overview_figure.tex": "\\node[right=4mm, inner sep=2.5pt] {\\RQoneGap};\n"})
    assert check_sources.check(clean) == []
    bad = paper_tree(tmp_path / "bad", {"results.tex": "The gap is 0.007 and 70\\% agree.\n\\footnotesize\nA 4mm gap.\n",
                                        "limitations.tex": "New: \\OnlyHere.\n"})
    problems = "\n".join(check_sources.check(bad))
    assert "results.tex:3: typed number" in problems  # a length outside a figure file is still a typed number
    assert "typed number" in problems and "\\OnlyHere appears in no other section" in problems and "\\footnotesize" in problems


def test_short_names_are_one_scheme_without_collisions():
    artifacts.KEY.clear()
    assert artifacts.short("pdfplumber/method1_tree_T384_noprefix") == "P/M1-384"
    assert artifacts.short("docling/langchain_recursive_size256_overlap0_noprefix") == "D/LC-256"
    assert artifacts.short("docling/recursive_size256_overlap64_noprefix") == "D/Rec-256o64"
    assert artifacts.short("pdfplumber/method1_tree_T256_prefix") == "P/M1-256+p"
    assert artifacts.short("docling/sentence_sentences5_noprefix") == "D/Sent-5"
    assert artifacts.short("docling/langchain_default_noprefix") == "D/LC-def"
    assert artifacts.short_family("langchain_recursive", "pdfplumber") == "P/LC"
    assert artifacts.short_variant("docling_ocr_off") == "D/ocr off"
    with pytest.raises(ValueError, match="would stand for both"):
        artifacts.register("M1-384", "setting", "something else")
    artifacts.KEY.clear()


def test_key_table_lists_every_short_name_used(root):
    artifacts.build(root, root / "out")
    key = (root / "out" / "tables" / "key.tex").read_text()
    generated = "".join((root / "out" / path).read_text() for path in ("tables/rq1.tex", "tables/rq4.tex", "tables/a1_index_cost.tex",
                                                                         "tables/a2_retrievers.tex", "tables/a6_no_indian.tex", "figures/rq5.tex"))
    for name in ("P/M1-384", "D/LC-256", "D/LC", "D/headings"):
        assert name in generated, name
    for entry in (r"\emph{Parsers}", "D & \\texttt{docling}", r"M1-$n$ & \texttt{method1\_tree\_T}$n$\texttt{\_noprefix}",
                  r"Rec-$n$ & \texttt{recursive\_size}$n$\texttt{\_overlap0\_noprefix}", "LC & \\texttt{langchain\\_recursive}",
                  r"\emph{Docling settings}", "headings & ", "D1 & \\texttt{indian\\_d1}"):
        assert entry in key, entry
    assert "M1-384" not in key and "P/M1-384" not in key  # settings listed once per naming pattern
    assert artifacts.setting_pattern("Rec-256o64", "recursive_size256_overlap64_noprefix") == ("Rec-{n}o{m}", "recursive_size{n}_overlap{m}_noprefix")
    assert artifacts.setting_pattern("LLM-r2", "llm_regex_run2_noprefix") == ("LLM-r{n}", "llm_regex_run{n}_noprefix")
    with pytest.raises(ValueError, match="do not share their numbers"):
        artifacts.setting_pattern("FT-256", "fixed_token_size384_overlap0_noprefix")


def test_small_needs_a_reason(tmp_path):
    paper = paper_tree(tmp_path / "small", {"results.tex": "\\small\n\\small % small: eleven columns do not fit at 11 pt\n"})
    problems = check_sources.check(paper)
    assert problems == ["sections/results.tex:1: \\small without a '% small: <reason>' comment"]


def tag_exists():
    return subprocess.run(["git", "-C", str(artifacts.PROJECT), "rev-parse", "-q", "--verify", f"refs/tags/{artifacts.TAG}"],
                          capture_output=True).returncode == 0


@pytest.mark.skipif(not tag_exists(), reason=f"real results are read only after the {artifacts.TAG} tag")
def test_real_numbers_match_results_md(tmp_path):
    artifacts.check_tag(artifacts.PROJECT)
    artifacts.build(artifacts.PROJECT, tmp_path / "generated")
    numbers = (tmp_path / "generated" / "tables" / "numbers.tex").read_text()
    for name, value in {"RQoneBestRecall": "0.772", "RQoneTied": "15", "RQonePrimaryGap": "$-$0.007", "RQonePrimaryGapCI": "[$-$0.045, 0.023]",
                        "RQoneFullGap": "$-$0.056", "RQoneTuningWinnerRank": "20", "RQfourBestFOne": "0.393",
                        "RQfourSpearmanTuningFOne": "0.75", "RQfourSpearmanHeldOutFOne": "0.43", "RQfourSpearmanTuningJudge": "0.75",
                        "RQfourSpearmanHeldOutJudge": "0.64", "JudgeSecondAgreement": "95", "JudgeSecondKappa": "0.86",
                        "CoverageTuningDoclingLost": "84", "CoverageTuningDoclingTotal": "970", "CoverageHeldOutPdfplumberLost": "205",
                        "AccountingHeldOut": "31", "AccountingMain": "17", "RQthreeDoclingHitOneScore": "0.622",
                        "RQthreeDoclingMrrScore": "0.742", "GoldenOverallInvalid": "20", "RQthreeSettingsKept": "50",
                        "DateSpecVone": "26 October 2026", "DateSpecVoneOne": "1 November 2026", "DateSpecVoneTwo": "3 November 2026",
                        "DateScorerFrozen": "5 November 2026", "DateHeldOutScored": "6 November 2026", "TuningDocuments": "25",
                        "TuningScoredDocuments": "20", "TuningMainDocuments": "19", "TuningMainQuestions": "860",
                        "DoclingVersion": "2.143.0", "PdfplumberVersion": "0.11.10", "BMKone": "1.5", "BMb": "0.75", "RRFk": "60",
                        "EmbedDim": "1{,}024", "BudgetLow": "750", "BudgetMain": "1{,}250", "BudgetHigh": "2{,}000", "TopKSmall": "5",
                        "TopKLarge": "10", "FixedKBudget": "4,000", "TuningSetups": "100", "HeldOutSetups": "98", "SizeMin": "256",
                        "SizeMax": "1{,}024", "SizeStep": "128", "ChunkMin": "100", "ChunkMax": "1{,}024", "PrefixCap": "10\\%",
                        "CILevel": "95", "Resamples": "2{,}000", "SplitHalfReps": "200", "AQSampleShare": "20\\%", "AQTuningQuestions": "179",
                        "AQHeldOutQuestions": "114", "AQScannedQuestions": "25", "JudgeReconKappaLow": "0.45", "JudgeReconKappaHigh": "0.46",
                        "JudgeDisagreements": "12", "RQonePrimarySettings": "13", "RQonePrimarySizes": "256, 384 and 512",
                        "RQonePrimarySentenceWindow": "5", "RQoneRawGap": "0.058",
                        "RQfourDoclingFixedTokenSizeOneZeroTwoFourDiff": "0.123", "RQfourDoclingFixedTokenSizeOneZeroTwoFourCI": "[0.050, 0.210]",
                        "RQfourDoclingFixedTokenSizeOneZeroTwoFourHolm": "$<$0.01", "RQfourDoclingMethodOneTreeTThreeEightFourDiff": "0.065",
                        "RQfourDoclingMethodOneTreeTThreeEightFourHolm": "0.025", "RQfourDoclingLangchainDefaultDiff": "0.047",
                        "RQfourDoclingLangchainDefaultHolm": "0.176", "RQfourScannedTopDiff": "0.243", "RQfourScannedTopHolm": "0.036",
                        "RQfourScannedSignificant": "1", "RQfiveADigitalDoclingRecall": "0.827",
                        "RQfiveADigitalPdfplumberRecall": "0.797--0.798",  # RESULTS.md 3 gives 0.798 (the 307-question sample)
                        "RQfiveAScannedDocuments": "8", "RQfiveAScannedQuestions": "34",
                        "CoverageBySourceHeldOutIndianDocling": "2\\%", "CoverageBySourceHeldOutIndianPdfplumber": "14\\%",
                        "CoverageBySourceHeldOutCOHRBenchDocling": "22\\%", "CoverageBySourceHeldOutCOHRBenchPdfplumber": "37\\%",
                        "GoldenSampled": "60", "GoldenInvalid": "20", "DeviationCount": "21", "ManualJudgeFirstPassAgreement": "70",
                        "CorrectionCount": "5", "GoldenUnsure": "8"}.items():
        assert f"\\newcommand{{\\{name}}}{{{value}}}" in numbers, name
