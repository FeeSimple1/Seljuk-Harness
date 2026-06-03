"""Regression tests for the third-pass fixes: scenario special VP, the
Year-objective march latch, and the Artukid Legacy Mayyafariqin seat."""
import pytest

from seljuk import scenarios as S
from seljuk import campaign
from seljuk import engine
from seljuk.rng import DiceRoller


def _r():
    return DiceRoller(seed=1)


# --- Manzikert: 1 VP per permanently Disbanded enemy Lord --------------------

def test_manzikert_play_disband_scores_but_setup_removed_does_not():
    gs = S.load_scenario("manzikert")
    base = S.score(gs)  # setup-removed lords already excluded
    # A Roman Lord permanently Disbanded DURING play -> Seljuk scores +1.
    rl = next(lid for lid, l in gs.lords.items()
              if l.side == "roman" and l.cylinder != "removed")
    gs.lords[rl].cylinder = "removed"  # no setup_removed flag
    assert S.score(gs)["seljuk"] == base["seljuk"] + 1.0
    # A Seljuk Lord permanently Disbanded -> Roman scores +1.
    sl = next(lid for lid, l in gs.lords.items()
              if l.side == "seljuk" and l.cylinder != "removed")
    gs.lords[sl].cylinder = "removed"
    assert S.score(gs)["roman"] == base["roman"] + 1.0


def test_manzikert_setup_removed_lords_excluded():
    gs = S.load_scenario("manzikert")
    # Any setup-removed lords carry the flag and must NOT add VP.
    assert S.score(gs) == {"roman": 1.0, "seljuk": 3.5}  # matches starting_vp


# --- Year: Arisighi switch, reached objectives, end-of-Winter control --------

def test_year_arisighi_switch_scores_roman():
    gs = S.load_scenario("year_of_treacherous_ambition")
    base = S.score(gs)
    gs.lords["arisighi"].side = "roman"
    assert S.score(gs)["roman"] == base["roman"] + 1.0


def test_year_reached_objectives_score_seljuk():
    gs = S.load_scenario("year_of_treacherous_ambition")
    base = S.score(gs)
    gs.meta.notes["reached_ikonion"] = True
    assert S.score(gs)["seljuk"] == base["seljuk"] + 1.0
    gs.meta.notes["reached_western_anatolia"] = True
    assert S.score(gs)["seljuk"] == base["seljuk"] + 2.0


def test_year_end_winter_control_only_scores_at_final_turn():
    objectives = ("manbij", "edessa", "khliat", "manzikert")
    gs = S.load_scenario("year_of_treacherous_ambition")
    # Before the final turn the end-of-Winter control bonus does NOT apply.
    assert gs.meta.calendar_box < gs.meta.final_box
    mid = S.score(gs)
    # Advance to the final turn; the 4 objective Locales each grant +1 to their
    # current controller. Compute the expected split dynamically.
    gs.meta.calendar_box = gs.meta.final_box
    gs.meta.subphase = "campaign.end"   # end-of-turn: control bonus now applies
    exp_r = sum(1.0 for o in objectives if S._locale_control(gs, o) == "roman")
    exp_s = sum(1.0 for o in objectives if S._locale_control(gs, o) == "seljuk")
    assert exp_r + exp_s == 4.0
    end = S.score(gs)
    assert end["roman"] == mid["roman"] + exp_r
    assert end["seljuk"] == mid["seljuk"] + exp_s


def test_year_control_bonus_absent_before_final_turn():
    gs = S.load_scenario("year_of_treacherous_ambition")
    # Manually compute marker-only score (no special control bonus) by checking
    # that moving to the final turn changes the score (the bonus kicks in).
    pre = S.score(gs)
    gs.meta.calendar_box = gs.meta.final_box
    gs.meta.subphase = "campaign.end"
    post = S.score(gs)
    assert post != pre  # the end-of-Winter control bonus is now included


# --- March latch sets the Year objective flag -------------------------------

def test_march_to_ikonion_latches_year_flag():
    gs = S.load_scenario("year_of_treacherous_ambition")
    aa = gs.lords["alp_arslan"]
    aa.mustered = True
    aa.cylinder = "herakleia_kybistra"   # road-adjacent to Ikonion
    aa.assets.provender = 0; aa.assets.loot = 0  # unladen, cheap march
    aa.flags.pop("first_march_used", None)
    gs.meta.phase = "campaign"; gs.meta.subphase = "campaign.command"
    gs.meta.active_player = "seljuk"; gs.meta.active_lord = "alp_arslan"
    gs.meta.active_card = "alp_arslan"; gs.meta.actions_remaining = 4
    gs.seljuk.command_plan = ["alp_arslan"]; gs.seljuk.plan_pointer = 1
    engine.apply_action(gs, {"type": "cmd_march", "lord": "alp_arslan", "to": "ikonion"})
    assert gs.meta.notes.get("reached_ikonion") is True
    assert S.score(gs)["seljuk"] >= 1.0


# --- Artukid Legacy: Mayyafariqin (and Amid) are Supply/Bounty seats ---------

def test_artukid_legacy_makes_mayyafariqin_a_seat():
    gs = S.load_scenario("emperor_and_the_lion")
    ab = gs.lords["artuk_beg"]
    ab.mustered = True
    ab.capabilities = ["S10"]                 # Artukid Legacy
    ab.cylinder = "mayyafariqin"
    # At a seat -> supply cost 0; without the Capability it is not his seat.
    assert campaign._min_supply_cost(gs, ab) == 0
    ab.capabilities = []
    assert campaign._min_supply_cost(gs, ab) != 0


def test_artukid_legacy_bounty_uses_mayyafariqin():
    gs = S.load_scenario("emperor_and_the_lion")
    ab = gs.lords["artuk_beg"]
    ab.mustered = True
    ab.capabilities = ["S10"]
    ab.cylinder = "mayyafariqin"
    ab.assets.loot = 2
    ab.assets.carts = 2
    gs.holding_boxes.mosul_baghdad_loot = 0
    campaign._bounty(gs)
    assert gs.holding_boxes.mosul_baghdad_loot == 2  # banked via Mayyafariqin seat
