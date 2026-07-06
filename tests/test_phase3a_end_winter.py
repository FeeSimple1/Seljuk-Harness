"""Phase 3a: End Campaign (4.7) and Winter (4.7.6)."""
from seljuk import scenarios as S, campaign, engine


def test_grow_halves_enemy_ravaged_in_spring_472():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.meta.calendar_box = 4  # Spring
    for lid in ("larisa", "tephrike", "keltzene", "chaldia"):
        gs.locales[lid].ravaged_side = "seljuk"  # 4 Seljuk Ravaged
    campaign._grow(gs)
    remaining = sum(1 for l in gs.locales.values() if l.ravaged_side == "seljuk")
    assert remaining == 2  # reduced to ceil(4/2)=2 (Roman removed floor(4/2)=2)


def test_grow_noop_outside_spring():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.meta.calendar_box = 5  # Summer
    gs.locales["larisa"].ravaged_side = "seljuk"
    gs.locales["tephrike"].ravaged_side = "seljuk"
    campaign._grow(gs)
    assert sum(1 for l in gs.locales.values() if l.ravaged_side == "seljuk") == 2


def test_repair_removes_one_siege_from_three_or_four_473():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.locales["azaz"].siege_markers = 4
    gs.locales["manbij"].siege_markers = 2
    campaign._repair(gs)
    assert gs.locales["azaz"].siege_markers == 3
    assert gs.locales["manbij"].siege_markers == 2  # unchanged (<3)


def test_wastage_discards_one_excess_asset_474():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]
    aa.assets.carts = 3
    aa.assets.coin = 1
    campaign._wastage(gs)
    assert aa.assets.carts == 2  # one excess Cart discarded


def test_seljuk_unity_penalty_removes_loot_then_places_roman_markers_476():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.meta.calendar_box = 3
    gs.meta.seljuk_unity_targets = {"3": 10}
    # current Seljuk-marked Locales: Kaisareia Ruins + Hama Conquered = 2 -> deficit 8
    gs.holding_boxes.mosul_baghdad_loot = 3
    campaign._seljuk_unity(gs)
    assert gs.holding_boxes.mosul_baghdad_loot == 0           # 3 loot removed first
    assert gs.holding_boxes.constantinople_roman_vp_markers == 5  # remaining 5 -> Roman markers


def test_bounty_scores_loot_up_to_carts_476():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]  # at Ani (a Seat)
    aa.assets.loot = 3
    aa.assets.carts = 2
    campaign._bounty(gs)
    assert gs.holding_boxes.mosul_baghdad_loot == 2  # min(loot 3, carts 2)
    assert aa.assets.loot == 1


def test_winter_quarters_returns_to_seat_unladen_and_halves_carts_476():
    gs = S.load_scenario("emperor_and_the_lion")
    aa = gs.lords["alp_arslan"]
    aa.cylinder = "larisa"  # away from Seat
    aa.assets.loot = 2
    aa.assets.carts = 3
    campaign._begin_winter_quarters(gs)  # Alp has TWO free Seats -> owner chooses (4.7.6)
    p = next(p for p in gs.meta.pending if p["type"] == "winter_quarters" and p["lord"] == "alp_arslan")
    assert set(p["dests"]) == {"ani", "to_mosul_and_baghdad"}
    engine.apply_action(gs, {"type": "winter_quarters", "lord": "alp_arslan", "dest": "ani"})
    assert aa.cylinder in S.sd.lord("alp_arslan")["seats"]
    assert aa.assets.loot == 0          # Unladen
    assert aa.assets.carts == 2          # halve 3 -> 2 (round up)


def test_end_campaign_advances_turn_when_not_final():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.meta.calendar_box = 1  # Spring 1068, not final, not a Winter box
    campaign._end_campaign(gs)
    assert gs.meta.calendar_box == 2
    assert gs.meta.phase == "levy"


def test_end_campaign_final_turn_is_game_over():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.meta.calendar_box = 12  # Autumn 1071 (final)
    campaign._end_campaign(gs)
    assert gs.meta.phase == "game_over"
    assert gs.meta.notes["winner"] in ("roman", "seljuk", "draw")


def test_winter_box_conducts_winter_then_game_end_for_specter():
    gs = S.load_scenario("specter_of_norman_betrayal")
    gs.meta.calendar_box = 6  # Autumn 1069 = Winter box AND final turn
    campaign._end_campaign(gs)
    while any(p["type"] == "winter_quarters" for p in gs.meta.pending):   # settle 4.7.6 choices
        p = next(p for p in gs.meta.pending if p["type"] == "winter_quarters")
        engine.apply_action(gs, {"type": "winter_quarters", "lord": p["lord"], "dest": p["dests"][0]})
    assert gs.meta.phase == "game_over"


def test_aleppo_independence_auto_victory_476():
    gs = S.load_scenario("manzikert")
    gs.meta.calendar_box = 9  # any Winter box
    gs.meta.aleppo_independence_played = True
    gs.locales["aleppo"].conquered_side = "seljuk"
    winner = campaign._winter(gs)
    assert winner == "seljuk"


def test_no_mustered_lords_loses_immediately_52():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    campaign.start_campaign(gs)
    # build minimal plans
    from seljuk import engine
    sp = campaign.plan_size(gs)  # 7 (Spring); max 5 No Command -> pad with a 2nd lord card
    engine.apply_action(gs, {"type": "build_plan", "side": "seljuk", "cards": ["alp_arslan", "alp_arslan"] + ["no_command"] * (sp - 2)})
    engine.apply_action(gs, {"type": "build_plan", "side": "roman", "cards": ["romanos_diogenes", "romanos_diogenes"] + ["no_command"] * (sp - 2)})
    # wipe all Seljuk Mustered Lords, then end Alp Arslan's card
    for l in gs.lords.values():
        if l.side == "seljuk":
            l.mustered = False
    engine.apply_action(gs, {"type": "end_activation"})
    assert gs.meta.phase == "game_over" and gs.meta.notes["winner"] == "roman"
