from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def spa_build_stub() -> None:
    build_dir = Path(__file__).resolve().parents[3] / "webui" / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / "index.html").write_text("<html><body><div id='app'>dashboard-shell</div></body></html>", encoding="utf-8")
    (build_dir / "200.html").write_text("<html><body><div id='app'>spa-fallback</div></body></html>", encoding="utf-8")
