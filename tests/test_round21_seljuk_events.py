"""Regression tests through the player menu for the S8 and S15 Events."""

import pytest

from seljuk import engine, scenarios
from seljuk.invariants import check_invariants
from seljuk.llm.compact import CompactInterface, InterfaceError
from seljuk.llm.session import LLMSession
from seljuk.state import Assets, IllegalAction

ALP = "alp_arslan"
ROMANOS = "romanos_diogenes"
THEMA = "Sebasteia"
LOCALE = "sebasteia"


def _draw(card, stage=None):
    # Stage Summer Levy and let the actual deck and RNG queue the Event.
    gs = scenarios.load_scenario("emperor_and_the_lion", seed={"S8": 4, "S15": 174}[card])
    gs.meta.calendar_box = 2
    gs.meta.notes["first_aow_done"] = True
    if stage:
        stage(gs)
    engine.start_levy(gs)
    assert [p["card"] for p in gs.meta.pending] == [card]
    assert check_invariants(gs) == []
    return gs


def _event(ui, card):
    [row] = ui.actions(type="resolve_event", card=card)["entries"]
    return row["id"], ui.details(row["id"])["help"]


def _apply_and_replay(ui, tmp_path, card, args):
    action_id, help_ = _event(ui, card)
    path = tmp_path / "pending.json"
    ui.session.save(path)
    restored = CompactInterface(LLMSession.load(path), player="seljuk")
    restored_id, restored_help = _event(restored, card)
    assert restored_help == help_
    ui.apply(action_id, parameters={"args": args})
    restored.apply(restored_id, parameters={"args": args})
    assert ui.gs.to_json() == restored.gs.to_json()
    assert ui.gs.meta.pending == []
    assert ui.gs.seljuk.draw_deck.count(card) == 1
    assert check_invariants(ui.gs) == []
    return ui.gs.history[-1]["result"]


def _pass_pay(session):
    ui = CompactInterface(session)
    [row] = ui.actions(type="pass_step")["entries"]
    ui.apply(row["id"])


@pytest.mark.parametrize(("args", "final"), [
    ({"lord": ALP, "to": "coin", "amount": 1}, (3, 1)),
    ({"lord": ALP, "to": "carts", "amount": 2}, (0, 4)),
    ({"lord": ALP, "to": "coin", "amount": 0}, (2, 2)),
    ({}, (2, 2)),
])
def test_s8_exchanges_only_on_the_chosen_seljuk_mat(tmp_path, args, final):
    gs = _draw("S8")
    ui = CompactInterface(LLMSession(gs), player="seljuk")
    _, help_ = _event(ui, "S8")
    assert set(help_["eligible_lords"]) == {ALP, "arisighi", "ibn_khan"}
    assert help_["max_amount_by_lord_and_destination"][ALP] == {"coin": 2, "carts": 2}
    _apply_and_replay(ui, tmp_path, "S8", args)
    assets = ui.gs.lords[ALP].assets
    assert (assets.coin, assets.carts) == final
    assert ui.gs.lords[ROMANOS].assets == gs.lords[ROMANOS].assets
    _pass_pay(ui.session)
    roman = CompactInterface(ui.session, player="roman")
    assert any(row["action"]["payer"] == ROMANOS and row["action"]["asset"] == "coin"
               for row in roman.actions(type="pay")["entries"])


def test_s8_rejects_bad_exchanges_without_consuming_the_event():
    gs = _draw("S8")
    ui = CompactInterface(LLMSession(gs), player="seljuk")
    action_id, _ = _event(ui, "S8")
    before = gs.to_json()
    for fields, code in [
        ({"lord": ROMANOS}, "bad_event_target"),
        ({"lord": "afsin_beg"}, "bad_event_target"),
        ({"to": "loot"}, "bad_direction"),
        ({"amount": 3}, "bad_amount"),
        ({"amount": -1}, "bad_amount"),
        ({"amount": True}, "bad_amount"),
        ({"amount": 1.5}, "bad_amount"),
    ]:
        args = {"lord": ALP, "to": "carts", "amount": 2, **fields}
        with pytest.raises(IllegalAction, match=code):
            ui.apply(action_id, parameters={"args": args})
        with pytest.raises(IllegalAction, match=code):
            engine.apply_action(gs, {"type": "resolve_event", "card": "S8", "args": args})
        assert ui.gs.to_json() == before


