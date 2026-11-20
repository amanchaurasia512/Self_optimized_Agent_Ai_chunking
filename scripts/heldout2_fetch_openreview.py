"""Held-out set 2 (spec v1.2 "Held-out set 2: PeerQA" and "Held-out set 2: correction and PDF sources"): download the
PDFs of the OpenReview papers among the 93 eligible PeerQA papers (at least 2 answerable questions with evidence in
answer_evidence_mapped, from the metadata in data/external/peerqa/), with the author's own OpenReview login.
Credentials come only from the environment (OPENREVIEW_USERNAME, OPENREVIEW_PASSWORD); they are never printed or
saved. One request every 2 seconds; a failed paper is retried once. Each file is saved as <output>/<paper_id>.pdf
only if it is a PDF (starts with %PDF-); a paper already saved is not downloaded again. Prints counts and failures only.
Needs openreview-py in the environment that runs it. Run from the repo root:
    OPENREVIEW_USERNAME=... OPENREVIEW_PASSWORD=... python -m scripts.heldout2_fetch_openreview --output data/raw/peerqa"""
import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path

from src.common.manifest import PROJECT_ROOT

PEERQA = PROJECT_ROOT / "data" / "external" / "peerqa"
MIN_QUESTIONS, EXPECTED_PAPERS, EXPECTED_OPENREVIEW = 2, 93, 64
INTERVAL = 2.0  # seconds between requests
API = {"v2": "https://api2.openreview.net", "v1": "https://api.openreview.net"}


def eligible_papers():
    """Paper ids with at least 2 answerable questions whose answer_evidence_mapped is not empty (metadata only)."""
    rows = [json.loads(line) for line in (PEERQA / "qa.jsonl").read_text(encoding="utf-8").splitlines()]
    counts = Counter(row["paper_id"] for row in rows if row["answerable"] is True and row["answer_evidence_mapped"])
    papers = sorted(paper for paper, count in counts.items() if count >= MIN_QUESTIONS)
    if len(papers) != EXPECTED_PAPERS:
        raise SystemExit(f"expected {EXPECTED_PAPERS} eligible papers, found {len(papers)}")
    return papers


def clients(username, password):
    """Logged-in API v2 and v1 clients (ICLR 2022 and NeurIPS 2022 notes may be served by either); a version whose
    login fails is left out, and the run stops only if neither logs in. Error texts are never shown."""
    import openreview
    makers = {"v2": openreview.api.OpenReviewClient, "v1": openreview.Client}
    apis, refused = {}, []
    for name, make in makers.items():
        try:
            apis[name] = make(baseurl=API[name], username=username, password=password)
        except Exception as error:  # the error text may repeat what was sent
            refused.append(f"{name} ({type(error).__name__})")
    if not apis:
        raise SystemExit(f"OpenReview login failed: {', '.join(refused)}")
    if refused:
        print(f"login refused by {', '.join(refused)}; using {', '.join(apis)}")
    return apis


def fetch(apis, forum_id, wait):
    """The PDF bytes from the first API version that serves them; raises with the last error otherwise."""
    errors = []
    for name, client in apis.items():
        wait()
        try:
            data = client.get_pdf(forum_id)
        except Exception as error:  # the API raises its own error types; keep the reason only
            errors.append(f"{name}: {type(error).__name__}")
            continue
        if data[:5] == b"%PDF-":
            return data
        errors.append(f"{name}: not a PDF ({len(data)} bytes)")
    raise RuntimeError("; ".join(errors))


def main():
    arg_parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    arg_parser.add_argument("--output", required=True, type=Path, help="folder for <paper_id>.pdf")
    args = arg_parser.parse_args()
    username, password = os.environ.get("OPENREVIEW_USERNAME"), os.environ.get("OPENREVIEW_PASSWORD")
    if not username or not password:
        raise SystemExit("set OPENREVIEW_USERNAME and OPENREVIEW_PASSWORD in the environment")
    papers = [paper for paper in eligible_papers() if paper.startswith("openreview/")]
    if len(papers) != EXPECTED_OPENREVIEW:
        raise SystemExit(f"expected {EXPECTED_OPENREVIEW} OpenReview papers, found {len(papers)}")
    apis = clients(username, password)
    del username, password

    last = [0.0]
    def wait():
        time.sleep(max(0.0, last[0] + INTERVAL - time.monotonic()))
        last[0] = time.monotonic()

    saved, skipped, failed = 0, 0, {}
    for paper in papers:
        target = args.output / f"{paper}.pdf"
        if target.exists() and target.read_bytes()[:5] == b"%PDF-":
            skipped += 1
            continue
        for attempt in (1, 2):
            try:
                data = fetch(apis, paper.rsplit("/", 1)[1], wait)
            except RuntimeError as error:
                failed[paper] = str(error)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            failed.pop(paper, None)
            saved += 1
            break
    print(f"OpenReview papers {len(papers)} | downloaded {saved} | already present {skipped} | failed {len(failed)}")
    for paper, reason in failed.items():
        print(f"FAILED {paper}: {reason}")


if __name__ == "__main__":
    main()
