"""Explicit keep-all policy for tests exercising later Campaign/Winter steps."""
from seljuk import engine


def keep_reset_cards(state):
    while pending := next((p for p in state.meta.pending if p["type"] == "reset_discard"), None):
        engine.apply_action(state, {"type": "reset_done", "side": pending["side"]})
