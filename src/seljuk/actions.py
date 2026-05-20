"""Levy-phase action handlers (Phase 2).

Pay, Disband, Muster (Lords / Vassals / Transport / Capabilities / Themata),
Call to Arms options, Arts of War draw, and Loyalty Checks. Each handler
validates against the rules and either mutates state or raises IllegalAction
with a code and rule citation.
"""
