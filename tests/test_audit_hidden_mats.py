"""Optional Rule 6.1 Hidden Mats: a side cannot see the enemy's Mustered Lord
mats (Forces, Assets, Vassals, This-Lord Capabilities); board-visible state
(Locale, Service, Besieged) stays public. Off by default."""
import json

import pytest

from seljuk import cli, render, scenarios as S
from seljuk.llm import LLMSession, view
from seljuk.llm.compact import CompactInterface
from seljuk.state import VassalSlot, shift_vassal_service


def _mustered_enemy(gs, side):
    enemy = "roman" if side == "seljuk" else "seljuk"
    lid = next(l for l, x in gs.lords.items() if x.side == enemy)
    gs.lords[lid].mustered = True
    gs.lords[lid].forces = {"turkic_horse": 3}
    return lid


def test_hidden_mats_redacts_enemy_mustered_mats():
    gs = S.load_scenario("emperor_and_the_lion", options={"hidden_mats": True})
    lid = _mustered_enemy(gs, "seljuk")
    d = view.filtered_state(gs, "seljuk")
    e = d["lords"][lid]
    assert e["forces"] == "<hidden>" and e["assets"] == "<hidden>"
    assert e["vassals"] == "<hidden>" and e["capabilities"] == "<hidden>"
    assert e["cylinder"] == gs.lords[lid].cylinder          # Locale stays public
    assert e["mustered"] is True


def test_hidden_mats_keeps_own_mats_visible():
    gs = S.load_scenario("emperor_and_the_lion", options={"hidden_mats": True})
    own = next(l for l, x in gs.lords.items() if x.side == "seljuk")
    gs.lords[own].mustered = True; gs.lords[own].forces = {"ghulam_cavalry": 2}
    d = view.filtered_state(gs, "seljuk")
    assert d["lords"][own]["forces"] == {"ghulam_cavalry": 2}   # own Forces visible


def test_hidden_mats_off_by_default_shows_enemy_forces():
    gs = S.load_scenario("emperor_and_the_lion")
    lid = _mustered_enemy(gs, "seljuk")
    d = view.filtered_state(gs, "seljuk")
    assert d["lords"][lid]["forces"] == {"turkic_horse": 3}     # standard rules: visible


def _muster_alp_arslan_vassal(*, vassal_service=True, hidden_mats=True):
    session = LLMSession.start_new("emperor_and_the_lion", seed=1, options={
        "vassal_service": vassal_service, "hidden_mats": hidden_mats,
    })
    for kind in ("deploy_capability", "deploy_capability", "pass_step", "pass_step"):
        move = next(move for move in session.legal_actions() if move["type"] == kind)
        session.apply({key: value for key, value in move.items() if not key.startswith("_")})
    result = session.apply({"type": "levy_vassal", "lord": "alp_arslan", "vassal_index": 0})
    assert result["vassal_service_box"] == (4 if vassal_service else None)
    return session


def test_public_vassal_marker_in_player_views_after_legal_muster(tmp_path, capsys):
    session = _muster_alp_arslan_vassal()
    gs = session.gs
    before = gs.to_json()
    expected = [{"vassal_index": 0, "service_box": 4}]
    roman_lord = session.state("roman")["lords"]["alp_arslan"]
    assert roman_lord["public_vassal_service"] == expected
    assert all(roman_lord[field] == "<hidden>" for field in ("vassals", "forces", "assets", "capabilities"))
    assert session.state("seljuk")["lords"]["alp_arslan"]["public_vassal_service"] == expected
    assert session.state("seljuk")["lords"]["alp_arslan"]["vassals"][0]["levied"]
    compact = CompactInterface(session, player="roman")
    assert compact.inspect("lord", "alp_arslan", full=True)["data"]["current"] == roman_lord
    assert compact.inspect("state", full=True)["data"]["lords"]["alp_arslan"] == roman_lord
    assert "Vassal Service: Vassal #0 at box 4" in session.briefing("roman")

    saved = tmp_path / "game.json"
    session.save(str(saved))
    args = ["state", "--file", str(saved), "--side", "roman"]
    assert cli.main([*args, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["lords"]["alp_arslan"] == roman_lord
    assert cli.main([*args, "--lord", "alp_arslan"]) == 0
    focused = capsys.readouterr().out
    assert "Mat: <hidden>" in focused and "Vassal Service: Vassal #0 at box 4" in focused
    assert "Forces:" not in focused and "Assets:" not in focused
    assert cli.main([*args, "--calendar"]) == 0
    calendar_row = next(line for line in capsys.readouterr().out.splitlines() if "box  4" in line)
    assert "Vassal Service: Alp Arslan Vassal #0" in calendar_row
    assert gs.to_json() == before


@pytest.mark.parametrize("delta, box", [(-9, 0), (1, 5), (12, 13)])
def test_public_vassal_marker_tracks_calendar_shifts(delta, box):
    session = _muster_alp_arslan_vassal()
    gs = session.gs
    lord = gs.lords["alp_arslan"]
    before = session.state("roman")
    shift_vassal_service(gs, lord, delta)
    marker = session.state("roman")["lords"][lord.id]["public_vassal_service"]
    assert marker == [{"vassal_index": 0, "service_box": box}]
    before["lords"][lord.id]["public_vassal_service"] = marker
    assert session.state("roman") == before  # no change to the redacted mat
    calendar_row = next(line for line in render.calendar_view(gs).splitlines() if f"box {box:2d} " in line)
    assert "Vassal Service: Alp Arslan Vassal #0" in calendar_row


def test_public_service_shows_special_marker_and_hides_markers_on_the_mat():
    session = _muster_alp_arslan_vassal()
    gs = session.gs
    lord = gs.lords["alp_arslan"]
    lord.vassals[0].levied = False
    lord.vassals[0].service_box = None
    lord.vassals[0].unready = True
    lord.vassals.append(VassalSlot(forces={"ghulam_cavalry": 2}, special_name="elite_ghulam_cavalry",
                                   requires_capability="S20", levied=True, service_box=6))
    filtered = session.state("roman")["lords"][lord.id]
    assert filtered["vassals"] == "<hidden>"
    assert filtered["public_vassal_service"] == [{"special_name": "elite_ghulam_cavalry", "service_box": 6}]
    assert "elite ghulam cavalry at box 6" in render.lord_view(gs, lord.id, "roman")


@pytest.mark.parametrize("hidden_mats", [False, True])
def test_vassal_service_off_has_no_public_calendar_markers(hidden_mats):
    session = _muster_alp_arslan_vassal(vassal_service=False, hidden_mats=hidden_mats)
    assert "public_vassal_service" not in session.state("roman")["lords"]["alp_arslan"]
    assert "Vassal Service:" not in render.calendar_view(session.gs)
