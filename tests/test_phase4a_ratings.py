"""Phase 4a: Capability rating modifiers (Command / Lordship)."""
from seljuk import scenarios as S, capabilities as C, engine, campaign
from seljuk.rng import DiceRoller


def test_martial_society_plus_one_command_r8():
    gs = S.load_scenario("emperor_and_the_lion")
    l = gs.lords["roussel_de_bailleul"]; l.mustered = True; l.cylinder = "ankyra"; l.capabilities = ["R8"]
    assert C.command_rating(gs, "roussel_de_bailleul") == 3  # base 2 + 1


def test_sickle_of_anatolia_plus_one_command_s12():
    gs = S.load_scenario("emperor_and_the_lion")
    l = gs.lords["afsin_beg"]; l.mustered = True; l.cylinder = "ani"; l.capabilities = ["S12"]
    assert C.command_rating(gs, "afsin_beg") == 4  # base 3 + 1


def test_reconquista_plus_one_lordship_r10():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.lords["robert_crepin"].capabilities = ["R10"]
    assert C.lordship_rating(gs, "robert_crepin") == 2  # base 1 + 1


def test_centralized_administration_conditional_r6():
    gs = S.load_scenario("emperor_and_the_lion")
    l = gs.lords["romanos_diogenes"]; l.capabilities = ["R6"]; l.cylinder = "to_constantinople"
    # At his Seat (Roman Empire Holding Box) with a Supply Route -> +1.
    assert C.command_rating(gs, "romanos_diogenes") == 5  # base 4 + 1
    # Move to a Seljuk Locale (outside the Roman Empire) -> no bonus.
    l.cylinder = "ani"
    assert C.command_rating(gs, "romanos_diogenes") == 4


def test_support_from_aleppo_rolls_for_bonus_s14():
    gs = S.load_scenario("emperor_and_the_lion")
    l = gs.lords["ibn_khan"]; l.mustered = True; l.cylinder = "hama"; l.capabilities = ["S14"]
    # roll <= 3 grants +1; find seeds for each branch.
    def first(v):
        for s in range(200):
            if DiceRoller(s).d6() == v:
                return DiceRoller(s)
        raise AssertionError
    assert C.command_rating(gs, "ibn_khan", first(2)) == 3  # base 2 +1 (roll 2)
    assert C.command_rating(gs, "ibn_khan", first(5)) == 2  # base 2 (roll 5)


def test_lordship_bonus_reflected_in_muster_budget():
    gs = S.load_scenario("emperor_and_the_lion")
    gs.lords["roussel_de_bailleul"].capabilities = ["R10"]
    from seljuk.actions import lordship_remaining
    gs.lords["roussel_de_bailleul"].flags["lordship_spent"] = 0
    assert lordship_remaining(gs, gs.lords["roussel_de_bailleul"]) == 2
