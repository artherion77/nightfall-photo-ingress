"""Test bootstrap for the src-layout package tree.

The test suite imports the installed package name directly. During local test
execution we prepend the repository's `src` directory to `sys.path` so tests can
run before or without an editable install refresh.
"""

from __future__ import annotations

import sys
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