def _invest(gs, locale):
    gs.lords[ALP].cylinder = locale
    gs.locales[locale].siege_markers = 1


@pytest.mark.parametrize("symbols", [1, 2])
def test_s15_selects_either_native_infantry_counter(tmp_path, symbols):
    gs = _draw("S15", lambda gs: _invest(gs, "tephrike"))
    ui = CompactInterface(LLMSession(gs), player="seljuk")
    action_id, help_ = _event(ui, "S15")
    markers = help_["eligible_markers"]
    assert [(m["unit"], m["symbols"], m["marker_index"]) for m in markers] == [
        ("infantry", 1, 0), ("infantry", 2, 1), ("tagmata", 1, 2),
    ]
    choice = markers[symbols - 1]
    opponent = CompactInterface(ui.session, player="roman")
    before = gs.to_json()
    assert opponent.actions(type="resolve_event")["entries"] == []
    with pytest.raises(InterfaceError) as rejected:
        opponent.apply({"type": "resolve_event", "card": "S15", "args": choice}, version=opponent.version)
    assert rejected.value.code == "not_your_decision"
    for args, code in [
        ({"source": "unlevied", "unit": "infantry"}, "themata_selection_required"),
        ({**choice, "symbols": 3 - symbols}, "bad_themata_selection"),
        ({**choice, "marker_index": True}, "bad_themata_selection"),
        ({**choice, "thema": "Iberia"}, "bad_themata_selection"),
        ({**choice, "source": "defending"}, "bad_themata_selection"),
    ]:
        with pytest.raises(IllegalAction, match=code):
            ui.apply(action_id, parameters={"args": args})
        assert ui.gs.to_json() == before
    result = _apply_and_replay(ui, tmp_path, "S15", choice)
    assert result["removed"] == choice
    assert [(m.unit, m.symbols) for m in ui.gs.themata[THEMA]] == [
        ("infantry", 3 - symbols), ("tagmata", 1),
    ]
    removed = ui.gs.meta.themata_removed[-1]
    assert (removed.unit, removed.symbols, removed.home_thema) == ("infantry", symbols, THEMA)
    with pytest.raises(InterfaceError) as rejected:
        ui.apply(action_id, parameters={"args": choice})
    assert rejected.value.code == "stale_selection"


def test_s15_selects_a_defending_counter_at_the_invested_stronghold(tmp_path):
    def stage(gs):
        _invest(gs, LOCALE)
        for marker in gs.themata[THEMA][:2]:
            marker.home_thema = THEMA
            gs.locales[LOCALE].themata_defending.append(marker)
        del gs.themata[THEMA][:2]

    ui = CompactInterface(LLMSession(_draw("S15", stage)), player="seljuk")
    _, help_ = _event(ui, "S15")
    [target] = [ref for ref in help_["eligible_markers"]
                if ref["source"] == "defending" and ref["symbols"] == 2]
    assert target["locale"] == LOCALE and target["marker_index"] == 1
    _apply_and_replay(ui, tmp_path, "S15", target)
    assert [(m.unit, m.symbols) for m in ui.gs.locales[LOCALE].themata_defending] == [("infantry", 1)]
    assert [m.unit for m in ui.gs.themata[THEMA]] == ["tagmata"]


