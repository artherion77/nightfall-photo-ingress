#!/usr/bin/env python3
"""Global repository lock helpers.

Provides Python context-manager usage and a small CLI for Bash callers.
"""

from __future__ import annotations

import argparse
import fcntl
import os
import sys
import time
from pathlib import Path

DEFAULT_LOCK_FILE = Path("/tmp/nightfall-repo.lock")
DEFAULT_TIMEOUT_SEC = 300
REENTRY_ENV = "DEVCTL_GLOBAL_LOCK_HELD"

_HELD_HANDLE: object | None = None


class RepoLock:
    def __init__(self, lock_file: Path = DEFAULT_LOCK_FILE, timeout_sec: int = DEFAULT_TIMEOUT_SEC) -> None:
        self.lock_file = Path(lock_file)
        self.timeout_sec = timeout_sec
        self._handle: object | None = None
        self._acquired = False

    def is_reentrant(self) -> bool:
        return os.environ.get(REENTRY_ENV) == "1"

    def acquire(self) -> bool:
        if self.is_reentrant():
            return True

        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        handle = self.lock_file.open("a+", encoding="utf-8")
        deadline = time.monotonic() + max(0, self.timeout_sec)

        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._handle = handle
                self._acquired = True
                os.environ[REENTRY_ENV] = "1"
                return True
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    handle.close()
                    raise TimeoutError(
                        f"timed out acquiring lock {self.lock_file} after {self.timeout_sec}s"
                    )
                time.sleep(0.05)

    def release(self) -> None:
        if not self._acquired or self._handle is None:
            return
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()
        self._handle = None
        self._acquired = False
        os.environ.pop(REENTRY_ENV, None)

    def __enter__(self) -> "RepoLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


def acquire_lock(lock_file: Path = DEFAULT_LOCK_FILE, timeout: int = DEFAULT_TIMEOUT_SEC) -> bool:
    """Acquire process-global lock and set reentry env on success."""
    global _HELD_HANDLE

    if os.environ.get(REENTRY_ENV) == "1":
        return True

    path = Path(lock_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    deadline = time.monotonic() + max(0, timeout)

    while True:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            _HELD_HANDLE = handle
            os.environ[REENTRY_ENV] = "1"
            return True
        except BlockingIOError:
            if time.monotonic() >= deadline:
                handle.close()
                return False
            time.sleep(0.05)


def release_lock() -> None:
    """Release process-global lock if currently held by this process."""
    global _HELD_HANDLE

    if _HELD_HANDLE is not None:
        fcntl.flock(_HELD_HANDLE.fileno(), fcntl.LOCK_UN)
        _HELD_HANDLE.close()
        _HELD_HANDLE = None
    os.environ.pop(REENTRY_ENV, None)


def _cli_status(lock_file: Path) -> int:
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_file.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("locked")
        handle.close()
        return 0

    print("unlocked")
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    handle.close()
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="repo_lock.py")
    parser.add_argument("command", choices=["acquire", "release", "status"])
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument("--lock-file", default=str(DEFAULT_LOCK_FILE))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    lock_file = Path(args.lock_file)

    if args.command == "acquire":
        ok = acquire_lock(lock_file=lock_file, timeout=args.timeout)
        if ok:
            return 0
        print(
            f"timed out acquiring lock {lock_file} after {args.timeout}s",
            file=sys.stderr,
        )
        return 1

    if args.command == "release":
        release_lock()
        return 0

    if args.command == "status":
        return _cli_status(lock_file)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
