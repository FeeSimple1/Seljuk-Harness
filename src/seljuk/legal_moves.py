"""The move enumerator (Phase 2+).

The implementation lives in ``engine.legal_moves`` (which also owns the Levy
step machine); this module re-exports it as the stable public name. It MUST
mirror every pre-check the handlers enforce (CROSS_PROJECT_LESSONS.md 1-2).
"""
from __future__ import annotations

from .engine import legal_moves

__all__ = ["legal_moves"]
