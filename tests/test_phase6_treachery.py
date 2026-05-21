"""Phase 6 (R3): Treachery -> Plan -> Loyalty Check (1.4); Imperial Coffers (R14)."""
import pytest

from seljuk import scenarios as S, engine, campaign
from seljuk.rng import DiceRoller
from seljuk.state import IllegalAction


def _campaign_with_treachery(side="seljuk"):
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    # Mustered Lords on both sides so 5.2 doesn't fire.
    gs.meta.notes["treachery_side"] = side
    gs.meta.notes["treachery_no_command_side"] = "roman" if side == "seljuk" else "seljuk"
    campaign.start_campaign(gs)
    return gs


def test_treachery_event_sets_flags_r8_s16_s19():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.meta.phase = "levy"
    gs.meta.pending.append({"type": "event_pending_resolution", "card": "R8", "side": "roman", "tags": ["treachery"]})
    engine.apply_action(gs, {"type": "resolve_event", "card": "R8", "args": {}})
    assert gs.meta.notes["treachery_side"] == "roman"
    assert gs.meta.notes["treachery_no_command_side"] == "seljuk"


def test_only_one_treachery_per_arts_of_war_phase():
    gs = _campaign_with_treachery("seljuk")
    from seljuk import events
    r = events._set_treachery(gs, "roman")
    assert r.get("no_op")  # already a Treachery this phase


def test_plan_size_increases_for_treachery_and_no_command_sides():
    gs = _campaign_with_treachery("seljuk")  # Spring 1068 base 7
    assert campaign.plan_size(gs, "seljuk") == 8   # +1 Treachery card
    assert campaign.plan_size(gs, "roman") == 8     # +1 forced No Command


def test_build_plan_requires_treachery_card_for_that_side():
    gs = _campaign_with_treachery("seljuk")
    with pytest.raises(IllegalAction):  # 8 cards but no "treachery" entry
        engine.apply_action(gs, {"type": "build_plan", "side": "seljuk",
                                 "cards": ["alp_arslan"] * 3 + ["no_command"] * 5})


def test_revealing_treachery_triggers_loyalty_then_resolves():
    gs = _campaign_with_treachery("seljuk")
    engine.apply_action(gs, {"type": "build_plan", "side": "seljuk",
                             "cards": ["treachery", "alp_arslan", "alp_arslan"] + ["no_command"] * 5})
    engine.apply_action(gs, {"type": "build_plan", "side": "roman",
                             "cards": ["romanos_diogenes", "romanos_diogenes"] + ["no_command"] * 6})
    # Seljuk reveals first card = treachery -> pending Loyalty Check.
    assert any(p["type"] == "loyalty_check" for p in gs.meta.pending)
    moves = engine.legal_moves(gs)
    assert {m["target"] for m in moves} == {"robert_crepin", "roussel_de_bailleul"}
    r = engine.apply_action(gs, {"type": "resolve_loyalty", "target": "robert_crepin"})
    lc = r["loyalty"]
    assert lc["switched"] == (lc["natural"] == 6 or (lc["natural"] != 1 and lc["modified"] > lc["fealty"]))
    assert not any(p["type"] == "loyalty_check" for p in gs.meta.pending)


def test_imperial_coffers_discard_triggers_loyalty_r14():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    gs.roman.capabilities_in_play = ["R14"]
    rob = gs.lords["robert_crepin"]; rob.side = "seljuk"; rob.mustered = True; rob.cylinder = "edessa"
    rom = gs.lords["chatatourios"]; rom.mustered = True; rom.cylinder = "manbij"  # adjacent to Edessa
    r = engine.apply_action(gs, {"type": "discard_imperial_coffers", "target": "robert_crepin"})
    assert "loyalty" in r
    assert "R14" not in gs.roman.capabilities_in_play  # discarded
