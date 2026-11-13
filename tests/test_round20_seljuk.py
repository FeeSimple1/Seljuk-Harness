"""Round 20 regressions through Seljuk's player action interface."""
from itertools import combinations

import pytest

from seljuk import engine, scenarios
from seljuk.invariants import check_invariants
from seljuk.llm.compact import CompactInterface
from seljuk.llm.session import LLMSession
from seljuk.state import IllegalAction

ALP = "alp_arslan"
ROMANOS = "romanos_diogenes"
DOUKAS = "andronikos_doukas"
RAVAGED = ("ankyra", "amaseia", "sebasteia")
EVENT_SEEDS = {"R5": 119, "S12": 254, "S23": 139, "R19": 42}


def _event_state(card):
    # Stage the second Levy of the audited scenario. The engine draws
    # the actual Event from the seeded deck.
    gs = scenarios.load_scenario("emperor_and_the_lion", seed=EVENT_SEEDS[card])
    gs.meta.calendar_box = 2
    gs.meta.notes["first_aow_done"] = True
    engine.start_levy(gs)
    assert [p["card"] for p in gs.meta.pending] == [card]
    return gs


def _rows(ui, kind, **fields):
    return [row for row in ui.actions(type=kind, limit=100)["entries"]
            if all(row["action"].get(key) == value for key, value in fields.items())]


def _row(ui, kind, **fields):
    [row] = _rows(ui, kind, **fields)
    return row


@pytest.mark.parametrize("card,wrong,legal,cylinder", [
    ("R5", ROMANOS, ALP, "afsin_beg"),
    ("S12", ALP, ROMANOS, "manuel_komnenos"),
    ("S23", ALP, ROMANOS, None),
])
def test_calendar_event_target_eligibility(card, wrong, legal, cylinder):
    gs = _event_state(card)
    ui = CompactInterface(LLMSession(gs))
    row = _row(ui, "resolve_event", card=card)
    help_ = ui.details(row["id"])["help"]
    assert help_["eligible_markers"][legal] == ["service"]
    assert wrong not in help_["eligible_markers"]
    assert help_["directions"] == ["left", "right"]
    before = gs.to_json()
    with pytest.raises(IllegalAction, match="bad_event_target"):
        ui.apply(row["id"], parameters={"args": {"lord": wrong, "what": "service"}})
    assert ui.gs.to_json() == before
    if card == "S23":
        with pytest.raises(IllegalAction, match="bad_what"):
            ui.apply(row["id"], parameters={"args": {"lord": legal, "what": "cylinder"}})
        assert ui.gs.to_json() == before

    ui.apply(row["id"], parameters={"args": {"lord": legal, "what": "service", "direction": "right"}})
    assert ui.gs.lords[legal].service_box == gs.lords[legal].service_box + 1
    assert ui.gs.side_decks("roman" if card == "R5" else "seljuk").draw_deck.count(card) == 1
    if cylinder:
        assert help_["eligible_markers"][cylinder] == ["cylinder"]
        branch = CompactInterface(LLMSession(gs))
        branch.apply(_row(branch, "resolve_event")["id"],
                     parameters={"args": {"lord": cylinder, "what": "cylinder", "direction": "left"}})
        assert branch.gs.lords[cylinder].cylinder_calendar_box == gs.lords[cylinder].cylinder_calendar_box - 1


def test_fatimid_conflict_rejects_besieged_service():
    gs = _event_state("R5")
    gs.lords[ROMANOS].cylinder = "ani"
    gs.lords[ALP].besieged = True
    gs.locales["ani"].siege_markers = 1
    ui = CompactInterface(LLMSession(gs), player="roman")
    row = _row(ui, "resolve_event")
    assert ALP not in ui.details(row["id"])["help"]["eligible_markers"]
    before = gs.to_json()
    with pytest.raises(IllegalAction, match="Unbesieged Seljuk Lord"):
        ui.apply(row["id"], parameters={"args": {"lord": ALP, "what": "service", "direction": "left"}})
    assert ui.gs.to_json() == before


@pytest.mark.parametrize("selected", list(combinations(RAVAGED, 2)))
def test_resilient_agriculture_offers_every_pair(selected):
    gs = _event_state("R19")
    for loc in (*RAVAGED, "hama"):
        gs.locales[loc].ravaged_side = "seljuk"
    ui = CompactInterface(LLMSession(gs), player="roman")
    row = _row(ui, "resolve_event")
    help_ = ui.details(row["id"])["help"]
    assert set(help_["eligible_locales"]) == set(RAVAGED)
    assert help_["required_count"] == 2
    before = gs.to_json()
    for invalid in ([], ["ankyra"], ["ankyra", "ankyra"], ["ankyra", "hama"], list(RAVAGED)):
        with pytest.raises(IllegalAction, match="bad_ravaged_selection"):
            ui.apply(row["id"], parameters={"args": {"locales": invalid}})
        assert ui.gs.to_json() == before
    ui.apply(row["id"], parameters={"args": {"locales": list(selected)}})
    assert {loc for loc in (*RAVAGED, "hama") if ui.gs.locales[loc].ravaged_side is None} == set(selected)
    assert ui.gs.history[-1]["result"]["cleared_locales"] == list(selected)
    assert ui.gs.meta.vp == scenarios.score(ui.gs)


