"""Bug fix: a This-Lord Capability card must return to the deck of its PRINTED
side, not the Lord's current allegiance. Otherwise a Loyalty-Check side switch
(1.4.2) or Wastage (4.7.4) of a Lord who changed sides migrates e.g. a Seljuk
S15 into the Roman Arts-of-War deck, where it later appears as a Roman draw."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, actions, campaign as C, events as E


def _gs():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    gs.seljuk.draw_deck.clear(); gs.roman.draw_deck.clear()   # isolate routing
    return gs


def test_loyalty_switch_routes_capability_by_printed_side():
    gs = _gs()
    aa = gs.lords["alp_arslan"]; aa.side = "seljuk"; aa.mustered = True
    aa.capabilities = ["S15"]                          # Seljuk-printed Capability
    actions._switch_side(gs, aa)                       # fails Loyalty -> now Roman
    assert aa.side == "roman"
    assert gs.seljuk.draw_deck == ["S15"]              # returned to the SELJUK deck
    assert "S15" not in gs.roman.draw_deck


def test_campaign_wastage_routes_capability_by_printed_side():
    gs = _gs()
    l = gs.lords["alp_arslan"]; l.side = "roman"       # a switched Lord, now Roman
    l.capabilities = ["S4", "S15"]                     # both Seljuk-printed
    l.assets.carts = 1; l.assets.provender = 1; l.assets.coin = 1; l.assets.loot = 1
    assert C._do_one_wastage(gs, l) is True
    assert gs.seljuk.draw_deck == ["S15"]              # popped (last) Capability -> Seljuk deck
    assert gs.roman.draw_deck == []


def test_event_wastage_routes_capability_by_printed_side():
    gs = _gs()
    l = gs.lords["alp_arslan"]; l.side = "roman"
    l.capabilities = ["S4", "S15"]
    l.assets.carts = 1; l.assets.provender = 1; l.assets.coin = 1; l.assets.loot = 1
    assert E._wastage_once(gs, l) is True
    assert gs.seljuk.draw_deck == ["S15"]
    assert gs.roman.draw_deck == []
