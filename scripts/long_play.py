"""Long, sustained self-play for deep-coverage bug-hunting (companion to
self_play.py and smoke_fuzz.py).

Unlike the greedy/aggressive drivers (which end games in a few turns), this
SUSTAINS both sides through Levy (Pay, then Muster Lords back from the Calendar,
then other levies + Call to Arms) and plays militarily WITHOUT rushing the
VP/Unity victory, so games run deep into the calendar -- multiple Turns, every
Winter/End-Campaign interphase, and the end-of-game VP scoring (5.3). It also
occasionally exercises Group March (4.3.1) co-marchers.

Checks after every step:
  * check_invariants on the live state;
  * round-trip every concrete enumerated move on a snapshot (over-enumeration +
    post-move invariants);
  * periodic save/load + reserialization-stability round-trip;
  * scenarios.score() runs without error;
and any uncaught exception is captured as a CRASH finding.

Usage:
  PYTHONPATH=src python3 scripts/long_play.py <scenario|ALL> <seeds csv>
  SUSTAIN=1 ... # de-prioritise combat to maximise game length
"""
import sys, random, json
sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
from seljuk.llm import LLMSession
from seljuk import engine, scenarios, static_data as sd
from seljuk.state import GameState, IllegalAction
from seljuk.invariants import check_invariants
from self_play import _resolve_pending, _build_plan_action

TEMPLATE = {"build_plan", "resolve_event"}
# Command preference: sustain + maneuver + fight, but de-prioritise Ravage (the
# VP/Unity victory driver) so games run long. Pass/end last.
PREF = ["cmd_supply","cmd_forage","cmd_recruit","cmd_tax","cmd_siege","cmd_storm",
        "cmd_sally","cmd_march","cmd_encamp","cmd_sortie","cmd_take_gift_coin",
        "play_hold_event","cmd_ravage","cmd_pass"]

def snapshot_roundtrip(s, findings, tag):
    """Over-enumeration: every concrete enumerated move must apply on a snapshot."""
    for mv in s.legal_actions():
        if mv["type"] in TEMPLATE:
            continue
        snap = GameState.from_json(s.gs.to_json())
        try:
            engine.apply_action(snap, {k:v for k,v in mv.items() if not k.startswith("_")})
        except IllegalAction as e:
            findings.append(f"{tag} OVER-ENUM {mv['type']}: {e}")
        else:
            iv = check_invariants(snap)
            if iv: findings.append(f"{tag} POST-MOVE-INVARIANT {mv['type']}: {iv[0]}")

def checks(s, findings, tag, deep=False):
    iv = check_invariants(s.gs)
    if iv: findings.append(f"{tag} INVARIANT: {iv[0]}")
    try:
        sc = scenarios.score(s.gs)
    except Exception as e:
        findings.append(f"{tag} SCORE-CRASH: {type(e).__name__}: {e}")
    if deep:
        j1 = s.gs.to_json(); g2 = GameState.from_json(j1); j2 = g2.to_json()
        if j1 != j2:
            findings.append(f"{tag} SERIALISATION-UNSTABLE")
        iv2 = check_invariants(g2)
        if iv2: findings.append(f"{tag} RELOAD-INVARIANT: {iv2[0]}")

def levy_apply(s, rng):
    """Sustain the active side: pay everyone, muster what we can, take CtA."""
    moves = s.legal_actions()
    t = {m["type"]: m for m in moves}
    if "deploy_capability" in t:
        s.apply(t["deploy_capability"]); return True
    # Pay every Lord we can (extends Service), then finish the step.
    pays = [m for m in moves if m["type"] == "pay"]
    if pays: s.apply(rng.choice(pays)); return True
    # Muster LORDS first (bring Lords from the Calendar back onto the map, 3.4.1)
    # so the side does not collapse to "no Mustered Lords"; then other levies.
    lord_musters = [m for m in moves if m["type"] == "levy_lord"]
    if lord_musters: s.apply(rng.choice(lord_musters)); return True
    other = [m for m in moves if m["type"] in
             ("levy_vassal","levy_transport","levy_capability","levy_themata","muster_restore")]
    if other and rng.random() < 0.7: s.apply(rng.choice(other)); return True
    cta = [m for m in moves if m["type"].startswith("cta_")]
    if cta and rng.random() < 0.5: s.apply(rng.choice(cta)); return True
    if "pass_step" in t: s.apply(t["pass_step"]); return True
    return False

