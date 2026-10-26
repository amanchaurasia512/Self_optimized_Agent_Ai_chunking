"""Run manifest: one JSON per run in runs/, recording code version, stack, environment, inputs, outputs and costs."""
import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = PROJECT_ROOT / "runs"


def git_output(*args):
    """Reads git state only; never commits."""
    result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def code_version():
    status = git_output("status", "--porcelain")
    return {"commit": git_output("rev-parse", "HEAD"), "uncommitted_changes": None if status is None else bool(status)}


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for block in iter(lambda: file.read(2**20), b""):
            digest.update(block)
    return digest.hexdigest()


def project_path(path):
    """Path relative to the project root when inside it (portable across machines), else absolute."""
    resolved = Path(path).resolve()
    return str(resolved.relative_to(PROJECT_ROOT)) if resolved.is_relative_to(PROJECT_ROOT) else str(resolved)


def new_run_id(phase, source):
    """Run id format from the naming scheme: P{phase}-{source}-{date}-{n}."""
    prefix = f"P{phase}-{source}-{datetime.now():%Y%m%d}"
    return f"{prefix}-{len(list(RUNS_DIR.glob(f'{prefix}-*.json'))) + 1}"


def build_manifest(run_id, spec_version, stack, inputs, outputs, costs, machine, config_path=None):
    return {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code": code_version(),
        "spec_version": spec_version,
        "config": {"path": project_path(config_path), "sha256": file_sha256(config_path)} if config_path else None,
        "stack": stack,
        "environment": {"machine": machine, "host": platform.node(), "python": platform.python_version(), "os": platform.platform()},
        "inputs": [{"path": project_path(path), "sha256": file_sha256(path)} for path in inputs],
        "outputs": [project_path(path) for path in outputs],
        "costs": costs,
    }


def write_manifest(manifest):
    RUNS_DIR.mkdir(exist_ok=True)
    path = RUNS_DIR / f"{manifest['run_id']}.json"
    if path.exists():
        raise FileExistsError(f"Manifest already exists, run ids must be unique: {path}")
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path