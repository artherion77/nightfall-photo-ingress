"""E2E Module 1 artifact integrity tests (Cases 9-11)."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path("/home/chris/dev/nightfall-photo-ingress")
GOVCTL_RUNS_DIR = REPO_ROOT / "artifacts" / "govctl"
WEB_BUILD_DIR = REPO_ROOT / "webui" / "build"
WHEEL_GLOB_DIR = REPO_ROOT / "dist"
STAGING_CONTAINER = "staging-photo-ingress"
STAGING_WEB_BUILD_DIR = "/opt/webui/build"


def _hash_files(paths: list[Path], rel_base: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.as_posix()):
        rel = path.relative_to(rel_base).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _compute_host_directory_hash(path: Path) -> str:
    if not path.exists():
        raise AssertionError(f"artifact path does not exist: {path}")
    files = [item for item in path.rglob("*") if item.is_file()]
    if not files:
        raise AssertionError(f"artifact path contains no files: {path}")
    return _hash_files(files, path)


def _compute_host_glob_hash(pattern: str) -> str:
    files = [item.resolve() for item in WHEEL_GLOB_DIR.parent.glob(pattern) if item.is_file()]
    if not files:
        raise AssertionError(f"glob matched no files: {pattern}")
    return _hash_files(files, REPO_ROOT)


def _compute_container_directory_hash(container: str, path: str) -> str:
    proc = subprocess.run(
        [
            "lxc",
            "exec",
            container,
            "--",
            "python3",
            "-c",
            (
                "import hashlib, pathlib, sys; "
                "root=pathlib.Path(sys.argv[1]); "
                "files=sorted([p for p in root.rglob(\"*\") if p.is_file()], key=lambda p: p.as_posix()); "
                "assert files, 'no files'; "
                "h=hashlib.sha256(); "
                "[h.update(p.relative_to(root).as_posix().encode(\"utf-8\")) or h.update(b\"\\0\") or h.update(p.read_bytes()) or h.update(b\"\\0\") for p in files]; "
                "print(h.hexdigest())"
            ),
            path,
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(f"unable to hash container artifact path {path}: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def _latest_build_fingerprint(target: str) -> dict[str, str]:
    latest: dict[str, str] | None = None
    run_dirs = sorted(GOVCTL_RUNS_DIR.glob("run-*"), key=lambda item: item.name)
    for run_dir in run_dirs:
        events_path = run_dir / "events.jsonl"
        if not events_path.exists():
            continue
        for raw in events_path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            event = json.loads(raw)
            if event.get("event") != "build_fingerprint":
                continue
            if event.get("target") != target:
                continue
            latest = event
    if latest is None:
        raise AssertionError(f"no build_fingerprint event found for target {target}")
    return latest


@pytest.mark.staging
def test_case_9_spa_build_hash_matches_recorded_fingerprint() -> None:
    """Case 9: host SPA build artifact hash matches the latest recorded fingerprint."""
    fingerprint = _latest_build_fingerprint("web.build")
    actual_hash = _compute_host_directory_hash(WEB_BUILD_DIR)
    assert fingerprint["artifact_path"] == "webui/build/"
    assert actual_hash == fingerprint["sha256"], "SPA build artifact hash diverges from recorded build_fingerprint"


@pytest.mark.staging
def test_case_10_wheel_hash_matches_recorded_fingerprint() -> None:
    """Case 10: wheel artifact hash matches the latest recorded fingerprint."""
    fingerprint = _latest_build_fingerprint("backend.build.wheel")
    actual_hash = _compute_host_glob_hash("dist/*.whl")
    assert fingerprint["artifact_path"] == "dist/*.whl"
    assert actual_hash == fingerprint["sha256"], "wheel artifact hash diverges from recorded build_fingerprint"


@pytest.mark.staging
def test_case_11_deployed_staging_spa_matches_host_build_artifact() -> None:
    """Case 11: deployed staging SPA is byte-identical to the host build artifact."""
    host_hash = _compute_host_directory_hash(WEB_BUILD_DIR)
    staging_hash = _compute_container_directory_hash(STAGING_CONTAINER, STAGING_WEB_BUILD_DIR)
    assert staging_hash == host_hash, "staging SPA artifact differs from the built host SPA artifact"