"""Shared pytest configuration and fixtures for all tests."""

import sys
from pathlib import Path

# Ensure the package is importable
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Make API integration fixtures available to all sub-suites (must live in top-level conftest).
pytest_plugins = ["tests.integration.api.conftest"]
