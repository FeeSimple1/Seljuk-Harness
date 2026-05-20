"""The move enumerator (Phase 2+).

Emits the palette of currently-legal actions for the active side, each with its
grammar, cost, prerequisites, and a rule citation. This is the primary surface
an LLM consumer uses. It MUST mirror every pre-check that the handlers enforce;
divergence between this enumerator and the handlers is the single
highest-yield bug class (CROSS_PROJECT_LESSONS.md sections 1-2), guarded by the
round-trip sweep.
"""
