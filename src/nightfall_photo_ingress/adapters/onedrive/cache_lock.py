"""File-lock helper for account-scoped token cache operations.

The lock is advisory and process-wide on POSIX systems.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import fcntl


class SingletonLockBusyError(RuntimeError):
    """Raised when a non-blocking singleton lock cannot be acquired."""


@contextmanager
def cache_file_lock(cache_path: Path) -> Iterator[None]:
    """Acquire an exclusive lock for a token cache path.

    The lock is stored in a sibling ``.lock`` file so callers can lock even
    when the cache file does not yet exist.
    """

    lock_path = cache_path.with_suffix(cache_path.suffix + ".lock")
    with _file_lock(lock_path, blocking=True):
        yield


@contextmanager
def account_singleton_lock(cache_path: Path, lock_name: str = ".runtime.lock") -> Iterator[None]:
    """Acquire a non-blocking per-account singleton lock.

    This prevents overlapping poll/refresh-sensitive operations for one account
    across processes.
    """

    lock_path = cache_path.parent / lock_name
    with _file_lock(lock_path, blocking=False):
        yield


@contextmanager
def _file_lock(lock_path: Path, blocking: bool) -> Iterator[None]:
    """Acquire advisory lock for the given path."""

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as handle:
        mode = fcntl.LOCK_EX if blocking else (fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            fcntl.flock(handle.fileno(), mode)
        except BlockingIOError as exc:
            raise SingletonLockBusyError(str(lock_path)) from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
