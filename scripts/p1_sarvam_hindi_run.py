"""Hindi track: run LlamaParse tiers on the Sarvam Indic OCR Bench Hindi samples and score each tier with the
benchmark's own metrics.py (CER/WER after its normalisation). Existing outputs are reused, so credits are never spent twice."""
import argparse
import json
import subprocess
import sys
import pandas as pd
import csv
from src.common.cost_logger import CostLogger
from src.common.manifest import PROJECT_ROOT, build_manifest, new_run_id, write_manifest
from src.parse.llamaparse_parser import CREDITS_PER_PAGE, make_client, parse_pdf, parser_info

SARVAM_DIR = PROJECT_ROOT / "data" / "external" / "sarvam_ocr"
OUTPUT_DIR = PROJECT_ROOT / "data" / "extracted" / "sarvam_hindi"
OCR_LANG = ["hi", "en"]
EXCLUSIONS_FILE = PROJECT_ROOT / "configs" / "sarvam_hindi_exclusions.csv"


def predict(samples, tier, client, logger):
    tier_dir = OUTPUT_DIR / tier
    tier_dir.mkdir(parents=True, exist_ok=True)
    predictions, new_outputs = [], []
    for sample in samples:
        output_path = tier_dir / f"{sample['image_name']}.json"
        if not output_path.exists():
            with logger.stage(f"{tier}:{sample['image_name']}"):
                text, pages = parse_pdf(PROJECT_ROOT / sample["file"], client, tier, OCR_LANG)
                logger.add_credits(len(pages) * CREDITS_PER_PAGE[tier])
                output_path.write_text(json.dumps({"image_name": sample["image_name"], "parser": parser_info(tier, OCR_LANG),
                                                   "text": text}, ensure_ascii=False, indent=2), encoding="utf-8")
            new_outputs.append(output_path)
        predictions.append({"image_name": sample["image_name"], "gt": sample["gt"], "language": sample["language"],
                            "pred": json.loads(output_path.read_text(encoding="utf-8"))["text"]})
    return predictions, new_outputs


def score(predictions, tier, subset):
    input_path, report_path = OUTPUT_DIR / f"predictions_{tier}_{subset}.json", OUTPUT_DIR / f"report_{tier}_{subset}.json"
    input_path.write_text(json.dumps(predictions, ensure_ascii=False, indent=2), encoding="utf-8")
    subprocess.run([sys.executable, str(SARVAM_DIR / "metrics.py"), "--input", str(input_path), "--normalize",
                    "--overwrite", "--output", str(report_path)], check=True, capture_output=True)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return {"tier": tier, "subset": subset, "samples": len(predictions),
            "cer": report.get("avg_metrics", {}).get("cer"), "wer": report.get("avg_metrics", {}).get("wer"),
            "word_accuracy": report.get("word_accuracy"), "loop_failures": report.get("loop_failure_count"),
            "missing": report.get("missing_prediction_count")}


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("--tiers", nargs="+", default=["fast", "cost_effective", "agentic"], choices=list(CREDITS_PER_PAGE))
    args = arg_parser.parse_args()

    samples = json.loads((SARVAM_DIR / "hindi_small" / "ground_truth.json").read_text(encoding="utf-8"))
    excluded = {row["image_name"] for row in csv.DictReader(EXCLUSIONS_FILE.open(encoding="utf-8"))} if EXCLUSIONS_FILE.exists() else set()
    client, logger = make_client(), CostLogger()
    results, outputs = [], []
    for tier in args.tiers:
        predictions, new_outputs = predict(samples, tier, client, logger)
        outputs += new_outputs
        results.append(score(predictions, tier, "all"))
        results.append(score([item for item in predictions if item["image_name"] not in excluded], tier, "hindi_only"))

    if outputs:
        manifest = build_manifest(new_run_id(1, "LOCAL"), "v1", {"benchmark": "sarvamai/indic-ocr-bench small_representative Hindi",
                                  "tiers": args.tiers, "ocr_lang": OCR_LANG}, [], outputs, logger.summary(), "laptop")
        print("manifest:", write_manifest(manifest), "| credits:", logger.summary()["totals"]["paid_credits"])
    print(pd.DataFrame(results).to_string(index=False))


if __name__ == "__main__":
    main()