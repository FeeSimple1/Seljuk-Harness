"""Bug fix: while Nomisma Debased (R19) is in effect (marker placed /
nomisma_debased_used), Non-Commander Roman Lords may not Tax. Commanders
(Romanos Diogenes, Manuel Komnenos) are exempt. Previously the prohibition was
never enforced (menu offered Tax and the handler granted the Coin)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, campaign as C, engine
from seljuk.state import IllegalAction


def _active(gs, lid, loc):
    l = gs.lords[lid]; l.mustered = True; l.cylinder = loc; l.besieged = False
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.active_player = "roman"; gs.meta.active_lord = lid
    gs.meta.active_card = lid; gs.meta.actions_remaining = 4
    gs.roman.command_plan = [lid]; gs.roman.plan_pointer = 1
    return l


def _tax_offered(gs):
    return any(m["type"] == "cmd_tax" for m in C.command_menu(gs))


def test_noncommander_roman_tax_blocked_under_nomisma():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    gs.meta.notes["nomisma_debased_used"] = True
    _active(gs, "roussel_de_bailleul", "ankyra")   # his Seat; not a Commander
    assert _tax_offered(gs) is False
    try:
        engine.apply_action(gs, {"type": "cmd_tax", "lord": "roussel_de_bailleul"})
        assert False, "expected IllegalAction"
    except IllegalAction as e:
        assert "nomisma_debased" in str(e)


def test_commander_exempt_under_nomisma():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    gs.meta.notes["nomisma_debased_used"] = True
    _active(gs, "romanos_diogenes", "to_constantinople")  # Commander
    # place him at his own Seat so Tax would otherwise be offered
    seat = __import__("seljuk.static_data", fromlist=["lord"]).lord("romanos_diogenes")["seats"][0]
    _active(gs, "romanos_diogenes", seat)
    assert _tax_offered(gs) is True


def test_noncommander_tax_allowed_without_nomisma():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    gs.meta.notes["nomisma_debased_used"] = False
    _active(gs, "roussel_de_bailleul", "ankyra")
    assert _tax_offered(gs) is True
