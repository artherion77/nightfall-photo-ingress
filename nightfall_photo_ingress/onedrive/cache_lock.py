"""File-lock helper for account-scoped token cache operations.

The lock is advisory and process-wide on POSIX systems.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import fcntl


@contextmanager
def cache_file_lock(cache_path: Path) -> Iterator[None]:
    """Acquire an exclusive lock for a token cache path.

    The lock is stored in a sibling ``.lock`` file so callers can lock even
    when the cache file does not yet exist.
    """

    lock_path = cache_path.with_suffix(cache_path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
