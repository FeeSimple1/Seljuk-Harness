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

### Validated palette (optional, recommended for agents)

`legal-moves --validate` returns the same palette but first probes every concrete
candidate on a throwaway copy of the game and **drops any move the rules engine
would reject**, printing each drop as an over-enumeration diagnostic on stderr.
So an agent that plays only from the validated palette never submits an illegal
move. (Templated moves — `build_plan`, `resolve_event`, `respond_approach`,
`assign_themata_defenders` — can't be probed blind and are returned marked
`"_unvalidated": true`.) It is slower (a probe per candidate) so it is for the
interactive/agent path, not bulk sweeps.

If you submit an illegal action, `do` prints `IllegalAction: <reason>` and exits
non-zero **without changing the game** — pick a different move. Every move
`legal-moves` offers is guaranteed applicable.

### Template actions and optional parameters

Most moves are ready to apply as-is. Some are templates or carry optional
parameters (hinted by `_`-prefixed keys):

- **build_plan** (Campaign Plan step). `legal-moves` gives `_plan_size` (how many
  cards), `_available_lords`, and `_treachery_required`. Build an ordered list
  of that many entries, each a Lord id (whose Command card you play, ≤4 per
  Lord), `"no_command"` (≤5), or `"treachery"` (exactly one, only if
  `_treachery_required`). Example:
  ```bash
  --action '{"type":"build_plan","side":"seljuk","cards":["alp_arslan","alp_arslan","afsin_beg","no_command","no_command","no_command","no_command"]}'
  ```
- **cmd_march with a Group March** (4.3.1). A `cmd_march` move that carries a
  `_co_marchers` hint (a list of co-located friendly Lord ids) and `_co_marcher_max`
  may optionally bring some of those Lords. Add a `"group"` list (a subset of
  `_co_marchers`, at most `_co_marcher_max`) to March them together:
  ```bash
  --action '{"type":"cmd_march","lord":"alp_arslan","to":"ararat","way_type":"pass","group":["arisighi"]}'
  ```
  The active Lord leads (he must be a Commander, or an S7 Trusted Commander who
  may bring exactly one). The whole group moves to the destination and the action
  cost is recomputed for the combined (possibly Laden) group, so a Group March may
  cost more than the solo March shown. Omit `group` to March alone.
- **cmd_march discard variants** (1.7.2). A Laden group's March move may carry
  `discard_excess` (over-laden: shed the excess Provender just to move) and/or a
  separate `discard_to_unladen` variant (shed all Loot + excess Provender to March
  one Command action cheaper). Apply whichever the menu offers; both shed Assets,
  so they are offered as explicit alternatives to the full-cost Laden March.
- **cmd_siege variants** (4.5.1). Besides the default Siege (roll Surrender, then
  add Siegeworks on failure), the menu may offer `roll_surrender:false` (add a
  Siegeworks without rolling) and, with R25 held, `honors_of_war:true` (a Fort
  auto-Surrenders). Pick the variant object as offered.
- **build_plan lieutenants** (4.1.3). The build_plan move hints
  `_lieutenant_options` (eligible `{"lieutenant": L, "lower_lord": M}` pairs:
  same side, co-located, neither a Commander, neither already stacked). Pass a
  `"lieutenants"` list of such pairs to appoint them for the Campaign; the
  Lieutenant then plays his Lower Lord's Command cards.
- **In-Battle Held Events** (`battle_events`). Moves that start a combat accept
  `"battle_events": {"seljuk": [...], "roman": [...]}` naming Held Event cards
  EITHER side plays for that combat; the palette hints what is available via
  `_battle_holds_available` (respond_approach, cmd_sally) or
  `_storm_events_available` (cmd_storm). Battle (Stand/Sortie) honors
  R2/S2/S3/S6/R24/R21/S21 (S6/R24 entries are dicts naming the Roman Lord:
  `{"card":"R24","lord":...}`); Storm honors R21/S21 plus, for the Roman
  defender, `"play_sultans_horse": true` (R4: Rounds -1, hinted by
  `_r4_sultans_horse_available`); Sally honors R21/S21 and R2/S2.
- **steeled_rounds** (R3 Steeled Resolve). Any combat-starting move accepts
  `"steeled_rounds": {LORD: N}` — the Round (default 1) in which that Lord's
  Capability applies.
- **local_scouts** (R18, respond_approach). The Approaching side may force one
  Avoiding Lord to Stand/Withdraw: `"local_scouts": {"lord": L, "action": "stand"}`.
- **besiege_bypass with surprise** (S1). The menu offers a
  `{"choice":"besiege","surprise":true}` variant when S1 is held and eligible;
  optionally add `storm_decisions` for the immediate Storm. If the Stronghold
  is owed a Themata assignment, that pends FIRST (S1 Clarification) and the
  2 Siege markers + Storm resume after it.
- **Loyalty coin DRMs** (1.4.1). `resolve_loyalty` / `discard_imperial_coffers`
  accept `"coins_for"` (checking side, +1 each) and `"coins_against"` (owner
  resists, -1 each), bounded by the `_max_coins_for` / `_max_coins_against`
  hints (Commander + co-located Unbesieged Lords' Coin; no resisting for a
  Besieged target).
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
| `loyalty_check` | `{"type":"resolve_loyalty","target":LORD}` (from `targets`; optional `coins_for`/`coins_against`, see hints) |
| `basil_response` | `{"type":"basil_response","play":true\|false}` |
| `winter_quarters` | `{"type":"winter_quarters","lord":L,"dest":SEAT}` or `{"lord":L,"stay":true}` (R15/S15; options in the pending's `dests`/`may_stay`) |

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
