# Playing the Seljuk harness with ChatGPT (bug-hunt setup)

Zip this repo, upload it to a ChatGPT Project (GPT-5.x), and let ChatGPT play
Seljuk in its own Python sandbox — no API key, no network. A baked-in
instrumentation layer (`scripts/chatgpt_play_helper.py`) auto-captures every
engine anomaly (illegal action, crash, stall, broken invariant). A different
model walking different trajectories surfaces bugs scripted sweeps miss.

The only dependency is the engine's own (`pydantic`), which the ChatGPT sandbox
has. Runtime essentials in the zip: the `src/` package + `scripts/` (for
`chatgpt_play_helper.py` and `self_play.py`); `tests/` and PDFs are not needed.

## Project custom instructions (paste verbatim)

> You are playtesting GMT's *Seljuk* (Levy & Campaign Vol. V) via a Python rules
> engine in this project, working in your Python tool. Unzip the uploaded repo if
> needed, then run:
>
> ```python
> import sys; sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
> import chatgpt_play_helper as nv
> nv.start("manzikert", seed=1)          # shortest scenario; see nv.SCENARIOS
> ```
>
> Play turn by turn:
> - `nv.show()` prints the active side's briefing and a NUMBERED list of legal
>   actions. You control BOTH sides; play each turn to win for whichever side is
>   active. You only see the active side's information.
> - Decide, then `nv.apply(N)` to play action number N.
> - Some actions are **templates** (shown `<template>`): `build_plan`,
>   `resolve_event`, `respond_approach`, `assign_themata_defenders`. They need
>   parameters you supply — build them as a FLAT dict and pass it to `nv.apply`,
>   e.g.:
>   - `nv.apply({"type":"build_plan","side":"seljuk","cards":["alp_arslan","alp_arslan","no_command","no_command"]})`
>     (an ordered list of `_plan_size` entries: a Lord id ≤4× each, `"no_command"`
>     ≤5×, exactly one `"treachery"` only if `_treachery_required`).
>   - `nv.apply({"type":"respond_approach","choices":{"<lord>":{"action":"stand"}}})`
>     (each defending Lord: `"stand"`, `"withdraw"`, or `{"action":"avoid","to":"<locale>"}`).
>   - `nv.apply({"type":"assign_themata_defenders","markers":[]})` (indices from the hint, or `[]`).
> - Seljuk actions are FLAT dicts, e.g.
>   `nv.apply({"type":"cmd_march","lord":"alp_arslan","to":"ani","way_type":"road"})`.
> - `nv.auto()` fast-forwards purely-forced turns; call it between decisions to
>   skip boilerplate.
> - Play to win: advance on objectives, March into contact / Siege / Storm, keep
>   Lords supplied (Forage/Supply or you starve and Disband), use Capabilities;
>   Pass only when best.
>
> The harness auto-records any engine anomaly. Periodically and at the end, run
> `nv.findings_report()` and paste its output back to the maintainer — that list
> is the goal of the exercise. `nv.save("game.json")` checkpoints (the sandbox is
> ephemeral; re-run the setup cell if it resets).

## Inspecting state & building the Plan (helpers)

Beyond the per-turn briefing, the helper exposes on-demand detail and a Plan
builder so you don't hand-assemble the trickiest action:

- `nv.state()` / `nv.state("roman")` — structured, hidden-info-filtered state
  for the side to act (or a named side).
- `nv.pending()` — sub-decisions owed right now (resolve these first).
- `nv.lookup_card("S1")` / `nv.lookup_lord("alp_arslan")` — full card text / Lord stats.
- `nv.map("ani")` — Ways out of a Locale (each `{to, type, ...}`) for routing a
  March; `nv.map()` lists every Locale's neighbors.
- `nv.plan_help()` — what the current Campaign Plan needs (size, available Lords, caps).
- `nv.plan(["alp_arslan","alp_arslan","no_command","no_command"])` — build & apply
  the Plan from an ordered list (Lord ids ≤4× each, `"no_command"` ≤5, exactly one
  `"treachery"` iff required); it pre-checks size/caps and explains any mistake
  instead of failing as a "finding".

## Scenarios

`manzikert` (3 turns, shortest — start here), `specter_of_norman_betrayal` (3),
`year_of_treacherous_ambition` (3, Learning), `showdown_in_anatolia` (6),
`emperor_and_the_lion` (12, full campaign). Vary `seed` and re-run; try more than
one model.

## What you get back

`nv.findings_report()` prints `N total, M notable`. Each notable entry is a real
engine defect to triage:
- `over_enum_filtered` / `illegal_action` — the menu offered a move the executor
  rejects (enumerator/handler asymmetry — the dominant class).
- `exception` / `exception_in_probe` — applying an offered move crashed.
- `no_legal_moves` — a stall/deadlock.
- `invariant` / `invariant_crash` — an illegal board state slipped through
  (e.g. co-located enemies).

For each: fix the root and add a **negative enumerator test** (assert the menu
does not offer the bad move, not only that the handler rejects it).

## How it works (and why it's safe)

The menu is the validated palette (`engine.validated_legal_moves`): every
concrete candidate is probed on a throwaway `GameState.from_json(gs.to_json())`
copy and dropped if the handler rejects it, so the model never sees an illegal
move and each drop is logged. This is safe because the RNG lives in the state —
probing advances only the copy's `rng_state`, never the real game's dice.

Smoke-test the wiring locally (no ChatGPT needed):

```python
import sys; sys.path.insert(0, "src"); sys.path.insert(0, "scripts")
import chatgpt_play_helper as nv
nv.start("manzikert", seed=1)
nv.show(); nv.auto()    # then nv.apply(N) at each real choice ...
nv.findings_report()
```
