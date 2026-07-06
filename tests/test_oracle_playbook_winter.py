"""Oracles from the Playbook Examples of Play: Winter (p12) and Loyalty Check
(pp.10-11), driven through the real engine functions.

Winter (Winter 1068): Seljuk Unity goal 10 vs 6 marked Locales -> lose 4 VP
(never a gain above the goal); Bounty +2 VP arrived FIRST (order: Bounty then
Unity); Alp Arslan "can choose to return to Ani or the Mosul & Baghdad Holding
Box" (Winter Quarters is the OWNER's choice); Nikephoros with Fealty To The
Basileus "can choose to stay in the field". Aleppo Diplomacy: a roll of 3
keeps the Independent marker (removal range is 1-2).

Loyalty Check (Robert Crepin, Fealty 4): the checking side may spend Coin
(+1 each) from its Commander; the owner resists (-1 each); with one Coin
against, "the Seljuk player must roll a 6 to succeed (normally a 5-6)";
a natural 6 always succeeds, a natural 1 always fails.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from seljuk import scenarios as S, campaign, actions, engine
from seljuk.rng import DiceRoller


class SeqRoller:
    def __init__(self, *vals): self.vals = list(vals); self.i = 0
    def d6(self):
        v = self.vals[min(self.i, len(self.vals) - 1)]; self.i += 1; return v
    def roll(self, n): return [self.d6() for _ in range(n)]


# --- Winter: Seljuk Unity (goal 10, six marked Locales -> -4 VP) -------------

def test_winter_example_seljuk_unity_shortfall_of_four():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    gs.meta.calendar_box = 3
    gs.meta.seljuk_unity_targets = {"3": 10}
    for st in gs.locales.values():   # pristine board: exactly the example's markers
        st.ravaged_side = None; st.ruins = False; st.ruins_color = None; st.conquered_side = None
    # Six Seljuk-marked Locales: 4 Ravaged + 1 Ruins + 1 Conquered (p12).
    for loc in ("chaldia", "keltzene", "melitene", "germanikeia"):
        gs.locales[loc].ravaged_side = "seljuk"
    gs.locales["kaisareia"].ruins = True; gs.locales["kaisareia"].ruins_color = "seljuk"
    gs.locales["theodosiopolis"].conquered_side = "seljuk"
    gs.holding_boxes.mosul_baghdad_loot = 2          # the +2 VP Bounty just banked
    gs.holding_boxes.constantinople_roman_vp_markers = 0
    campaign._seljuk_unity(gs)
    # Deficit 4: first strip banked Mosul Loot VP (2), then Roman +1 VP markers.
    assert gs.holding_boxes.mosul_baghdad_loot == 0
    assert gs.holding_boxes.constantinople_roman_vp_markers == 2


def test_winter_example_seljuk_unity_no_gain_at_or_above_goal():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    gs.meta.calendar_box = 3
    gs.meta.seljuk_unity_targets = {"3": 3}
    for loc in ("chaldia", "keltzene", "melitene", "germanikeia"):
        gs.locales[loc].ravaged_side = "seljuk"      # 4 >= goal 3
    gs.holding_boxes.mosul_baghdad_loot = 2
    campaign._seljuk_unity(gs)
    assert gs.holding_boxes.mosul_baghdad_loot == 2  # "lose 0 VP (but not gain)"
    assert gs.holding_boxes.constantinople_roman_vp_markers == 0


# --- Winter: Quarters is the owner's CHOICE (p12) ----------------------------

def test_winter_example_alp_chooses_ani_or_mosul_box():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    aa = gs.lords["alp_arslan"]; aa.cylinder = "melitene"
    gs.meta.calendar_box = 3; gs.meta.phase = "campaign"
    gs.roman.held_events = []; gs.seljuk.held_events = []
    campaign._end_campaign(gs)
    p = next(p for p in gs.meta.pending if p["type"] == "winter_quarters" and p["lord"] == "alp_arslan")
    assert set(p["dests"]) == {"ani", "to_mosul_and_baghdad"}   # "can choose to return to Ani or ..."
    mvs = [m for m in engine.legal_moves(gs) if m["type"] == "winter_quarters"]
    assert mvs, "the Quarters choice must be in the palette"
    engine.apply_action(gs, {"type": "winter_quarters", "lord": "alp_arslan",
                             "dest": "to_mosul_and_baghdad"})
    assert aa.cylinder == "to_mosul_and_baghdad"


def test_winter_example_fealty_to_basileus_stay_is_a_choice_r15():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    rom = gs.lords["romanos_diogenes"]
    rom.cylinder = "theodosiopolis"; rom.capabilities = ["R15"]   # Fealty To The Basileus
    campaign._begin_winter_quarters(gs)
    p = next(p for p in gs.meta.pending if p["type"] == "winter_quarters" and p["lord"] == "romanos_diogenes")
    assert p["may_stay"]
    engine.apply_action(gs, {"type": "winter_quarters", "lord": "romanos_diogenes", "stay": True})
    assert rom.cylinder == "theodosiopolis"          # "chooses to stay in the field"
    # ...but returning is equally legal (errata Clarification: to HIS Seat only).
    gs2 = S.load_scenario("emperor_and_the_lion", seed=1)
    r2 = gs2.lords["romanos_diogenes"]
    r2.cylinder = "theodosiopolis"; r2.capabilities = ["R15"]
    campaign._begin_winter_quarters(gs2)
    p2 = next(p for p in gs2.meta.pending if p["type"] == "winter_quarters" and p["lord"] == "romanos_diogenes")
    engine.apply_action(gs2, {"type": "winter_quarters", "lord": "romanos_diogenes",
                              "dest": p2["dests"][0]})
    assert r2.cylinder == p2["dests"][0]


# --- Winter: Aleppo Diplomacy die (a 3 keeps the marker; 1-2 removes) --------

def test_winter_example_aleppo_diplomacy_roll_three_stays():
    gs = S.load_scenario("emperor_and_the_lion", seed=7)
    gs.meta.independent_aleppo_on_map = True
    r = DiceRoller(seed=7)
    while True:
        st = r.get_state()
        if r.d6() == 3:
            break
    gs.meta.rng_state = [st[0], list(st[1]), st[2]]
    campaign._aleppo_diplomacy(gs)
    assert gs.meta.independent_aleppo_on_map is True     # "roll is a 3, and it stays"


def test_winter_example_aleppo_diplomacy_low_roll_removes():
    gs = S.load_scenario("emperor_and_the_lion", seed=7)
    gs.meta.independent_aleppo_on_map = True
    r = DiceRoller(seed=7)
    while True:
        st = r.get_state()
        if r.d6() <= 2:
            break
    gs.meta.rng_state = [st[0], list(st[1]), st[2]]
    campaign._aleppo_diplomacy(gs)
    assert gs.meta.independent_aleppo_on_map is False


# --- Loyalty Check (pp.10-11): Robert, Fealty 4, one Coin against ------------

def test_loyalty_example_coin_against_needs_a_six():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    rob = gs.lords["robert_crepin"]
    rob.side = "roman"; rob.mustered = True; rob.cylinder = "edessa"; rob.besieged = False
    rom = gs.lords["romanos_diogenes"]; rom.assets.coin = 1      # "spends his last Coin"
    res = actions.resolve_loyalty_check(gs, "robert_crepin", "seljuk",
                                        SeqRoller(5), coins_for=0, coins_against=1)
    assert res["fealty"] == 4
    assert res["natural"] == 5 and res["modified"] == 4
    assert res["switched"] is False          # "must roll a 6 (normally a 5-6)"
    assert rom.assets.coin == 0              # the resisting Coin is spent


def test_loyalty_example_natural_six_always_succeeds():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    rob = gs.lords["robert_crepin"]
    rob.side = "roman"; rob.mustered = True; rob.cylinder = "edessa"; rob.besieged = False
    gs.lords["romanos_diogenes"].assets.coin = 1
    res = actions.resolve_loyalty_check(gs, "robert_crepin", "seljuk",
                                        SeqRoller(6), coins_for=0, coins_against=1)
    assert res["switched"] is True           # "a roll of 6 always being a success"
    assert gs.lords["robert_crepin"].side == "seljuk"


def test_loyalty_example_natural_one_always_fails():
    gs = S.load_scenario("emperor_and_the_lion", seed=1)
    rob = gs.lords["robert_crepin"]
    rob.side = "roman"; rob.mustered = True; rob.cylinder = "edessa"; rob.besieged = False
    aa = gs.lords["alp_arslan"]; aa.assets.coin = 8              # huge +DRM cannot save a 1
    res = actions.resolve_loyalty_check(gs, "robert_crepin", "seljuk",
                                        SeqRoller(1), coins_for=5, coins_against=0)
    assert res["switched"] is False
