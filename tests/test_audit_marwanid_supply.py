"""Audit tidy: 3.5.1.1 -- only one Marwanid Seat may be a Supply Source per
Command card (when both Amid and Mayyafariqin are activated)."""
from seljuk import scenarios as S, campaign


def test_marwanid_one_supply_source_per_card():
    gs = S.load_scenario("year_of_treacherous_ambition")
    gs.meta.notes["marwanid_seats"] = ["amid", "mayyafariqin"]
    ab = gs.lords["afsin_beg"]; ab.mustered = True; ab.cylinder = "mayyafariqin"
    # No lock yet: Mayyafariqin is itself a Seat -> cost 0.
    assert campaign._min_supply_route(gs, ab) == (0, "mayyafariqin")
    # Once a card has used Amid as its Marwanid Supply Source, Mayyafariqin is
    # not available as a Supply Source for the rest of that card.
    gs.meta.notes["marwanid_supply_lock"] = "amid"
    cost, seat = campaign._min_supply_route(gs, ab)
    assert seat != "mayyafariqin"
