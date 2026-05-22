# Seljuk Harness — LLM Play Guide

This guide lets another agent (or person) play a full game of GMT's *Seljuk*
through the harness. The harness enforces every rule, auto-resolves dice, and
tells you the legal moves at every step — you supply the decisions.

You drive the game entirely through the `seljuk.cli` command line against a
**save file** (a JSON game state). Every command reads that file; `do` also
writes it back. Run commands with:

```bash
PYTHONPATH=src python -m seljuk.cli <command> [args]
```

(If the package is installed, just `seljuk <command>`.)

## Scenarios

`emperor_and_the_lion`, `specter_of_norman_betrayal`, `year_of_treacherous_ambition`,
`showdown_in_anatolia`, `manzikert`. The two sides are **seljuk** and **roman**.

## The turn loop

The whole game is this loop. Repeat until the game is over.

```bash
# 1. Start a game (once)
python -m seljuk.cli new emperor_and_the_lion --seed 1 --out game.json

# 2. Read the situation (human-readable). Note the ACTIVE side.
python -m seljuk.cli briefing --file game.json

# 3. Resolve any owed sub-decisions FIRST (see "Pending" below).
python -m seljuk.cli pending --file game.json

# 4. List the active side's legal actions (machine-readable JSON palette).
python -m seljuk.cli legal-moves --file game.json

# 5. Pick ONE action and apply it. This saves the new state back to the file.
python -m seljuk.cli do --file game.json --action '{"type": "pass_step"}'

# 6. Go back to step 2.
```

Each command prints a status line like
`phase=campaign/campaign.command  active=seljuk  actions_left=3  box=4/12`
so you always know whose turn it is and where you are. When the game ends it
prints `GAME OVER - winner: seljuk|roman|draw`.

### Choosing an action

`legal-moves` returns a JSON array of action objects. Each has a `type` and the
parameters the handler needs, plus a human `_desc`. To play one, pass it to
`do`. You may keep or drop the `_`-prefixed hint fields — the engine ignores
them. Example:

```bash
python -m seljuk.cli do --file game.json \
  --action '{"type": "cmd_march", "lord": "alp_arslan", "to": "ani", "way_type": "road"}'
```

If you submit an illegal action, `do` prints `IllegalAction: <reason>` and exits
non-zero **without changing the game** — pick a different move. Every move
`legal-moves` offers is guaranteed applicable.

### Two template actions that need you to build them

Most moves are ready to apply as-is. Two are templates:

- **build_plan** (Campaign Plan step). `legal-moves` gives `_plan_size` (how many
  cards), `_available_lords`, and `_treachery_required`. Build an ordered list
  of that many entries, each a Lord id (whose Command card you play, ≤4 per
  Lord), `"no_command"` (≤5), or `"treachery"` (exactly one, only if
  `_treachery_required`). Example:
  ```bash
  --action '{"type":"build_plan","side":"seljuk","cards":["alp_arslan","alp_arslan","afsin_beg","no_command","no_command","no_command","no_command"]}'
  ```
- **resolve_event** (an immediate Arts-of-War Event that needs a choice). Pass
  `args` with the choice the card calls for, e.g.
  `{"type":"resolve_event","card":"R5","args":{"lord":"alp_arslan","direction":"left"}}`.
  Look the card up with `lookup_card` semantics (its text is in
  `data/static/cards.json`). Events that need no choice resolve with `args:{}`.

## Pending sub-decisions

After some actions the game owes a sub-decision before normal play resumes.
`pending` lists them; resolve each with `do`. The mapping:

| pending `type` | resolve with action |
|----------------|---------------------|
| `deploy_capability` | `{"type":"deploy_capability","card":C,"lord":L}` (L from `eligible`) |
| `event_pending_resolution` | `{"type":"resolve_event","card":C,"args":{...}}` |
| `approach_response` | `{"type":"respond_approach","choices":{LORD:{"action":"stand"\|"withdraw"\|"avoid","to":LOCALE}}}` |
| `besiege_or_bypass` | `{"type":"besiege_bypass","choice":"besiege"\|"bypass"}` |
| `assign_themata_defenders` | `{"type":"assign_themata_defenders","markers":[...]}` |
| `ravage_defence` | `{"type":"resolve_ravage_defence","defend_with":INDEX_or_null}` |
| `loyalty_check` | `{"type":"resolve_loyalty","target":LORD}` (from `targets`) |
| `basil_response` | `{"type":"basil_response","play":true\|false}` |

Battles, Storms, and Sallies are **auto-resolved** by the engine when you Stand
(or Storm/Sally); the result is returned by `do`. You don't roll dice — the
seeded RNG in the save file does, deterministically.

## Hidden information

`state --file game.json --side seljuk --json` returns the machine-readable game
state **filtered for that side**: the opponent's draw deck, held Events, and
unrevealed Plan cards are masked as `"<hidden>"`. Your own are fully visible, as
are the opponent's already-revealed Command cards. The human `briefing` and
`state` (summary) views are for convenience/observing.

## Winning

`is_over` is true when `phase == game_over`; the winner is in the status line and
in `winner`. Victory comes from VP (½ per Ruins/Ravaged, 1 per Roman-Conquered),
the Seljuk Unity track, or an Aleppo auto-victory — all scored by the engine.

---

## Mode A — Solo / single chat

One chat drives both sides (or plays one side and makes reasonable moves for the
other). Just run the turn loop; the `active` side in the status line tells you
who acts. Nothing else to coordinate.

## Mode B — Head-to-head (two chats)

Two chats play a real game, one as **seljuk** and one as **roman**, sharing a
single save file in a folder both can read/write (e.g. the Cowork workspace).

Setup (either chat, once):
```bash
python -m seljuk.cli new <scenario> --out /path/to/shared/game.json
```

Each chat's turn protocol:
1. `briefing --file game.json` and read the status line. **Act only when
   `active=` is your side.** If it's the opponent's turn, wait and re-check.
2. View your own state: `state --file game.json --side YOUR_SIDE --json`.
3. Resolve `pending` decisions that are yours, then `legal-moves`, then `do`.
4. After your `do`, the status line shows whose turn is next. Hand off (the file
   is already saved).

Honor system: the harness does **not** stop a chat from reading the opponent's
filtered-out info or applying the opponent's moves. For a fair game, each chat
should only ever call `state --side ITS_OWN_SIDE`, only resolve pending
decisions owed by its side, and only `do` actions for its own Lords. The
`legal-moves` palette is always for the current `active` side, so following "act
only on your turn" keeps both honest.

Tip: keep a turn log by piping `do` output to a shared file, or use
`history --file game.json --n 20` to review recent moves.

## Quick reference — common action types

You never need to memorise these (use `legal-moves`), but for orientation:
Levy: `pay`, `levy_lord`, `levy_vassal`, `levy_transport`, `levy_capability`,
`levy_themata`, `cta_loot`, `cta_strategic_objective`, `pass_step`.
Campaign: `build_plan`, `cmd_march`, `cmd_tax`, `cmd_forage`, `cmd_ravage`,
`cmd_supply`, `cmd_recruit`, `cmd_siege`, `cmd_storm`, `cmd_sally`, `cmd_pass`,
`end_activation`, `play_hold_event`, `winter_activate`, `winter_proceed`.
