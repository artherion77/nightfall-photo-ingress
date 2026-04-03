"""Shared pytest configuration and fixtures for all tests."""

import sys
from pathlib import Path

# Ensure the package is importable
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Re-export API fixtures used by Chunk 1 endpoint contract tests.
from tests.api_test_support import *  # noqa: F401,F403
