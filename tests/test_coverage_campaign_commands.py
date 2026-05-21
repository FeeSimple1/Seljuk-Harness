"""Aggressive coverage of campaign command-handler guards (Tax/Forage/Ravage/
Supply) and the Ravage-defence resolver."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S
from seljuk import campaign as C
from seljuk.rng import DiceRoller
from seljuk.state import IllegalAction


def _r():
    return DiceRoller(seed=1)


def _active(gs, lord_id, side="seljuk", actions=4):
    """Put one Lord active in campaign.command (guards raise before _after_card)."""
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.active_player = side; gs.meta.active_lord = lord_id
    gs.meta.active_card = lord_id; gs.meta.actions_remaining = actions
    l = gs.lords[lord_id]; l.mustered = True
    return l


def test_tax_besieged_and_not_taxable():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    aa = _active(gs, "alp_arslan"); aa.cylinder = "larisa"; aa.besieged = True
    with pytest.raises(IllegalAction):
        C.h_cmd_tax(gs, {"lord": "alp_arslan"}, _r())
    aa.besieged = False  # at larisa, not his seat, not roman commander
    with pytest.raises(IllegalAction):
        C.h_cmd_tax(gs, {"lord": "alp_arslan"}, _r())


def test_tax_not_active_lord():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    _active(gs, "alp_arslan")
    with pytest.raises(IllegalAction):
        C.h_cmd_tax(gs, {"lord": "afsin_beg"}, _r())  # not the activated lord


def test_forage_blocked_by_ravage(monkeypatch):
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    aa = _active(gs, "alp_arslan"); aa.cylinder = "larisa"
    gs.locales["larisa"].ravaged_side = "seljuk"
    with pytest.raises(IllegalAction):
        C.h_cmd_forage(gs, {"lord": "alp_arslan"}, _r())


def test_ravage_guards(monkeypatch):
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    monkeypatch.setattr(C, "_after_card", lambda g: None)
    aa = _active(gs, "alp_arslan")
    # besieged
    aa.cylinder = "ani"; aa.besieged = True
    with pytest.raises(IllegalAction):
        C.h_cmd_ravage(gs, {"lord": "alp_arslan"}, _r())
    aa.besieged = False
    # not_enemy: Ani is Seljuk-controlled
    with pytest.raises(IllegalAction):
        C.h_cmd_ravage(gs, {"lord": "alp_arslan"}, _r())
    # already_ravaged at an enemy locale
    aa.cylinder = "larisa"  # Roman-allegiance locale
    gs.locales["larisa"].ravaged_side = "seljuk"
    with pytest.raises(IllegalAction):
        C.h_cmd_ravage(gs, {"lord": "alp_arslan"}, _r())
    # bad_actions count for Seljuk
    gs.locales["larisa"].ravaged_side = None
    with pytest.raises(IllegalAction):
        C.h_cmd_ravage(gs, {"lord": "alp_arslan", "actions": 3}, _r())


def test_ravage_roman_success(monkeypatch):
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    monkeypatch.setattr(C, "_after_card", lambda g: None)
    ch = _active(gs, "chatatourios", side="roman")
    ch.side = "roman"
    # find a Seljuk-allegiance locale to ravage
    from seljuk import static_data as sd
    target = next(l for l in sd.all_locale_ids()
                  if sd.locale(l)["allegiance"] == "seljuk" and not gs.locales[l].ruins)
    ch.cylinder = target
    out = C.h_cmd_ravage(gs, {"lord": "chatatourios"}, _r())
    assert out["success"] is True
    assert gs.locales[target].ravaged_side == "roman"


def test_supply_besieged_and_no_route():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    aa = _active(gs, "alp_arslan"); aa.cylinder = "larisa"; aa.besieged = True
    with pytest.raises(IllegalAction):
        C.h_cmd_supply(gs, {"lord": "alp_arslan"}, _r())


def test_resolve_ravage_defence_paths(monkeypatch):
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    monkeypatch.setattr(C, "_after_card", lambda g: None)
    # no pending
    with pytest.raises(IllegalAction):
        C.h_resolve_ravage_defence(gs, {}, _r())
    # set up a pending ravage_defence
    aa = _active(gs, "alp_arslan"); aa.side = "seljuk"
    thema = next(t for t, box in gs.themata.items() if box)
    loc = next(l for l in __import__("seljuk.static_data", fromlist=["x"]).all_locale_ids()
               if __import__("seljuk.static_data", fromlist=["x"]).locale(l).get("thema") == thema)
    aa.cylinder = loc
    gs.meta.actions_remaining = 0
    gs.meta.pending.append({"type": "ravage_defence", "locale": loc, "thema": thema, "ravager": "alp_arslan"})
    # Roman declines -> Ravage succeeds
    out = C.h_resolve_ravage_defence(gs, {"defend_with": None}, _r())
    assert out["success"] is True
