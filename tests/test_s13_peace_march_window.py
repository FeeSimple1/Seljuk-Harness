"""Bug fix: while S13 Peace Offering is active, the command menu must not offer a
March that would trigger an Approach (into an enemy-occupied Locale) when the
active Lord cannot pay the required Coin -- the handler rejects it
(peace_offering_coin), so the enumerator and validator disagreed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, campaign as C
from seljuk.state import GameState, IllegalAction
from seljuk import engine


def _setup(gs, coin):
    aa = gs.lords["alp_arslan"]; aa.mustered = True; aa.cylinder = "ani"; aa.assets.coin = coin
    aa.assets.loot = 0; aa.assets.provender = 0
    rom = gs.lords["romanos_diogenes"]; rom.mustered = True; rom.cylinder = "mempet"  # adjacent (road) enemy
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.active_player = "seljuk"; gs.meta.active_lord = "alp_arslan"
    gs.meta.active_card = "alp_arslan"; gs.meta.actions_remaining = 4
    gs.meta.notes["peace_offering_season"] = True       # S13 active this Season
    gs.seljuk.command_plan = ["alp_arslan"]; gs.seljuk.plan_pointer = 1
    return aa


def _march_to_mempet(gs):
    return [m for m in C.command_menu(gs) if m["type"] == "cmd_march" and m["to"] == "mempet"]


def test_approach_march_suppressed_when_coin_unaffordable():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    _setup(gs, coin=0)                                   # no Coin -> cannot pay S13
    assert _march_to_mempet(gs) == []
    # every offered March still round-trips through the handler
    for m in C.command_menu(gs):
        if m["type"] != "cmd_march":
            continue
        snap = GameState.from_json(gs.to_json())
        try:
            engine.apply_action(snap, {k: v for k, v in m.items() if not k.startswith("_")})
        except IllegalAction as e:
            assert "peace_offering_coin" not in str(e)


def test_approach_march_offered_when_coin_affordable():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    _setup(gs, coin=1)                                   # can pay the S13 Coin
    assert _march_to_mempet(gs) != []


def test_approach_march_offered_when_not_peace_season():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    aa = _setup(gs, coin=0)
    gs.meta.notes.pop("peace_offering_season", None)     # S13 not active -> no gate
    assert _march_to_mempet(gs) != []