import os
SUSTAIN = os.environ.get("SUSTAIN") == "1"
SUSTAIN_PREF = ["cmd_supply","cmd_forage","cmd_recruit","cmd_tax","cmd_take_gift_coin","cmd_pass"]

def cmd_apply(s, rng):
    moves = s.legal_actions()
    t = {m["type"]: m for m in moves}
    if "build_plan" in t:
        s.apply(_build_plan_action(s, t["build_plan"])); return True
    concrete = [m for m in moves if m["type"] not in TEMPLATE]
    pref = SUSTAIN_PREF if SUSTAIN else PREF
    if SUSTAIN:
        for typ in pref:
            cand = [m for m in concrete if m["type"] == typ]
            if cand:
                m = rng.choice(cand)
                s.apply({k:v for k,v in m.items() if not k.startswith("_")}); return True
        if "end_activation" in t: s.apply(t["end_activation"]); return True
        if "cmd_pass" in t: s.apply(t["cmd_pass"]); return True
        if moves: s.apply({k:v for k,v in moves[0].items() if not k.startswith("_")}); return True
        return False
    # Choose by preference, with light randomness; skip end/pass unless nothing else.
    for typ in PREF:
        cand = [m for m in concrete if m["type"] == typ]
        if cand:
            m = rng.choice(cand)
            act = {k:v for k,v in m.items() if not k.startswith("_")}
            # sometimes exercise Group March
            if act["type"] == "cmd_march" and m.get("_co_marchers") and rng.random() < 0.4:
                k = rng.randint(1, m["_co_marcher_max"])
                act["group"] = rng.sample(m["_co_marchers"], k)
            if act["type"] == "cmd_storm": act["storm_decisions"] = [("concede", rng.random()<0.3)]*8
            if act["type"] == "cmd_sally": act["battle_decisions"] = [("concede", rng.random()<0.3)]*8
            s.apply(act); return True
    if "end_activation" in t: s.apply(t["end_activation"]); return True
    if "cmd_pass" in t: s.apply(t["cmd_pass"]); return True
    if moves: s.apply({k:v for k,v in moves[0].items() if not k.startswith("_")}); return True
    return False

def play(scenario, seed, max_steps=20000):
    findings = []
    s = LLMSession.start_new(scenario, seed)
    rng = random.Random(seed*131+7)
    steps = 0; combats = 0; max_box = s.gs.meta.calendar_box
    iv = check_invariants(s.gs)
    if iv: return dict(seed=seed, findings=[f"@start {iv[0]}"], box=max_box, steps=0, over=False)
    while not s.is_over() and steps < max_steps:
        steps += 1
        tag = f"{scenario}#{seed}@{steps}/{s.gs.meta.subphase}"
        try:
            if s.gs.meta.pending:
                if not _resolve_pending(s):
                    s.gs.meta.pending.pop(0)
            elif s.gs.meta.phase in ("campaign", "winter"):
                # over-enum check before acting
                snapshot_roundtrip(s, findings, tag)
                if not cmd_apply(s, rng): break
            elif s.gs.meta.phase == "levy":
                if not levy_apply(s, rng): break
            else:
                break
            checks(s, findings, tag, deep=(steps % 50 == 0))
            max_box = max(max_box, s.gs.meta.calendar_box)
        except IllegalAction as e:
            findings.append(f"{tag} APPLIED-ILLEGAL: {e}")
            break
        except Exception as e:
            import traceback
            findings.append(f"{tag} CRASH {type(e).__name__}: {e}\n{traceback.format_exc()}")
            break
        if len(findings) > 30: break
    return dict(seed=seed, findings=findings, box=max_box, steps=steps,
                over=s.is_over(), winner=s.winner(), reason=s.gs.meta.notes.get("win_reason"))

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "emperor_and_the_lion"
    seeds = [int(x) for x in (sys.argv[2].split(",") if len(sys.argv) > 2 else ["1"])]
    for sd_ in seeds:
        r = play(which, sd_)
        flag = "  <<< FINDINGS" if r["findings"] else ""
        print(f"{which[:20]:20} seed {sd_}: box={r['box']} steps={r['steps']} over={r['over']} winner={r['winner']} reason={r.get('reason')}{flag}")
        for f in r["findings"][:12]:
            print("    ", f.splitlines()[0])
