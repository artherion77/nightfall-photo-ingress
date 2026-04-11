from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(REPO_ROOT / "dev" / "lib"))
from find_repo_root import find_repo_root, reset_cache  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """Ensure each test starts with a fresh cache."""
    reset_cache()
    yield  # type: ignore[misc]
    reset_cache()


def test_finds_root_from_anchor_at_root(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    result = find_repo_root(anchor=tmp_path / "dummy.py", sentinel="pyproject.toml")
    assert result == tmp_path


def test_finds_root_from_nested_anchor(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    result = find_repo_root(anchor=nested / "script.py", sentinel="pyproject.toml")
    assert result == tmp_path


def test_raises_when_sentinel_not_found(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="Repository root not found"):
        find_repo_root(anchor=nested / "x.py", sentinel="nonexistent.sentinel", max_depth=5)


def test_raises_when_depth_exceeded(tmp_path: Path) -> None:
    # Place sentinel at root but restrict depth to 1 with deep nesting
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    deep = tmp_path / "a" / "b" / "c" / "d"
    deep.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="Repository root not found"):
        find_repo_root(anchor=deep / "x.py", sentinel="pyproject.toml", max_depth=2)


def test_caches_result(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    first = find_repo_root(anchor=tmp_path / "dummy.py", sentinel="pyproject.toml")
    # Second call should return cached value even with a different anchor
    second = find_repo_root(anchor=Path("/nonexistent/dummy.py"), sentinel="pyproject.toml")
    assert first == second == tmp_path


def test_reset_cache_allows_rediscovery(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    first = find_repo_root(anchor=tmp_path / "dummy.py", sentinel="pyproject.toml")
    reset_cache()
    # After reset, a new anchor is needed (or default kicks in)
    second = find_repo_root(anchor=tmp_path / "dummy.py", sentinel="pyproject.toml")
    assert first == second


def test_finds_real_repo_root() -> None:
    """Smoke test against the actual repository."""
    result = find_repo_root(anchor=Path(__file__), sentinel="pyproject.toml")
    assert result == REPO_ROOT
    assert (result / "pyproject.toml").is_file()


def test_metricsctl_repo_root_matches_from_any_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify that _repo_root() in metricsctl resolves correctly regardless of CWD.

    We simulate this by calling find_repo_root with the canonical metricsctl
    anchor (dev/lib/metricsctl.py) while CWD is set to a temporary directory.
    """
    monkeypatch.chdir(tmp_path)
    metricsctl_path = REPO_ROOT / "dev" / "lib" / "metricsctl.py"
    result = find_repo_root(anchor=metricsctl_path, sentinel="pyproject.toml")
    assert result == REPO_ROOT
