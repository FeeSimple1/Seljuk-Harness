"""Cross-game S1/S2/S3/S6: Spoils allocation, Losses and Withdrawal."""
import pytest

from seljuk import battle, campaign, engine, scenarios
from seljuk.rng import DiceRoller
from seljuk.state import Assets, IllegalAction


class Sixes:
    def d6(self):
        return 6


def position(seed=1):
    state = scenarios.load_scenario("emperor_and_the_lion", seed=seed)
    for lord in state.lords.values():
        lord.mustered = False
        lord.cylinder = "offboard"
        lord.besieged = False
        lord.forces = {}
        lord.routed = {}
        lord.themata_on_mat = []
        lord.assets = Assets()
    state.meta.phase = "campaign"
    state.meta.subphase = "campaign.command"
    state.meta.active_lord = state.meta.active_card = "alp_arslan"
    state.meta.active_player = "seljuk"
    state.meta.actions_remaining = 2
    state.meta.pending = []
    return state


def place(state, lid, locale="melitene", **assets):
    lord = state.lords[lid]
    lord.mustered = True
    lord.cylinder = locale
    lord.forces = {"infantry": 1}
    lord.assets = Assets(**assets)
    lord.service_box = 10
    return lord


def test_battle_spoils_spill_to_ally_and_never_exceed_mat_cap():
    state = position()
    first = place(state, "alp_arslan", coin=8)
    second = place(state, "afsin_beg", coin=6)
    loser = place(state, "chatatourios", coin=3)
    events = {"retreat": [{"lord": loser.id, "fate": "retreat"}], "removed": []}
    battle._spoils_and_removal(state, [first.id, second.id], [loser.id],
                              "defender", events, None)
    assert first.assets.coin == second.assets.coin == 8
    assert loser.assets.coin == 0
    assert events["spoils"]["distributed"] == {second.id: {"coin": 2}}
    assert events["spoils"]["lost_to_cap"] == {"coin": 1}


def test_printed_sack_spoils_spill_to_ally():
    state = position()
    first = place(state, "alp_arslan", coin=8, provender=8)
    second = place(state, "afsin_beg")
    reward = battle.award_spoils(state, "melitene", [first.id, second.id])
    assert first.assets.coin == first.assets.provender == 8
    assert second.assets.coin == reward["coin"] == 1
    assert second.assets.provender == reward["provender"] == 2


def test_owner_can_split_each_asset_with_json_roundtrippable_decisions():
    state = position()
    first = place(state, "alp_arslan")
    second = place(state, "afsin_beg")
    ctx = battle.DecisionContext({"seljuk": [
        ["spoils_recipient", second.id], ["spoils_amount", 1],
        ["spoils_recipient", first.id], ["spoils_amount", 2],
        ["spoils_recipient", second.id], ["spoils_amount", 1]], "roman": []})
    result = battle.distribute_spoils(state, {"coin": 4}, [first.id, second.id], ctx)
    assert first.assets.coin == second.assets.coin == 2
    assert result["lost_to_cap"] == {}
    assert all(record["choice"] in record["options"] for record in ctx.trace)


def test_public_storm_uses_winning_owners_spoils_decisions():
    state = position()
    first = place(state, "alp_arslan")
    second = place(state, "afsin_beg")
    loser = place(state, "chatatourios")
    loser.forces = {}
    first.forces = {"ghulam_cavalry": 4, "infantry": 4}
    second.forces = {"ghulam_cavalry": 4, "infantry": 4}
    state.locales["melitene"].siege_markers = 3
    ctx = battle.DecisionContext({"seljuk": [
        ["sack_choice", "conquer"], ["spoils_recipient", second.id],
        ["spoils_amount", 1], ["spoils_recipient", second.id],
        ["spoils_amount", 2]], "roman": []})
    result = battle.resolve_storm(state, [first.id, second.id], "melitene", ctx, Sixes())
    assert result["winner"] == "attacker" and result["sack"]
    assert second.assets.coin == 1 and second.assets.provender == 2
    assert first.assets.coin == first.assets.provender == 0


@pytest.mark.parametrize("conceder", [None, "defender"])
def test_withdrawer_removed_by_losses_transfers_all_assets(conceder):
    state = position()
    winner = place(state, "alp_arslan")
    loser = place(state, "chatatourios", coin=3, carts=2, provender=2, loot=1)
    loser.forces = {}
    loser.routed = {"militia": 1}
    result = battle._end_battle(state, [winner.id], [loser.id], "defender", conceder,
                               "melitene", battle.DecisionContext(), Sixes())
    assert result["retreat"][0]["fate"] == "withdraw"
    assert result["removed"] == [loser.id]
    assert winner.assets.model_dump() == {"coin": 3, "carts": 2, "provender": 2, "loot": 1}
    assert loser.assets == Assets() and not loser.mustered


