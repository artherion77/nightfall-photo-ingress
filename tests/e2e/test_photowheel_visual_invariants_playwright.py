"""Staging E2E bridge for PhotoWheel visual invariants Playwright checks."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path('/home/chris/dev/nightfall-photo-ingress')
WEBUI_ROOT = '/opt/nightfall-webui'
DEV_CONTAINER = os.environ.get('DEV_CONTAINER', 'dev-photo-ingress')
PLAYWRIGHT_SPEC = 'tests/e2e/photowheel.visual-invariants.spec.ts'


def _container_is_running(name: str) -> bool:
    proc = subprocess.run(['lxc', 'info', name], capture_output=True, text=True)
    if proc.returncode != 0:
        return False
    return 'status: running' in proc.stdout.lower()


@pytest.mark.staging
@pytest.mark.xfail(
    reason="Known env-dependent staging visual variance; tracked in GH issue #29",
    strict=False,
)
def test_case_17_photowheel_visual_invariants_playwright(base_url: str) -> None:
    """Case 17: execute staging-system Playwright visual invariant checks (VIS-1..VIS-7)."""
    if not _container_is_running(DEV_CONTAINER):
        pytest.skip(f"dev container '{DEV_CONTAINER}' is not running")

    ensure = subprocess.run(
        [str(REPO_ROOT / 'dev' / 'bin' / 'devctl'), 'ensure-stack-ready', 'webui'],
        capture_output=True,
        text=True,
    )
    if ensure.returncode != 0:
        raise AssertionError(
            'failed to sync webui stack into dev container:\n'
            f'stdout:\n{ensure.stdout}\n\n'
            f'stderr:\n{ensure.stderr}'
        )

    command = (
        f"cd {WEBUI_ROOT} && "
        f"STAGING_BASE_URL={base_url} "
        f"npx playwright test {PLAYWRIGHT_SPEC} --reporter=line"
    )
    proc = subprocess.run(
        ['lxc', 'exec', DEV_CONTAINER, '--', 'bash', '-lc', command],
        capture_output=True,
        text=True,
    )

    if proc.returncode != 0:
        raise AssertionError(
            'playwright visual invariant checks failed:\n'
            f'stdout:\n{proc.stdout}\n\n'
            f'stderr:\n{proc.stderr}'
        )