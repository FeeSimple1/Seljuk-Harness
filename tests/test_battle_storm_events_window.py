"""SMOKE-008 follow-up: R21 Nomadic Tribes / S21 Common Cultural Cause are
"before/in Battle or Storm" Held Events. Like the other in-Battle holds, they
are played via the battle_events parameter (not a standalone command-menu item)
and remove up to 2 Turkic Horse at the Active Lord's Locale. Storm honors only
these Turkic-removal holds; in-Battle-only holds are filtered out. The available
holds are advertised on the approach/storm menu entries for discoverability."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, engine, battle, campaign as C


def _gs():
    return S.load_scenario("emperor_and_the_lion", seed=1)


def _seljuk_with_turkic(gs, at="ani", n=3):
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = at
    aa.forces = {"turkic_horse": n}
    return aa


def test_r21_consumed_in_battle_removes_two_turkic():
    gs = _gs(); aa = _seljuk_with_turkic(gs, n=3)
    gs.roman.held_events.append("R21")
    battle._consume_battle_events(gs, {"roman": ["R21"]}, locale="ani")
    assert aa.forces["turkic_horse"] == 1                 # removed up to 2
    assert "R21" not in gs.roman.held_events and "R21" in gs.roman.draw_deck


def test_s21_consumed_removes_turkic():
    gs = _gs(); aa = _seljuk_with_turkic(gs, n=2)
    gs.seljuk.held_events.append("S21")
    battle._consume_battle_events(gs, {"seljuk": ["S21"]}, locale="ani")
    assert aa.forces["turkic_horse"] == 0                 # both removed (can force a Disband)
    assert "S21" in gs.seljuk.draw_deck


def test_storm_allow_filter_excludes_battle_only_holds():
    gs = _gs(); aa = _seljuk_with_turkic(gs, n=3)
    gs.roman.held_events.extend(["R2", "R21"])            # R2 is in-Battle only
    played, _cc, _charge = battle._consume_battle_events(
        gs, {"roman": ["R2", "R21"]}, locale="ani", allow={"R21", "S21"})
    assert "R21" in played["roman"] and "R2" not in played["roman"]
    assert "R2" in gs.roman.held_events                   # not consumed in a Storm
    assert aa.forces["turkic_horse"] == 1                 # R21 still fired


def test_not_offered_as_standalone_command_menu_item():
    # They are battle/storm event parameters, never plain command-menu entries.
    gs = _gs(); _seljuk_with_turkic(gs)
    gs.roman.held_events.append("R21"); gs.seljuk.held_events.append("S21")
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.active_player = "seljuk"; gs.meta.active_lord = "alp_arslan"
    gs.meta.actions_remaining = 2; gs.meta.notes["card_full_actions"] = 2
    cards = {m.get("card") for m in engine.legal_moves(gs) if m["type"] == "play_hold_event"}
    assert "R21" not in cards and "S21" not in cards


def test_approach_entry_advertises_available_battle_holds():
    gs = _gs()
    gs.lords["alp_arslan"].mustered = True; gs.lords["alp_arslan"].cylinder = "ani"
    gs.lords["romanos_diogenes"].mustered = True; gs.lords["romanos_diogenes"].cylinder = "ani"
    gs.roman.held_events.append("R21")
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.pending = [{"type": "approach_response", "locale": "ani",
                        "attackers": ["alp_arslan"], "defenders": ["romanos_diogenes"]}]
    entry = next(m for m in C.legal_moves_campaign(gs) if m["type"] == "respond_approach")
    assert "R21" in entry["_battle_holds_available"]["defender"]


def test_standalone_resolver_still_works():
    # Backwards-compatible do/apply escape hatch (existing behavior).
    gs = _gs(); _seljuk_with_turkic(gs, n=2)
    gs.roman.held_events = ["R21"]
    engine.apply_action(gs, {"type": "play_hold_event", "card": "R21",
                             "args": {"locale": "ani", "count": 2}})
    assert gs.lords["alp_arslan"].forces["turkic_horse"] == 0
