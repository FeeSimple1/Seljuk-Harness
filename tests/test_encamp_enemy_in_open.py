"""Bug fix: a bypassing Lord must not be able to Encamp (convert Bypass -> Siege)
while an enemy Lord stands in the open at the Locale -- that left opposing
in-the-open Lords co-located (invariant violation). The menu must not offer it
and the handler must reject it."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, campaign as C, engine
from seljuk.state import IllegalAction
from seljuk.invariants import check_invariants

LOC = "laodikeia"


def _setup(gs):
    sj = gs.lords["alp_arslan"]; sj.side = "seljuk"; sj.mustered = True
    sj.cylinder = LOC; sj.bypassed = True; sj.besieged = False
    gs.locales[LOC].bypass = True; gs.locales[LOC].siege_markers = 0
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.active_player = "seljuk"; gs.meta.active_lord = "alp_arslan"
    gs.meta.active_card = "alp_arslan"; gs.meta.actions_remaining = 4
    return sj


def _put_enemy_in_open(gs):
    rom = gs.lords["romanos_diogenes"]; rom.side = "roman"; rom.mustered = True
    rom.cylinder = LOC; rom.bypassed = False; rom.besieged = False


def test_encamp_not_offered_with_enemy_in_open():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    _setup(gs); _put_enemy_in_open(gs)
    assert [m for m in C.command_menu(gs) if m["type"] == "cmd_encamp"] == []


def test_encamp_handler_rejects_with_enemy_in_open():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    _setup(gs); _put_enemy_in_open(gs)
    try:
        engine.apply_action(gs, {"type": "cmd_encamp", "lord": "alp_arslan"})
        assert False, "expected IllegalAction"
    except IllegalAction as e:
        assert "enemy_in_open" in str(e)
    assert check_invariants(gs) == []


def test_encamp_still_offered_and_legal_without_enemy_in_open():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    _setup(gs)  # no enemy present
    assert [m for m in C.command_menu(gs) if m["type"] == "cmd_encamp"]
    engine.apply_action(gs, {"type": "cmd_encamp", "lord": "alp_arslan"})
    assert gs.locales[LOC].siege_markers == 1 and gs.locales[LOC].bypass is False
    assert check_invariants(gs) == []
