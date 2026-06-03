"""4.4.2 + 4.4.1 Important box: a Lord draws one Provender per Stronghold Seat
used in a single Supply action, each Seat funded by its OWN Carts along its Route
(Carts are not shared across Routes), bounded by the Cart budget and the
8-Provender cap (1.7.3). Replaces the old single-Provender-per-action model."""
from seljuk import scenarios as S, campaign, engine
from seljuk.rng import DiceRoller


def _lord(gs):
    l = gs.lords["alp_arslan"]; l.mustered = True; l.side = "seljuk"
    l.cylinder = "ani"; l.assets.provender = 0; l.assets.carts = 0
    return l


def test_plan_draws_one_provender_per_fundable_seat(monkeypatch):
    gs = S.load_scenario("emperor_and_the_lion"); l = _lord(gs)
    # Stands on one Seat (cost 0); two more Seats at 1 and 2 Carts.
    monkeypatch.setattr(campaign, "_supply_route_costs",
                        lambda g, ld: {"ani": 0, "seatB": 1, "seatC": 2})
    monkeypatch.setattr(campaign, "_available_carts", lambda g, ld: 3)
    gain, used, total = campaign._supply_plan(gs, l)
    assert gain == 3 and total == 3 and set(used) == {"ani", "seatB", "seatC"}


def test_plan_capped_by_cart_budget(monkeypatch):
    gs = S.load_scenario("emperor_and_the_lion"); l = _lord(gs)
    monkeypatch.setattr(campaign, "_supply_route_costs",
                        lambda g, ld: {"ani": 0, "seatB": 2, "seatC": 2})
    monkeypatch.setattr(campaign, "_available_carts", lambda g, ld: 2)
    gain, used, total = campaign._supply_plan(gs, l)
    # Free Seat + one 2-Cart Seat; the second 2-Cart Seat is unfunded.
    assert gain == 2 and total == 2 and "ani" in used


def test_plan_capped_by_provender_room(monkeypatch):
    gs = S.load_scenario("emperor_and_the_lion"); l = _lord(gs)
    l.assets.provender = 6                     # only room for 2 more (cap 8)
    monkeypatch.setattr(campaign, "_supply_route_costs",
                        lambda g, ld: {"ani": 0, "seatB": 1, "seatC": 1, "seatD": 1})
    monkeypatch.setattr(campaign, "_available_carts", lambda g, ld: 9)
    gain, used, _ = campaign._supply_plan(gs, l)
    assert gain == 2


def test_plan_at_most_one_marwanid_seat(monkeypatch):
    gs = S.load_scenario("year_of_treacherous_ambition"); l = _lord(gs)
    gs.meta.notes["marwanid_seats"] = ["amid", "mayyafariqin"]
    monkeypatch.setattr(campaign, "_supply_route_costs",
                        lambda g, ld: {"amid": 0, "mayyafariqin": 1, "ani": 1})
    monkeypatch.setattr(campaign, "_available_carts", lambda g, ld: 5)
    gain, used, _ = campaign._supply_plan(gs, l)
    # Only one of the two Marwanid Locales may be a Source this card (3.5.1.1).
    assert len([s for s in used if s in campaign._MARWANID_LOCALES]) == 1


def test_handler_grants_planned_provender(monkeypatch):
    gs = S.load_scenario("emperor_and_the_lion"); l = _lord(gs)
    gs.meta.phase = "campaign"; gs.meta.active_lord = "alp_arslan"; gs.meta.actions_remaining = 2
    monkeypatch.setattr(campaign, "_supply_route_costs",
                        lambda g, ld: {"ani": 0, "seatB": 1})
    monkeypatch.setattr(campaign, "_available_carts", lambda g, ld: 4)
    r = campaign.h_cmd_supply(gs, {"lord": "alp_arslan"}, DiceRoller(1))
    assert r["provender_gained"] == 2 and l.assets.provender == 2


def test_handler_single_seat_still_draws_one():
    gs = S.load_scenario("emperor_and_the_lion"); l = _lord(gs)
    l.assets.carts = 0                       # at Ani (a Seat): no Carts needed
    gs.meta.phase = "campaign"; gs.meta.active_lord = "alp_arslan"; gs.meta.actions_remaining = 2
    r = campaign.h_cmd_supply(gs, {"lord": "alp_arslan"}, DiceRoller(1))
    assert l.assets.provender == 1 and r["seat"] == "ani"
