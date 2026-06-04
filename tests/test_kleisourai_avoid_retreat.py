"""SMOKE-008 follow-up: Kleisourai (R23) also fires when a Seljuk Lord crosses a
Pass while *Avoiding Battle* or *Retreating* (not only on a March). Both are
collected during the action and offered to the Roman holder as a reaction before
the Command card ends (resumes Feed/Pay/Disband afterward)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, engine, campaign as C, battle

# germanikeia <-> mopsuestia is a Pass; germanikeia <-> melitene is a Road.
BATTLE_LOC, PASS_DEST, ROAD_ORIGIN = "germanikeia", "mopsuestia", "melitene"


def _gs():
    return S.load_scenario("emperor_and_the_lion", seed=1)


def _kl(gs):
    return next((p for p in gs.meta.pending if p["type"] == "kleisourai"), None)


def test_avoid_across_pass_offers_reaction_then_resumes():
    gs = _gs()
    rom = gs.lords["romanos_diogenes"]; rom.mustered = True; rom.cylinder = BATTLE_LOC
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = BATTLE_LOC
    aa.forces = {"turkic_horse": 3}
    gs.roman.held_events.append("R23")
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.active_player = "roman"; gs.meta.active_lord = "romanos_diogenes"
    gs.meta.active_card = "romanos_diogenes"; gs.meta.actions_remaining = 0
    gs.seljuk.command_plan = []; gs.seljuk.plan_pointer = 0
    gs.roman.command_plan = ["romanos_diogenes"]; gs.roman.plan_pointer = 1
    gs.meta.pending = [{"type": "approach_response", "locale": BATTLE_LOC,
                        "attackers": ["romanos_diogenes"], "defenders": ["alp_arslan"],
                        "from": ROAD_ORIGIN}]
    before = sum(aa.forces.values())
    engine.apply_action(gs, {"type": "respond_approach",
                             "choices": {"alp_arslan": {"action": "avoid", "to": PASS_DEST}}})
    assert aa.cylinder == PASS_DEST                      # avoided across the Pass
    p = _kl(gs)
    assert p is not None and p["trigger"] == "reaction" and "alp_arslan" in p["movers"]
    assert {m["type"] for m in engine.legal_moves(gs)} == {"play_kleisourai", "decline_kleisourai"}
    engine.apply_action(gs, {"type": "play_kleisourai"})
    assert "R23" not in gs.roman.held_events
    assert sum(gs.lords["alp_arslan"].forces.values()) in (before, before - 1)
    assert _kl(gs) is None                               # card-end resumed


def test_avoid_across_pass_decline_takes_no_hit():
    gs = _gs()
    gs.lords["romanos_diogenes"].mustered = True; gs.lords["romanos_diogenes"].cylinder = BATTLE_LOC
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = BATTLE_LOC; aa.forces = {"turkic_horse": 3}
    gs.roman.held_events.append("R23")
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.active_player = "roman"; gs.meta.active_lord = "romanos_diogenes"
    gs.meta.active_card = "romanos_diogenes"; gs.meta.actions_remaining = 0
    gs.roman.command_plan = ["romanos_diogenes"]; gs.roman.plan_pointer = 1
    gs.meta.pending = [{"type": "approach_response", "locale": BATTLE_LOC,
                        "attackers": ["romanos_diogenes"], "defenders": ["alp_arslan"], "from": ROAD_ORIGIN}]
    engine.apply_action(gs, {"type": "respond_approach",
                             "choices": {"alp_arslan": {"action": "avoid", "to": PASS_DEST}}})
    engine.apply_action(gs, {"type": "decline_kleisourai"})
    assert sum(gs.lords["alp_arslan"].forces.values()) == 3
    assert "R23" in gs.roman.held_events
    assert _kl(gs) is None


def test_avoid_across_road_offers_no_reaction():
    gs = _gs()
    gs.lords["romanos_diogenes"].mustered = True; gs.lords["romanos_diogenes"].cylinder = BATTLE_LOC
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = BATTLE_LOC; aa.forces = {"turkic_horse": 3}
    gs.roman.held_events.append("R23")
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.active_player = "roman"; gs.meta.active_lord = "romanos_diogenes"
    gs.meta.active_card = "romanos_diogenes"; gs.meta.actions_remaining = 0
    gs.roman.command_plan = ["romanos_diogenes"]; gs.roman.plan_pointer = 1
    gs.meta.pending = [{"type": "approach_response", "locale": BATTLE_LOC,
                        "attackers": ["romanos_diogenes"], "defenders": ["alp_arslan"], "from": PASS_DEST}]
    # Avoid to lykandos (a Road from germanikeia) -> not a Pass crossing.
    engine.apply_action(gs, {"type": "respond_approach",
                             "choices": {"alp_arslan": {"action": "avoid", "to": "lykandos"}}})
    assert _kl(gs) is None


def test_retreat_across_pass_collects_crosser():
    gs = _gs()
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = BATTLE_LOC; aa.forces = {"turkic_horse": 2}
    gs.locales[PASS_DEST].conquered_side = "seljuk"      # make the Pass dest a legal Seljuk retreat
    ctx = battle.DecisionContext([("retreat", PASS_DEST)])
    fate = battle._lord_fate(gs, aa, "defender", BATTLE_LOC, False, ctx)
    assert fate == "retreat" and aa.cylinder == PASS_DEST
    assert "alp_arslan" in gs.meta.notes.get("_kleisourai_crossers", [])


def test_after_card_gate_raises_reaction_for_collected_retreater():
    gs = _gs()
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = PASS_DEST; aa.forces = {"turkic_horse": 2}
    gs.roman.held_events.append("R23")
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.active_player = "roman"; gs.meta.active_lord = "romanos_diogenes"
    gs.meta.active_card = "romanos_diogenes"; gs.meta.actions_remaining = 0
    gs.roman.command_plan = ["romanos_diogenes"]; gs.roman.plan_pointer = 1
    gs.meta.notes["_kleisourai_crossers"] = ["alp_arslan"]
    C._after_card(gs)
    p = _kl(gs)
    assert p is not None and p["trigger"] == "reaction" and p["resume"] == "after_card"
    engine.apply_action(gs, {"type": "play_kleisourai"})
    assert "R23" not in gs.roman.held_events and _kl(gs) is None
