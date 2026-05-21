"""Smoke coverage for presentation/utility modules: a render crash would break
the LLM interface, so exercise every view across all scenarios."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, render, map as gmap, static_data as sd
from seljuk.llm import tools, briefing


@pytest.mark.parametrize("scenario", S.SCENARIOS)
def test_render_all_views_do_not_crash(scenario):
    gs = S.load_scenario(scenario, seed=1)
    for fn in (render.summary, render.verbose, render.calendar_view, render.thema_view):
        out = fn(gs)
        assert isinstance(out, str) and out
    # per-lord and per-locale views
    any_lord = next(iter(gs.lords))
    assert render.lord_view(gs, any_lord)
    any_loc = sd.all_locale_ids()[0]
    assert render.locale_view(gs, any_loc)


def test_render_lord_view_mustered_on_map():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = "ani"
    aa.forces = {"turkic_horse": 4}; aa.assets.coin = 2
    assert "Alp Arslan" in render.lord_view(gs, "alp_arslan")


def test_legal_moves_reexport_is_engine_legal_moves():
    from seljuk import legal_moves as lm
    from seljuk import engine
    assert lm.legal_moves is engine.legal_moves


def test_llm_tool_lookups():
    assert tools.lookup_card("S1")["id"] == "S1"
    assert tools.lookup_lord("alp_arslan")["id"] == "alp_arslan"
    loc = tools.lookup_locale("aleppo")
    assert loc["id"] == "aleppo"
    assert isinstance(tools.list_cards_for_side("seljuk"), list)
    assert tools.list_cards_for_side("seljuk")


def test_briefing_renders_with_pending_and_history():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    gs.meta.pending.append({"type": "loyalty_check", "_owed_by": "roman"})
    gs.history.append({"action": {"type": "cmd_pass"}})
    text = briefing.briefing(gs)
    assert "Pending decisions" in text


def test_map_allegiance_and_thema_helpers():
    assert isinstance(gmap.allegiance("aleppo"), str) and gmap.allegiance("aleppo")
    # thema_of returns a Thema name or None
    gmap.thema_of("aleppo")
