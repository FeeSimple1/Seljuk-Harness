"""Combat-aggressive self-play (Phase 6; not shipped). Seeks Battle/Siege/Storm.

Where the greedy self_play driver advances the turn structure, this agent prefers
March-toward-enemy, Stand on Approach, Besiege then Storm — exercising the combat
paths (the lessons note that combat-seeking agents surface a different bug class
than greedy ones). Used for bug-finding; drives every scenario to terminal.

Usage:  PYTHONPATH=src python3 scripts/strategic_agent.py <scenario> --seed N
"""
from __future__ import annotations

import argparse

from seljuk.llm import LLMSession
from seljuk.state import IllegalAction
from self_play import _resolve_pending, _build_plan_action  # type: ignore


def _enemy_target(gs, mv) -> bool:
    """True if a cmd_march destination holds an enemy Lord or an enemy Stronghold."""
    from seljuk import static_data as sd, campaign
    to = mv.get("to")
    side = gs.lords[mv["lord"]].side
    enemy = "roman" if side == "seljuk" else "seljuk"
    if any(l.mustered and l.cylinder == to and l.side == enemy for l in gs.lords.values()):
        return True
    loc = sd.locale(to)
    return loc.get("is_stronghold") and not gs.locales[to].ruins and \
        campaign.actions.current_allegiance(gs, to) == enemy


def _pick(gs, moves, types):
    # Combat first: Storm, then Surrender-Siege, then March-to-enemy, then Ravage.
    if "cmd_storm" in types:
        return types["cmd_storm"]
    if "cmd_siege" in types:
        return types["cmd_siege"]
    marches = [m for m in moves if m["type"] == "cmd_march"]
    toward = [m for m in marches if _enemy_target(gs, m)]
    if toward:
        return toward[0]
    if "cmd_ravage" in types:
        return types["cmd_ravage"]
    if marches:
        return marches[0]
    return None


def play_game(scenario: str, seed: int = 1, max_steps: int = 6000) -> dict:
    s = LLMSession.start_new(scenario, seed)
    steps = 0
    while not s.is_over() and steps < max_steps:
        steps += 1
        if s.gs.meta.pending:
            _resolve_pending(s)
            continue
        moves = s.legal_actions()
        if not moves:
            break
        types = {m["type"]: m for m in moves}
        if "build_plan" in types:
            s.apply(_build_plan_action(s, types["build_plan"]))
            continue
        if "pass_step" in types:  # Levy: advance
            s.apply({"type": "pass_step"})
            continue
        chosen = _pick(s.gs, moves, types)
        if chosen is None:
            chosen = types.get("end_activation") or moves[0]
        try:
            s.apply({k: v for k, v in chosen.items() if not k.startswith("_")})
        except IllegalAction:
            s.apply(types.get("end_activation") or {"type": "end_activation"})
    return {"scenario": scenario, "seed": seed, "steps": steps, "over": s.is_over(),
            "winner": s.winner(), "phase": s.gs.meta.phase, "box": s.gs.meta.calendar_box}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario"); ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    print(play_game(a.scenario, a.seed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
