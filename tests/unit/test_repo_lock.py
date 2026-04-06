from __future__ import annotations

import os
import fcntl
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE = REPO_ROOT / "dev" / "lib" / "repo_lock.py"

sys.path.insert(0, str(REPO_ROOT / "dev" / "lib"))
import repo_lock as repo_lock_module  # noqa: E402
from repo_lock import RepoLock, _cli_status, acquire_lock, main, release_lock  # noqa: E402


@pytest.fixture(autouse=True)
def _cleanup_env() -> None:
    os.environ.pop("DEVCTL_GLOBAL_LOCK_HELD", None)
    yield
    os.environ.pop("DEVCTL_GLOBAL_LOCK_HELD", None)
    release_lock()


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MODULE), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _hold_os_lock(lock_file: Path, ready: threading.Event, release_now: threading.Event) -> None:
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    with lock_file.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        ready.set()
        release_now.wait(timeout=2)
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def test_acquire_lock_sets_reentry_env(tmp_path: Path) -> None:
    lock_file = tmp_path / "repo.lock"
    assert acquire_lock(lock_file=lock_file, timeout=1) is True
    assert os.environ.get("DEVCTL_GLOBAL_LOCK_HELD") == "1"


def test_release_lock_clears_reentry_env(tmp_path: Path) -> None:
    lock_file = tmp_path / "repo.lock"
    assert acquire_lock(lock_file=lock_file, timeout=1) is True
    release_lock()
    assert os.environ.get("DEVCTL_GLOBAL_LOCK_HELD") is None


def test_release_lock_when_not_held_is_noop() -> None:
    release_lock()
    assert os.environ.get("DEVCTL_GLOBAL_LOCK_HELD") is None


def test_reentry_guard_skips_lock_attempt(tmp_path: Path) -> None:
    os.environ["DEVCTL_GLOBAL_LOCK_HELD"] = "1"
    lock_file = tmp_path / "repo.lock"
    assert acquire_lock(lock_file=lock_file, timeout=0) is True


def test_repo_lock_context_manager_sets_and_clears_env(tmp_path: Path) -> None:
    lock_file = tmp_path / "repo.lock"
    with RepoLock(lock_file=lock_file, timeout_sec=1):
        assert os.environ.get("DEVCTL_GLOBAL_LOCK_HELD") == "1"
    assert os.environ.get("DEVCTL_GLOBAL_LOCK_HELD") is None


def test_repo_lock_reentrant_context_noop(tmp_path: Path) -> None:
    os.environ["DEVCTL_GLOBAL_LOCK_HELD"] = "1"
    with RepoLock(lock_file=tmp_path / "repo.lock", timeout_sec=1):
        assert os.environ.get("DEVCTL_GLOBAL_LOCK_HELD") == "1"


def test_repo_lock_timeout_raises(tmp_path: Path) -> None:
    lock_file = tmp_path / "repo.lock"
    ready = threading.Event()
    release_now = threading.Event()
    t = threading.Thread(target=_hold_os_lock, args=(lock_file, ready, release_now), daemon=True)
    t.start()
    ready.wait(timeout=1)
    try:
        second = RepoLock(lock_file=lock_file, timeout_sec=0)
        with pytest.raises(TimeoutError):
            second.acquire()
    finally:
        release_now.set()
        t.join(timeout=2)


def test_cli_status_unlocked(tmp_path: Path) -> None:
    lock_file = tmp_path / "repo.lock"
    r = _run_cli("status", "--lock-file", str(lock_file))
    assert r.returncode == 0
    assert r.stdout.strip() == "unlocked"


def test_cli_status_locked(tmp_path: Path) -> None:
    lock_file = tmp_path / "repo.lock"
    holder = RepoLock(lock_file=lock_file, timeout_sec=1)
    holder.acquire()
    try:
        r = _run_cli("status", "--lock-file", str(lock_file))
        assert r.returncode == 0
        assert r.stdout.strip() == "locked"
    finally:
        holder.release()


