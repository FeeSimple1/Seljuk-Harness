"""Phase 4: S18 Unstoppable Turkmen -- Bypass without stopping, once per Command."""
from seljuk import scenarios as S, campaign


def test_s18_bypass_without_stopping():
    gs = S.load_scenario("emperor_and_the_lion")
    lord = gs.lords["sav_tekin"]
    lord.mustered = True; lord.cylinder = "manbij"; lord.capabilities = ["S18"]
    to = "melitene"   # Roman Stronghold, no enemy Lords / Siege
    gs.locales[to].siege_markers = 0; gs.locales[to].bypass = False
    r = campaign._resolve_arrival(gs, [lord], to, unstoppable=True)
    assert r.get("bypassed_without_stopping") == to     # no Besiege/Bypass stop
    assert gs.locales[to].bypass is True
    assert lord.flags.get("unstoppable_used_this_card") is True
    assert not any(p["type"] == "besiege_or_bypass" for p in gs.meta.pending)


def test_without_capability_normal_besiege_bypass_pending():
    gs = S.load_scenario("emperor_and_the_lion")
    lord = gs.lords["sav_tekin"]; lord.mustered = True; lord.cylinder = "manbij"
    to = "melitene"; gs.locales[to].siege_markers = 0; gs.locales[to].bypass = False
    # No capability -> normal pending even if unstoppable flag is passed.
    r = campaign._resolve_arrival(gs, [lord], to, unstoppable=True)
    assert r.get("pending") == "besiege_or_bypass"


def test_s18_once_per_command():
    gs = S.load_scenario("emperor_and_the_lion")
    lord = gs.lords["sav_tekin"]; lord.mustered = True; lord.capabilities = ["S18"]
    lord.flags["unstoppable_used_this_card"] = True   # already used this card
    to = "melitene"; gs.locales[to].siege_markers = 0; gs.locales[to].bypass = False
    r = campaign._resolve_arrival(gs, [lord], to, unstoppable=True)
    assert r.get("pending") == "besiege_or_bypass"    # cannot use it twice on one card
