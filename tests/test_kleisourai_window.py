"""SMOKE-008 follow-up: Kleisourai (R23) is a Roman reaction when a Seljuk Lord
crosses a Pass. After a Seljuk March across a Pass, the Roman holder is offered
the reaction (play -> 1 Hit per crossing Lord, then arrival resumes; or decline)
as a blocking decision before the Approach/Besiege is resolved."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, engine, campaign as C
from seljuk.invariants import check_invariants

PASS_FROM, PASS_TO = "mopsuestia", "germanikeia"   # a Pass edge on the map


def _gs():
    return S.load_scenario("emperor_and_the_lion", seed=1)


def _seljuk_marcher(gs, lid="alp_arslan", at=PASS_FROM, actions=5):
    l = gs.lords[lid]
    l.mustered = True; l.cylinder = at; l.besieged = False
    l.forces = {"turkic_horse": 3}
    l.assets.loot = 0; l.assets.provender = 0; l.assets.carts = 1
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.active_player = "seljuk"; gs.meta.active_lord = lid
    gs.meta.active_card = lid; gs.meta.actions_remaining = actions
    gs.meta.notes["card_full_actions"] = actions
    gs.seljuk.command_plan = [lid]; gs.seljuk.plan_pointer = 1
    gs.roman.command_plan = []; gs.roman.plan_pointer = 0
    return l


def _kl(gs):
    return next((p for p in gs.meta.pending if p["type"] == "kleisourai"), None)


def _march(gs, lid="alp_arslan"):
    return engine.apply_action(gs, {"type": "cmd_march", "lord": lid, "to": PASS_TO, "way_type": "pass"})


def test_offered_after_seljuk_pass_march():
    gs = _gs(); _seljuk_marcher(gs); gs.roman.held_events.append("R23")
    _march(gs)
    assert _kl(gs) is not None
    assert {m["type"] for m in engine.legal_moves(gs)} == {"play_kleisourai", "decline_kleisourai"}
    assert gs.lords["alp_arslan"].cylinder == PASS_TO   # the Lord did cross


def test_play_applies_one_hit_per_mover_and_consumes_card():
    gs = _gs(); _seljuk_marcher(gs); gs.roman.held_events.append("R23")
    before = sum(gs.lords["alp_arslan"].forces.values())
    _march(gs)
    r = engine.apply_action(gs, {"type": "play_kleisourai"})
    assert "R23" not in gs.roman.held_events and "R23" in gs.roman.draw_deck
    assert len(r["hits"]) == 1                       # one moving Lord
    after = sum(gs.lords["alp_arslan"].forces.values())
    assert after in (before, before - 1)             # eliminated iff Protection failed
    assert _kl(gs) is None


def test_decline_resumes_with_no_hit():
    gs = _gs(); _seljuk_marcher(gs); gs.roman.held_events.append("R23")
    before = sum(gs.lords["alp_arslan"].forces.values())
    _march(gs)
    engine.apply_action(gs, {"type": "decline_kleisourai"})
    assert sum(gs.lords["alp_arslan"].forces.values()) == before
    assert "R23" in gs.roman.held_events
    assert _kl(gs) is None


def test_not_offered_when_roman_lacks_card():
    gs = _gs(); _seljuk_marcher(gs)                  # Roman does not hold R23
    _march(gs)
    assert _kl(gs) is None


def test_not_offered_on_non_pass_march():
    gs = _gs(); gs.roman.held_events.append("R23")
    l = _seljuk_marcher(gs, at="edessa")
    # edessa->harran is a Road (not a Pass); march there instead
    import seljuk.map as gmap
    road_to = next(w["to"] for w in gmap.ways_from("edessa") if w["type"] != "pass")
    engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": road_to})
    assert _kl(gs) is None


def test_co_location_invariant_holds_during_reaction():
    gs = _gs(); _seljuk_marcher(gs); gs.roman.held_events.append("R23")
    # Put a Roman Lord at the destination so the crossing co-locates enemies.
    rom = gs.lords["romanos_diogenes"]; rom.mustered = True; rom.cylinder = PASS_TO; rom.besieged = False
    _march(gs)
    assert _kl(gs) is not None
    assert check_invariants(gs) == []                # kleisourai locale excluded
    engine.apply_action(gs, {"type": "decline_kleisourai"})
    # arrival now resolves -> an Approach is owed (still a legal momentary contact)
    assert check_invariants(gs) == []