def test_conceding_retreat_removed_by_losses_transfers_all_assets():
    state = position()
    winner = place(state, "alp_arslan")
    loser = place(state, "chatatourios", coin=3, carts=2, provender=2, loot=1)
    loser.forces = {}
    loser.routed = {"militia": 1}
    ctx = battle.DecisionContext([["retreat", ["retreat", "larisa"]]])
    result = battle._end_battle(state, [winner.id], [loser.id], "defender", "defender",
                               "melitene", ctx, Sixes())
    assert result["retreat"][0]["fate"] == "retreat"
    assert result["removed"] == [loser.id]
    assert winner.assets.coin == 3 and winner.assets.carts == 2


@pytest.mark.parametrize(
    "first_transport,second_transport,second_fate,kept",
    [
        ((2, 0), (0, 2), ["retreat", "larisa"], (2, 0)),
        ((4, 1), (1, 2), ["retreat", "larisa"], (2, 1)),
        ((1, 3), (4, 0), ["retreat", "larisa"], (1, 2)),
        ((2, 2), (0, 0), ["retreat", "larisa"], (2, 0)),
        ((2, 0), (0, 2), ["retreat", "lykandos"], (0, 0)),
        ((2, 0), (0, 2), "withdraw", (0, 0)),
    ],
)
def test_conceding_retreaters_share_carts_only_to_the_same_destination(
    first_transport, second_transport, second_fate, kept,
):
    state = position()
    attacker = place(state, "alp_arslan", "edessa")
    attacker.forces = {"ghulam_cavalry": 4, "turkic_horse": 2}
    first = place(state, "chatatourios", provender=first_transport[0],
                  carts=first_transport[1], coin=1, loot=1)
    second = place(state, "romanos_diogenes", provender=second_transport[0],
                   carts=second_transport[1])
    first.forces = {"infantry": 4, "tagmata": 2}
    second.forces = {"infantry": 4, "tagmata": 2}
    engine.apply_action(state, {"type": "cmd_march", "lord": attacker.id,
                                "to": "melitene", "way_type": "pass"})
    fates = {first.id: ["retreat", "larisa"], second.id: second_fate}
    retreat_choices = [["retreat", fates[lid]] for lid in state.meta.pending[0]["defenders"]]
    result = engine.apply_action(state, {
        "type": "respond_approach",
        "choices": {first.id: {"action": "stand"}, second.id: {"action": "stand"}},
        "battle_decisions": {
            "seljuk": [["concede", False]],
            "roman": [["concede", True], *retreat_choices],
        },
    })["battle"]
    assert result["conceder"] == "defender"
    assert first.cylinder == "larisa"
    assert second.cylinder == ("melitene" if second_fate == "withdraw" else second_fate[1])
    assert result["ending"]["removed"] == []
    assert (first.assets.provender, second.assets.provender) == kept
    assert first.assets.carts == first_transport[1]
    assert second.assets.carts == second_transport[1]
    assert first.assets.coin == 1 and first.assets.loot == 0
    excess = first_transport[0] + second_transport[0] - sum(kept)
    assert result["ending"]["spoils"]["pool"] == {
        "coin": 0, "loot": 1, "provender": excess, "carts": 0,
    }
    assert attacker.assets.loot == 1 and attacker.assets.provender == excess


def test_retreating_lord_removed_by_losses_does_not_lend_carts():
    state = position()
    winner = place(state, "alp_arslan")
    first = place(state, "chatatourios", provender=2)
    second = place(state, "romanos_diogenes", carts=2)
    second.forces = {}
    second.routed = {"militia": 1}
    ctx = battle.DecisionContext([["retreat", ["retreat", "larisa"]]] * 2)
    result = battle._end_battle(state, [winner.id], [first.id, second.id], "defender",
                               "defender", "melitene", ctx, Sixes())
    assert result["retreat"] == [
        {"lord": first.id, "fate": "retreat"}, {"lord": second.id, "fate": "retreat"},
    ]
    assert result["removed"] == [second.id]
    assert first.assets.provender == 0
    assert winner.assets.provender == winner.assets.carts == 2


def test_surviving_withdrawer_keeps_assets():
    state = position()
    winner = place(state, "alp_arslan")
    loser = place(state, "chatatourios", coin=3, carts=2)
    result = battle._end_battle(state, [winner.id], [loser.id], "defender", "defender",
                               "melitene", battle.DecisionContext(), Sixes())
    assert result["removed"] == []
    assert loser.assets.coin == 3 and loser.assets.carts == 2
    assert winner.assets == Assets()


