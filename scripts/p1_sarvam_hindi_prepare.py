"""Hindi track: extract the Hindi samples of Sarvam Indic OCR Bench (small_representative split)
as image files plus a ground-truth JSON, and fetch the benchmark's own scorer (metrics.py)."""
import json
from pathlib import Path

import pandas as pd
from huggingface_hub import hf_hub_download

from src.common.manifest import PROJECT_ROOT, project_path

REPO_ID = "sarvamai/indic-ocr-bench"
SPLIT_FILE = "small_representative/small_representative-00000-of-00001.parquet"
OUTPUT_DIR = PROJECT_ROOT / "data" / "external" / "sarvam_ocr"


def main():
    split_path = hf_hub_download(REPO_ID, SPLIT_FILE, repo_type="dataset", local_dir=OUTPUT_DIR)
    hf_hub_download(REPO_ID, "metrics.py", repo_type="dataset", local_dir=OUTPUT_DIR)
    frame = pd.read_parquet(split_path)
    hindi = frame[frame["language"] == "Hindi"]

    image_dir = OUTPUT_DIR / "hindi_small" / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for row in hindi.itertuples(index=False):
        suffix = Path(row.image.get("path") or "sample.png").suffix or ".png"
        image_path = image_dir / f"{row.image_name}{suffix}"
        image_path.write_bytes(row.image["bytes"])
        records.append({"image_name": row.image_name, "gt": row.gt, "language": row.language,
                        "file": project_path(image_path)})
    (OUTPUT_DIR / "hindi_small" / "ground_truth.json").write_text(json.dumps(records, ensure_ascii=False, indent=2),
                                                                  encoding="utf-8")

    print(len(hindi), "Hindi samples out of", len(frame), "in the small split")
    print("ground-truth words per sample:")
    print(hindi["gt"].str.split().str.len().describe().round(1))
    print("\nexample:", records[0]["image_name"], "|", records[0]["gt"][:150])


if __name__ == "__main__":
    main()