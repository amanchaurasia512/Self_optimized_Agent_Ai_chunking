"""Re-draw the AQ judge-check cases (spec note "AQ judge check: size changed from 20 to 40 cases", 2026-11-15).

Read-only, no LLM call: aq_run.answered() and the draw of aq_run.draw_check_cases (both unchanged since 3d5407e), compared
with the stored judge_check_keys.csv and judge_check.csv. Never calls draw_check_cases, which would overwrite them.
Writes the comparison to data/results/repro-20261115/redraw_judge_check.log.
Run from the repo root: python -m scripts.redraw_judge_check
"""
import pandas as pd

from scripts.aq_run import CHECK_CASES, CHECK_FILE, CHECK_KEYS, SEED, answered
from src.common.manifest import PROJECT_ROOT

LOG = PROJECT_ROOT / "data" / "results" / "repro-20261115" / "redraw_judge_check.log"
KEYS = ["parser", "setting", "doc_id", "question_id"]
TEXT = ["question", "reference", "answer"]


def main():
    cases = answered().query("set == 'tuning'").sample(CHECK_CASES, random_state=SEED).reset_index(drop=True)
    stored_keys, stored_text = pd.read_csv(CHECK_KEYS, dtype=str), pd.read_csv(CHECK_FILE, dtype=str)
    lines = [f"pandas {pd.__version__} | rows {len(cases)} {len(stored_keys)} {len(stored_text)}",
             f"keys identical, same order: {cases[KEYS].astype(str).equals(stored_keys[KEYS])}",
             "question/reference/answer identical, same order: "
             f"{cases[TEXT].astype(str).equals(stored_text[TEXT].fillna('').astype(str))}",
             f"same set of keys: {set(map(tuple, cases[KEYS].astype(str).values)) == set(map(tuple, stored_keys[KEYS].values))}"]
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
