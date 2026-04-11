#!/usr/bin/env python3
"""Shared virtual-environment bootstrap helpers for CLI entrypoints."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_running_in_venv(venv_name: str = ".venv") -> bool:
    """Return True when current interpreter appears to be from the target venv."""
    try:
        if Path(sys.prefix).name == venv_name:
            return True
    except Exception:
        pass

    current = Path(sys.executable).resolve()
    return venv_name in current.parts


def ensure_venv(
    script_path: Path,
    venv_name: str = ".venv",
    guard_var: str | None = None,
    repo_root: Path | None = None,
) -> None:
    """Re-exec the current script under repo venv Python when needed.

    No-op when:
    - venv Python does not exist
    - already running in target interpreter
    - reentry guard is set

    When *repo_root* is provided the venv is resolved relative to it instead
    of being derived from the parent directory of *script_path*.
    """
    script = Path(script_path).resolve()
    effective_root = Path(repo_root).resolve() if repo_root is not None else script.parent

    if os.name == "nt":
        venv_python = effective_root / venv_name / "Scripts" / "python.exe"
    else:
        venv_python = effective_root / venv_name / "bin" / "python"

    if not venv_python.exists():
        return

    # Use sys.prefix to check whether the venv is active rather than
    # comparing resolved executable paths.  On systems where the venv
    # Python is a symlink to the system interpreter (common on
    # Debian/Ubuntu), resolved paths are identical and the old check
    # would incorrectly skip re-exec.
    if is_running_in_venv(venv_name):
        return

    effective_guard = guard_var or f"NIGHTFALL_{script.stem.upper()}_VENV_REEXEC"
    if os.environ.get(effective_guard) == "1":
        return

    env = os.environ.copy()
    env[effective_guard] = "1"
    os.execve(str(venv_python), [str(venv_python), str(script), *sys.argv[1:]], env)