@pytest.mark.parametrize("remaining", ["none", "ordinary", "routed", "themata"])
def test_s15_checks_all_remaining_forces_before_disbanding(tmp_path, remaining):
    def stage(gs):
        _invest(gs, LOCALE)
        gs.meta.options["hidden_mats"] = True
        roman = gs.lords[ROMANOS]
        roman.cylinder = LOCALE
        roman.besieged = True
        marker = gs.themata[THEMA].pop(0)
        marker.home_thema = THEMA
        roman.themata_on_mat = [marker]
        roman.assets.coin -= 1
        roman.lost = roman.forces.copy()
        roman.forces = {}
        if remaining in ("ordinary", "routed"):
            roman.lost["infantry"] -= 1
            if remaining == "ordinary":
                roman.forces = {"infantry": 1}
            else:
                roman.routed = {"infantry": 1}
        if remaining == "themata":
            other = gs.themata[THEMA].pop(0)
            other.home_thema = THEMA
            other.strength = other.routed = 1
            roman.themata_on_mat.append(other)

    gs = _draw("S15", stage)
    # A mat Capability from earlier play, without changing the seeded draw.
    gs.roman.draw_deck.remove("R3")
    gs.lords[ROMANOS].capabilities = ["R3"]
    ui = CompactInterface(LLMSession(gs), player="seljuk")
    _, help_ = _event(ui, "S15")
    [target] = [ref for ref in help_["eligible_markers"]
                if ref["source"] == "levied" and ref["symbols"] == 1]
    assert target == {"source": "levied", "thema": THEMA, "locale": LOCALE,
                      "lord": ROMANOS, "marker_index": 0, "unit": "infantry", "symbols": 1}
    mat = ui.session.state("seljuk")["lords"][ROMANOS]
    assert all(mat[field] == "<hidden>" for field in ("themata_on_mat", "forces", "assets", "capabilities"))
    result = _apply_and_replay(ui, tmp_path, "S15", target)
    assert ui.gs.meta.themata_removed[:-1] == gs.meta.themata_removed
    removed = ui.gs.meta.themata_removed[-1]
    assert (removed.unit, removed.symbols, removed.home_thema) == ("infantry", 1, THEMA)
    roman = ui.gs.lords[ROMANOS]
    assert ui.gs.locales[LOCALE].siege_markers == 1
    if remaining == "none":
        assert result["disband"]["disband"] == "at_limit_recyclable"
        assert not roman.mustered and not roman.besieged
        assert roman.cylinder == "calendar" and roman.cylinder_calendar_box == 6
        assert roman.assets == Assets() and roman.service_box is None
        assert not roman.capabilities and not roman.vassals and not roman.themata_on_mat
        assert ui.gs.roman.draw_deck.count("R3") == 1
        for _ in range(2):
            _pass_pay(ui.session)
        assert ui.gs.meta.subphase == "levy.muster"
        assert not ui.gs.lords[ROMANOS].mustered
    else:
        assert "disband" not in result
        assert roman.mustered and roman.besieged and roman.cylinder == LOCALE
        assert roman.assets == gs.lords[ROMANOS].assets and roman.service_box == 5
        assert roman.capabilities == ["R3"]
        assert sum(roman.unrouted_forces().values()) + sum(roman.routed_forces().values()) == 1


def test_s15_lifts_a_siege_if_the_disbanded_commander_was_the_only_besieger():
    def stage(gs):
        _invest(gs, LOCALE)
        stronghold = gs.locales[LOCALE]
        stronghold.conquered_side = "seljuk"
        stronghold.conquered_count = 1
        gs.lords[ALP].besieged = True
        roman = gs.lords[ROMANOS]
        roman.cylinder = LOCALE
        marker = gs.themata[THEMA].pop(0)
        marker.home_thema = THEMA
        roman.themata_on_mat = [marker]
        roman.lost = roman.forces.copy()
        roman.forces = {}

    ui = CompactInterface(LLMSession(_draw("S15", stage)), player="seljuk")
    action_id, help_ = _event(ui, "S15")
    [target] = [ref for ref in help_["eligible_markers"] if ref["source"] == "levied"]
    ui.apply(action_id, parameters={"args": target})
    assert ui.gs.lords[ROMANOS].cylinder == "calendar"
    assert ui.gs.locales[LOCALE].siege_markers == 0
    assert not ui.gs.lords[ALP].besieged
    assert check_invariants(ui.gs) == []