def test_cli_status_in_process_unlocked(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = _cli_status(tmp_path / "repo.lock")
    assert rc == 0
    assert capsys.readouterr().out.strip() == "unlocked"


def test_cli_status_in_process_locked(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    lock_file = tmp_path / "repo.lock"
    ready = threading.Event()
    release_now = threading.Event()
    t = threading.Thread(target=_hold_os_lock, args=(lock_file, ready, release_now), daemon=True)
    t.start()
    ready.wait(timeout=1)
    try:
        rc = _cli_status(lock_file)
        assert rc == 0
        assert capsys.readouterr().out.strip() == "locked"
    finally:
        release_now.set()
        t.join(timeout=2)


def test_cli_acquire_success(tmp_path: Path) -> None:
    lock_file = tmp_path / "repo.lock"
    r = _run_cli("acquire", "--lock-file", str(lock_file), "--timeout", "1")
    assert r.returncode == 0


def test_cli_acquire_timeout(tmp_path: Path) -> None:
    lock_file = tmp_path / "repo.lock"

    ready = threading.Event()
    release_now = threading.Event()

    t = threading.Thread(target=_hold_os_lock, args=(lock_file, ready, release_now), daemon=True)
    t.start()
    ready.wait(timeout=1)
    try:
        r = _run_cli("acquire", "--lock-file", str(lock_file), "--timeout", "0")
        assert r.returncode == 1
        assert "timed out acquiring lock" in r.stderr
    finally:
        release_now.set()
        t.join(timeout=2)


def test_cli_release_success(tmp_path: Path) -> None:
    lock_file = tmp_path / "repo.lock"
    r = _run_cli("release", "--lock-file", str(lock_file))
    assert r.returncode == 0


def test_main_dispatch_status(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["status", "--lock-file", str(tmp_path / "repo.lock")])
    assert rc == 0
    assert capsys.readouterr().out.strip() in {"locked", "unlocked"}


def test_main_acquire_timeout_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    lock_file = tmp_path / "repo.lock"
    ready = threading.Event()
    release_now = threading.Event()
    t = threading.Thread(target=_hold_os_lock, args=(lock_file, ready, release_now), daemon=True)
    t.start()
    ready.wait(timeout=1)
    try:
        rc = main(["acquire", "--lock-file", str(lock_file), "--timeout", "0"])
        assert rc == 1
        assert "timed out acquiring lock" in capsys.readouterr().err
    finally:
        release_now.set()
        t.join(timeout=2)


def test_main_release_branch(tmp_path: Path) -> None:
    rc = main(["release", "--lock-file", str(tmp_path / "repo.lock")])
    assert rc == 0


def test_main_unknown_branch_returns_2(monkeypatch: pytest.MonkeyPatch) -> None:
    class _DummyParser:
        def parse_args(self, argv):
            return type("Args", (), {"command": "bogus", "lock_file": "/tmp/x", "timeout": 0})()

    monkeypatch.setattr(repo_lock_module, "_build_parser", lambda: _DummyParser())
    assert main(["ignored"]) == 2


def test_main_bad_args_raises_system_exit() -> None:
    with pytest.raises(SystemExit):
        main([])


def test_acquire_lock_timeout_returns_false(tmp_path: Path) -> None:
    lock_file = tmp_path / "repo.lock"
    ready = threading.Event()
    release_now = threading.Event()
    t = threading.Thread(target=_hold_os_lock, args=(lock_file, ready, release_now), daemon=True)
    t.start()
    ready.wait(timeout=1)
    try:
        assert acquire_lock(lock_file=lock_file, timeout=0) is False
    finally:
        release_now.set()
        t.join(timeout=2)


def test_timeout_blocks_until_release_then_acquires(tmp_path: Path) -> None:
    lock_file = tmp_path / "repo.lock"
    holder = RepoLock(lock_file=lock_file, timeout_sec=1)
    holder.acquire()

    def _release() -> None:
        time.sleep(0.15)
        holder.release()

    t = threading.Thread(target=_release, daemon=True)
    t.start()

    contender = RepoLock(lock_file=lock_file, timeout_sec=1)
    try:
        assert contender.acquire() is True
    finally:
        contender.release()
    t.join(timeout=1)
