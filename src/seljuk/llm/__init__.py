"""LLM-consumer interface (Phase 5): hidden-info view, briefing, lookups, and
the LLMSession that routes actions through the same engine as every other path."""
from .session import LLMSession

__all__ = ["LLMSession"]
