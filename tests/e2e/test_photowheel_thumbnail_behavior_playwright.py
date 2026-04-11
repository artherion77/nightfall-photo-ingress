"""Staging E2E bridge for PhotoWheel thumbnail behavior Playwright checks."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.e2e.playwright_staging_runner import (
    container_is_running,
    ensure_staging_playwright_runner_ready,
    run_playwright_spec_in_staging,
)


REPO_ROOT = Path('/home/chris/dev/nightfall-photo-ingress')
STAGING_CONTAINER = os.environ.get('STAGING_CONTAINER', 'staging-photo-ingress')
PLAYWRIGHT_SPEC = 'tests/e2e/photowheel.thumbnail-behavior.spec.ts'


@pytest.mark.staging
@pytest.mark.xfail(
    reason="Known env-dependent staging queue size variance; tracked in GH issue #29",
    strict=False,
)
def test_case_18_photowheel_thumbnail_behavior_playwright(base_url: str) -> None:
    """Case 18: execute staging-system Playwright thumbnail behavior checks (C.1-C.5)."""
    if not container_is_running(STAGING_CONTAINER):
        pytest.skip(f"staging container '{STAGING_CONTAINER}' is not running")

    ensure_staging_playwright_runner_ready(STAGING_CONTAINER, REPO_ROOT)
    run_playwright_spec_in_staging(STAGING_CONTAINER, PLAYWRIGHT_SPEC, base_url)
