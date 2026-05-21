"""Phase 6: Surprise (S1), Local Scouts (R18), Basil Alousianos (R7)."""
from seljuk import scenarios as S, engine


def _cmd(gs, lord, side):
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"; gs.meta.active_player = side
    gs.meta.active_lord = lord; gs.meta.active_card = lord; gs.meta.actions_remaining = 4
    gs.seljuk.command_plan = ["alp_arslan"]; gs.seljuk.plan_pointer = 1
    gs.roman.command_plan = ["chatatourios"]; gs.roman.plan_pointer = 1


def test_surprise_places_two_siege_and_storms_s1():
    gs = S.load_scenario("emperor_and_the_lion", seed=4)
    aa = gs.lords["alp_arslan"]; aa.cylinder = "tephrike"; aa.forces = {"turkic_horse": 6}  # alone at a Roman fort
    gs.seljuk.held_events = ["S1"]
    _cmd(gs, "alp_arslan", "seljuk")
    gs.meta.pending = [{"type": "besiege_or_bypass", "locale": "tephrike", "lords": ["alp_arslan"]}]
    r = engine.apply_action(gs, {"type": "besiege_bypass", "choice": "besiege", "surprise": True})
    assert r["action"] == "besiege_surprise" and "storm" in r
    assert "S1" not in gs.seljuk.held_events  # consumed


def test_local_scouts_forces_avoider_to_stand_r18():
    gs = S.load_scenario("emperor_and_the_lion", seed=5)
    rom = gs.lords["romanos_diogenes"]; rom.cylinder = "melitene"; rom.forces = {"tagmata": 3, "turkic_horse": 2}
    aa = gs.lords["alp_arslan"]; aa.cylinder = "melitene"; aa.forces = {"militia": 1}; aa.assets.loot = 0; aa.assets.provender = 0
    gs.roman.held_events = ["R18"]
    _cmd(gs, "romanos_diogenes", "roman")
    gs.meta.pending = [{"type": "approach_response", "locale": "melitene",
                        "attackers": ["romanos_diogenes"], "defenders": ["alp_arslan"]}]
    r = engine.apply_action(gs, {"type": "respond_approach",
                                 "choices": {"alp_arslan": {"action": "avoid", "to": "germanikeia"}},
                                 "local_scouts": {"lord": "alp_arslan", "action": "stand"}})
    assert "R18" not in gs.roman.held_events            # consumed
    assert "battle" in r                                 # forced to Stand -> Battle resolved


def test_basil_converts_surrender_to_bypass_r7():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    aa = gs.lords["alp_arslan"]; aa.cylinder = "tephrike"  # Roman fort
    gs.locales["tephrike"].siege_markers = 3  # threshold 3 -> Basil-eligible
    gs.roman.held_events = ["R7"]
    _cmd(gs, "alp_arslan", "seljuk")
    r = engine.apply_action(gs, {"type": "cmd_siege", "lord": "alp_arslan"})
    assert r.get("seized") and r.get("pending") == "basil_response"
    moves = engine.legal_moves(gs)
    assert any(m["type"] == "basil_response" for m in moves)
    engine.apply_action(gs, {"type": "basil_response", "play": True})
    assert gs.locales["tephrike"].bypass and gs.locales["tephrike"].conquered_side is None
    assert "R7" in gs.meta.asterisks_used


def test_basil_decline_conquers_r7():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    aa = gs.lords["alp_arslan"]; aa.cylinder = "tephrike"
    gs.locales["tephrike"].siege_markers = 3
    gs.roman.held_events = ["R7"]
    _cmd(gs, "alp_arslan", "seljuk")
    engine.apply_action(gs, {"type": "cmd_siege", "lord": "alp_arslan"})
    engine.apply_action(gs, {"type": "basil_response", "play": False})
    assert gs.locales["tephrike"].conquered_side == "seljuk"
