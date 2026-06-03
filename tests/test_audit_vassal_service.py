"""Optional Rule 6.2 Vassal Service: track Vassal Service on the Calendar.
Off by default; when on, a Mustering Vassal's marker is placed by its Service
Rating, shifts with its Lord's marker, Disbands at its Service limit (returning
Forces to the pool), and is Unready until after the ensuing Muster."""
import pytest
from seljuk import scenarios as S, actions
from seljuk.state import shift_vassal_service, IllegalAction
from seljuk.rng import DiceRoller


def _ready_lord(gs, lid="alp_arslan"):
    l = gs.lords[lid]; l.mustered = True; l.side = "seljuk"
    l.cylinder = "ani"; l.flags["mustered_this_segment"] = False
    gs.meta.subphase = "levy.muster"; gs.meta.active_player = l.side
    return l


def _first_vassal_idx(l):
    return next(i for i, v in enumerate(l.vassals) if not v.levied and not v.requires_capability)


def test_levy_vassal_places_service_marker_by_rating():
    gs = S.load_scenario("emperor_and_the_lion", options={"vassal_service": True})
    gs.meta.calendar_box = 4
    l = _ready_lord(gs)
    i = _first_vassal_idx(l)
    rating = l.vassals[i].service
    actions.h_levy_vassal(gs, {"lord": l.id, "vassal_index": i}, DiceRoller(1))
    assert l.vassals[i].service_box == 4 + int(rating)


def test_default_off_places_no_marker():
    gs = S.load_scenario("emperor_and_the_lion")          # standard rules
    l = _ready_lord(gs)
    i = _first_vassal_idx(l)
    actions.h_levy_vassal(gs, {"lord": l.id, "vassal_index": i}, DiceRoller(1))
    assert l.vassals[i].service_box is None


def test_vassal_marker_shifts_with_lord():
    gs = S.load_scenario("emperor_and_the_lion", options={"vassal_service": True})
    l = _ready_lord(gs)
    i = _first_vassal_idx(l)
    actions.h_levy_vassal(gs, {"lord": l.id, "vassal_index": i}, DiceRoller(1))
    before = l.vassals[i].service_box
    shift_vassal_service(gs, l, 2)
    assert l.vassals[i].service_box == before + 2


def test_unready_vassal_may_not_muster():
    gs = S.load_scenario("emperor_and_the_lion", options={"vassal_service": True})
    l = _ready_lord(gs)
    i = _first_vassal_idx(l)
    l.vassals[i].unready = True
    with pytest.raises(IllegalAction):
        actions.h_levy_vassal(gs, {"lord": l.id, "vassal_index": i}, DiceRoller(1))


def test_reset_muster_segment_flips_unready_up():
    gs = S.load_scenario("emperor_and_the_lion", options={"vassal_service": True})
    l = _ready_lord(gs)
    l.vassals[0].unready = True
    actions.reset_muster_segment(gs)
    assert l.vassals[0].unready is False


def test_expired_vassal_disbands_and_returns_forces():
    gs = S.load_scenario("emperor_and_the_lion", options={"vassal_service": True})
    gs.meta.calendar_box = 5
    l = _ready_lord(gs)
    i = _first_vassal_idx(l)
    actions.h_levy_vassal(gs, {"lord": l.id, "vassal_index": i}, DiceRoller(1))
    v = l.vassals[i]
    added = dict(v.forces)
    before = {u: l.forces.get(u, 0) for u in added}
    v.service_box = gs.meta.calendar_box        # at its Service limit
    out = actions._disband_expired_vassals(gs, "seljuk")
    assert out and v.levied is False and v.unready is True and v.service_box is None
    for u, n in added.items():
        assert l.forces.get(u, 0) == before[u] - n   # Forces returned to the pool
