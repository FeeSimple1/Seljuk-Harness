"""Phase 5a: LLM interface — hidden-info view, briefing, session, lookups."""
from seljuk.llm import LLMSession
from seljuk.llm import view


def test_start_new_begins_phase():
    s = LLMSession.start_new("emperor_and_the_lion", seed=1)
    assert s.gs.meta.subphase is not None  # Levy step machine started


def test_hidden_info_masks_opponent_deck_and_hand():
    s = LLMSession.start_new("emperor_and_the_lion", seed=1)
    st = s.state("seljuk")
    assert set(st["roman"]["draw_deck"]) == {"<hidden>"}      # opponent deck hidden
    assert "<hidden>" not in st["seljuk"]["draw_deck"]         # own deck visible
    assert all(c == "<hidden>" for c in st["roman"]["held_events"])


def test_revealed_plan_cards_visible_unrevealed_hidden():
    s = LLMSession.start_new("year_of_treacherous_ambition", seed=1)  # starts in Campaign
    s.gs.roman.command_plan = ["chatatourios", "roussel_de_bailleul", "no_command"]
    s.gs.roman.plan_pointer = 1  # first card revealed
    st = s.state("seljuk")
    assert st["roman"]["command_plan"][0] == "chatatourios"     # revealed -> visible
    assert st["roman"]["command_plan"][1] == "<hidden>"          # unrevealed -> hidden


def test_briefing_includes_scenario_and_vp():
    s = LLMSession.start_new("specter_of_norman_betrayal", seed=1)
    b = s.briefing()
    assert "specter_of_norman_betrayal" in b and "VP" in b


def test_legal_actions_and_apply_route_through_engine():
    s = LLMSession.start_new("emperor_and_the_lion", seed=1)
    moves = s.legal_actions()
    assert moves
    s.apply({"type": "pass_step"})
    assert s.gs.meta.active_player == "roman"


def test_lookups():
    s = LLMSession.start_new("emperor_and_the_lion", seed=1)
    assert s.lookup_card("S8")["capability"]["name"] == "Marwanid Alliance"
    assert s.lookup_lord("alp_arslan")["ratings"]["command"] == 4


def test_save_load_round_trip(tmp_path):
    s = LLMSession.start_new("manzikert", seed=3)
    p = tmp_path / "g.json"
    s.save(str(p))
    s2 = LLMSession.load(str(p))
    assert s2.gs.meta.scenario == "manzikert"
    assert s2.gs.meta.calendar_box == s.gs.meta.calendar_box