@pytest.mark.parametrize("eligible", [[], ["sebasteia"]])
def test_resilient_agriculture_clears_as_many_as_possible(eligible):
    gs = _event_state("R19")
    gs.locales["hama"].ravaged_side = "seljuk"
    gs.locales["ankyra"].ravaged_side = "roman"
    for loc in eligible:
        gs.locales[loc].ravaged_side = "seljuk"
    ui = CompactInterface(LLMSession(gs))
    row = _row(ui, "resolve_event")
    assert ui.details(row["id"])["help"]["required_count"] == len(eligible)
    if eligible:
        with pytest.raises(IllegalAction, match="bad_ravaged_selection"):
            ui.apply(row["id"], parameters={"args": {}})
    ui.apply(row["id"], parameters={"args": {"locales": eligible} if eligible else {}})
    assert all(ui.gs.locales[loc].ravaged_side is None for loc in eligible)
    assert ui.gs.locales["hama"].ravaged_side == "seljuk"
    assert ui.gs.locales["ankyra"].ravaged_side == "roman"
    assert not ui.gs.meta.pending


def test_native_manzikert_pay_reaches_calendar_edge(tmp_path):
    ui = CompactInterface(LLMSession.start_new("manzikert", seed=1))
    for _ in range(2):
        ui.apply(_row(ui, "build_plan")["id"], parameters={"cards": ["no_command"] * 4})
    ui.apply(_row(ui, "fpd_done")["id"])
    path = tmp_path / "manzikert-pay.json"
    ui.session.save(path)
    outcomes = []
    for session in (ui.session, LLMSession.load(path)):
        roman = CompactInterface(session, player="roman")
        lord = roman.gs.lords[ROMANOS]
        assert (lord.service_box, lord.assets.coin) == (12, 2)
        row = _row(roman, "pay", payer=ROMANOS, target=ROMANOS, asset="coin")
        assert row["hints"]["_max"] == 1
        before = roman.gs.to_json()
        with pytest.raises(IllegalAction, match="pay_exceeds_service_limit"):
            roman.apply({**row["action"], "amount": 2}, version=roman.version)
        assert roman.gs.to_json() == before
        roman.apply(row["id"])
        assert (roman.gs.lords[ROMANOS].service_box, roman.gs.lords[ROMANOS].assets.coin) == (13, 1)
        assert not _rows(roman, "pay", payer=ROMANOS, target=ROMANOS)
        before = roman.gs.to_json()
        with pytest.raises(IllegalAction, match="pay_exceeds_service_limit"):
            engine.apply_action(roman.gs, row["action"])
        assert roman.gs.to_json() == before
        roman.apply(_row(roman, "pay", payer=ROMANOS, target=DOUKAS, asset="coin")["id"])
        assert roman.gs.lords[DOUKAS].service_box == 12
        assert roman.gs.lords[ROMANOS].assets.coin == 0
        assert not check_invariants(roman.gs)
        outcomes.append(roman.gs.to_json())
    assert outcomes[0] == outcomes[1]


@pytest.mark.parametrize("phase,step", [("levy", "levy.pay"), ("campaign", "campaign.fpd_pay")])
@pytest.mark.parametrize("asset", ["coin", "loot"])
def test_pay_can_advance_vassals_after_lord_reaches_edge(phase, step, asset):
    gs = scenarios.load_scenario("emperor_and_the_lion", options={"vassal_service": True})
    gs.meta.phase, gs.meta.subphase, gs.meta.active_player = phase, step, "seljuk"
    lord = gs.lords[ALP]
    lord.service_box = 13
    setattr(lord.assets, asset, 3)
    for box, vassal in zip((11, 12), lord.vassals):
        vassal.levied = True
        vassal.service_box = box
    ui = CompactInterface(LLMSession(gs))
    row = _row(ui, "pay", payer=ALP, target=ALP, asset=asset)
    assert ui.details(row["id"])["help"]["max_amount"] == 2
    before = ui.gs.to_json()
    with pytest.raises(IllegalAction, match="pay_exceeds_service_limit"):
        ui.apply({**row["action"], "amount": 3}, version=ui.version)
    assert ui.gs.to_json() == before
    ui.apply({**row["action"], "amount": 2}, version=ui.version)
    lord = ui.gs.lords[ALP]
    assert lord.service_box == 13
    assert [v.service_box for v in lord.vassals[:2]] == [13, 13]
    assert getattr(lord.assets, asset) == 1
    assert not _rows(ui, "pay", payer=ALP, target=ALP, asset=asset)
