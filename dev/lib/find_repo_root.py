"""Location-independent repository root discovery.

Walks up the directory tree from a known anchor (defaulting to this file's
own location) until the sentinel file is found.  The result is cached at
module level so repeated calls are free.
"""

from __future__ import annotations

from pathlib import Path

_SENTINEL: str = "pyproject.toml"
_MAX_DEPTH: int = 12
_cached_root: Path | None = None


def find_repo_root(
    *,
    anchor: Path | None = None,
    sentinel: str = _SENTINEL,
    max_depth: int = _MAX_DEPTH,
) -> Path:
    """Return the repository root directory.

    Discovery strategy:
    1. Start from *anchor* (default: the directory containing this module).
    2. Walk up at most *max_depth* levels looking for *sentinel*.
    3. Cache and return the first directory that contains the sentinel.
    4. Raise ``RuntimeError`` if the sentinel is not found within the depth
       limit.

    The function is deterministic and independent of the current working
    directory when *anchor* is omitted (it anchors to this file's location).
    """
    global _cached_root

    if _cached_root is not None:
        return _cached_root

    start = (anchor or Path(__file__)).resolve().parent

    current = start
    for _ in range(max_depth):
        if (current / sentinel).is_file():
            _cached_root = current
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent

    raise RuntimeError(
        f"Repository root not found: no '{sentinel}' within {max_depth} "
        f"levels above {start}"
    )


def reset_cache() -> None:
    """Clear the cached root (for testing only)."""
    global _cached_root
    _cached_root = None
