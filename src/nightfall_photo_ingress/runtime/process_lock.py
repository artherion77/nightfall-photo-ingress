"""Global process lock helpers for poll serialization.

This lock ensures only one poll run executes at a time across CLI/timer invocations.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import fcntl


@contextmanager
def global_process_lock(lock_path: Path) -> Iterator[None]:
    """Acquire a blocking global advisory lock for poll execution."""

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
