"""Domain logic for the photo ingress application.

This module contains core business concepts: registry state, storage decisions,
and ingest engine policies, independent of data sources.
"""

from .ingest import IngestDecisionEngine
from .registry import Registry

__all__ = ["Registry", "IngestDecisionEngine"]
