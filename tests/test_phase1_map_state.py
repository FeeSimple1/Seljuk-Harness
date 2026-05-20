"""Phase 1 map helpers and state model (Rules 1.3.1)."""
from seljuk import map as gmap, scenarios as S
from seljuk.state import Assets, GameState, LordState, Meta


def test_adjacency_is_symmetric():
    for lid in gmap.sd.all_locale_ids():
        for nb in gmap.neighbors(lid):
            assert lid in gmap.neighbors(nb)


def test_adjacent_to_pass_examples():
    # Khliat<->Anzitene is a Pass (D-001), so both are pass-adjacent.
    assert gmap.adjacent_to_pass("khliat")
    assert gmap.adjacent_to_pass("anzitene")
    # Antioch's Ways (Laodikeia, Artah, Mopsuestia) are all Roads.
    assert not gmap.adjacent_to_pass("antioch")


def test_whole_command_routes_touch_holding_boxes():
    wc = [w for w in gmap.sd.ways() if w["whole_command_card"]]
    for w in wc:
        assert "to_constantinople" in (w["a"], w["b"]) or "to_mosul_and_baghdad" in (w["a"], w["b"])


def test_state_round_trip_preserves_lord():
    gs = GameState(meta=Meta(scenario="t"))
    gs.lords["x"] = LordState(id="x", side="seljuk", mustered=True, cylinder="ani",
                              forces={"turkic_horse": 5}, assets=Assets(coin=2))
    gs2 = GameState.from_json(gs.to_json())
    assert gs2.lords["x"].forces["turkic_horse"] == 5
    assert gs2.lords["x"].assets.coin == 2


def test_extra_fields_are_rejected():
    """The model is strict (extra='forbid') to catch typos early."""
    import pydantic
    import pytest
    with pytest.raises(pydantic.ValidationError):
        Assets(carts=1, bogus=2)
