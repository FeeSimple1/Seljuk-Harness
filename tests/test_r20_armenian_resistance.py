"""R20 returns any Strategic Objective and gives Seljuks the investment choice."""
import pytest

from seljuk import engine, scenarios as S, events as E
from seljuk.invariants import check_invariants
from seljuk.llm.compact import CompactInterface, InterfaceError
from seljuk.llm.session import LLMSession
from seljuk.rng import DiceRoller
from seljuk.state import IllegalAction

LOC = "khliat"


def _gs():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    gs.locales[LOC].conquered_side = "seljuk"   # ensure Seljuk-friendly
    return gs


def _r():
    return DiceRoller(seed=1)


def test_conquers_roman():
    gs = _gs()
    r = E._ev_armenian_resistance(gs, {"locale": LOC}, _r())
    assert r["roman_conquered"] == LOC and gs.locales[LOC].conquered_side == "roman"


def test_strategic_objective_returns_to_available():
    gs = _gs()
    gs.locales[LOC].strategic_objective = True
    gs.holding_boxes.constantinople_strategic_objectives_available = 0
    r = E._ev_armenian_resistance(gs, {"locale": LOC}, _r())
    assert r.get("strategic_objective_returned") is True
    assert gs.locales[LOC].strategic_objective is False
    assert gs.holding_boxes.constantinople_strategic_objectives_available == 1


@pytest.mark.parametrize("choice", ["besiege", "bypass"])
def test_seljuk_investment_precedes_the_next_event(choice, tmp_path):
    gs = S.load_scenario("emperor_and_the_lion", seed=80)
    gs.meta.calendar_box = 2
    gs.meta.notes["first_aow_done"] = True
    gs.lords["alp_arslan"].cylinder = LOC
    engine.start_levy(gs)
    # R20 and R5 are drawn in that order by the real second-Levy shuffle.
    assert [p["card"] for p in gs.meta.pending] == ["R20", "R5"]
    roman = CompactInterface(LLMSession(gs), player="roman")
    [row] = roman.actions(type="resolve_event")["entries"]
    assert row["action"]["card"] == "R20"
    help_ = roman.details(row["id"])["help"]
    assert help_["argument_names"] == ["locale"] and LOC in help_["eligible_locales"]
    before = roman.gs.to_json()
    version = roman.version
    with pytest.raises(IllegalAction, match="Seljuk player chooses"):
        roman.apply(row["id"], parameters={"args": {"locale": LOC, "invest": "siege"}})
    assert roman.gs.to_json() == before and roman.version == version

    roman.apply(row["id"], parameters={"args": {"locale": LOC}})
    assert roman.gs.locales[LOC].conquered_side == "roman"
    assert roman.gs.locales[LOC].siege_markers == 0
    assert not roman.gs.locales[LOC].bypass
    assert roman.gs.roman.draw_deck.count("R20") == 1
    assert roman.owed == "seljuk" and not roman.actions()["entries"]
    action = {"type": "besiege_bypass", "choice": choice}
    with pytest.raises(InterfaceError, match="Decision belongs to seljuk"):
        roman.apply(action, version=roman.version)
    before = roman.gs.to_json()
    with pytest.raises(IllegalAction, match="pending_decision"):
        engine.apply_action(roman.gs, {"type": "pass_step"})
    with pytest.raises(IllegalAction, match="pending_decision"):
        engine.apply_action(roman.gs, {"type": "resolve_event", "card": "R5", "args": {}})
    with pytest.raises(IllegalAction, match="wrong_actor"):
        engine.apply_action(roman.gs, {**action, "side": "roman"})
    assert roman.gs.to_json() == before

    path = tmp_path / "r20.json"
    roman.session.save(path)
    restored = LLMSession.load(path)
    outcomes = []
    for session in (roman.session, restored):
        seljuk = CompactInterface(session, player="seljuk")
        rows = seljuk.actions()["entries"]
        assert [(r["action"]["type"], r["action"]["choice"]) for r in rows] == [
            ("besiege_bypass", "besiege"), ("besiege_bypass", "bypass"),
        ]
        seljuk.apply(next(r["id"] for r in rows if r["action"]["choice"] == choice))
        assert seljuk.owed == "roman"
        assert seljuk.gs.meta.subphase == "levy.pay"
        assert [p["card"] for p in seljuk.gs.meta.pending] == ["R5"]
        assert seljuk.gs.locales[LOC].siege_markers == int(choice == "besiege")
        assert seljuk.gs.locales[LOC].bypass is (choice == "bypass")
        assert seljuk.gs.lords["alp_arslan"].bypassed is (choice == "bypass")
        assert not check_invariants(seljuk.gs)
        outcomes.append(seljuk.gs.to_json())
    assert outcomes[0] == outcomes[1]