@pytest.mark.parametrize("already_inside", [False, True])
def test_postbattle_withdrawal_uses_shared_capacity_including_existing_occupants(already_inside):
    state = position()
    attacker = place(state, "alp_arslan")
    defenders = [place(state, lid) for lid in
                 ("chatatourios", "romanos_diogenes", "manuel_komnenos")]
    if already_inside:
        inside = place(state, "nikephoros_bryennios")
        inside.besieged = True
    result = battle._end_battle(state, [attacker.id], [lord.id for lord in defenders],
                               "defender", "defender", "melitene", battle.DecisionContext(), Sixes())
    assert sum(member.mustered and member.cylinder == "melitene" and member.besieged
               for member in state.lords.values()) == 2
    assert sum(r["fate"] == "withdraw" for r in result["retreat"]) == (1 if already_inside else 2)


@pytest.mark.parametrize("phase", ["approach", "aftermath"])
def test_constructed_fort_allows_withdrawal_but_has_only_one_slot(phase):
    state = position()
    attacker = place(state, "alp_arslan", "larisa")
    defenders = [place(state, lid, "larisa") for lid in ("chatatourios", "romanos_diogenes")]
    state.locales["larisa"].fort_marker = True
    if phase == "approach":
        state.meta.pending = [{"type": "approach_response", "locale": "larisa",
            "from": "sebasteia", "attackers": [attacker.id], "defenders": [member.id for member in defenders]}]
        before = state.to_json()
        with pytest.raises(IllegalAction, match="stronghold_full"):
            engine.apply_action(state, {"type": "respond_approach", "choices": {
                member.id: {"action": "withdraw"} for member in defenders}})
        assert state.to_json() == before
        engine.apply_action(state, {"type": "respond_approach", "choices": {
            defenders[0].id: {"action": "withdraw"},
            defenders[1].id: {"action": "avoid", "to": "melitene"}}})
    else:
        battle._end_battle(state, [attacker.id], [member.id for member in defenders], "defender",
                           "defender", "larisa", battle.DecisionContext(), DiceRoller(1))
    assert sum(member.mustered and member.cylinder == "larisa" and member.besieged
               for member in state.lords.values()) == 1


def test_avoid_spoils_overflow_also_reaches_ally_with_room():
    state = position()
    first = place(state, "alp_arslan", provender=8, loot=8)
    second = place(state, "afsin_beg")
    campaign._award_avoid_spoils(state, [first.id, second.id], {"loot": 3, "provender": 2})
    assert second.assets.loot == 3 and second.assets.provender == 2
    assert first.assets.loot == first.assets.provender == 8


def test_first_round_attacker_concede_resolves_a_public_approach():
    state = position()
    attacker = place(state, "alp_arslan", locale="edessa")
    defender = place(state, "chatatourios")
    attacker.forces = {"ghulam_cavalry": 8}
    defender.forces = {"tagmata": 8}
    engine.apply_action(state, {"type": "cmd_march", "lord": attacker.id, "to": "melitene"})
    result = engine.apply_action(state, {
        "type": "respond_approach", "choices": {defender.id: {"action": "stand"}},
        "battle_decisions": {"seljuk": [["concede", True]], "roman": [["concede", True]]},
    })["battle"]
    assert result["conceder"] == result["loser"] == "attacker"
    assert result["rounds"] == 1
    assert {step["round"] for step in result["strikes"]} == {1}
    assert [d["choice"] for d in result["decisions"] if d["type"] == "concede"] == [True]


@pytest.mark.parametrize("engagement, winner", [("battle", "attacker"), ("sally", "sally")])
def test_first_round_defender_concede_loses_even_when_its_strikes_rout_attacker(
    engagement, winner,
):
    state = position()
    attacker = place(state, "alp_arslan", locale="edessa" if engagement == "battle" else "melitene")
    defender = place(state, "chatatourios")
    defender.forces = {"tagmata": 8}
    if engagement == "battle":
        engine.apply_action(state, {"type": "cmd_march", "lord": attacker.id, "to": "melitene"})
        action = {"type": "respond_approach", "choices": {defender.id: {"action": "stand"}}}
    else:
        attacker.besieged = True
        loc = state.locales["melitene"]
        loc.conquered_side = "seljuk"
        loc.conquered_count = campaign._stronghold_size(state, "melitene")
        loc.siege_markers = 2
        action = {"type": "cmd_sally", "lord": attacker.id}
    action["battle_decisions"] = {"seljuk": [["concede", False]], "roman": [["concede", True]]}
    result = engine.apply_action(state, action)[engagement]
    assert result["conceder"] == "defender"
    assert result["winner"] == winner
    assert result["rounds"] == 1
    assert [d["choice"] for d in result["decisions"] if d["type"] == "concede"] == [False, True]
    assert any(step["target"] == attacker.id and step["routed_units"] == ["infantry"]
               for step in result["strikes"])
