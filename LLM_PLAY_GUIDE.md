# Seljuk Harness — LLM Play Guide

This guide lets another agent (or person) play a full game of GMT's *Seljuk*
through the harness. The harness implements the rules and auto-resolves dice; you supply the
decisions. Published rules, errata, and recorded adjudications remain the
authority, and tests do not establish that every reachable position is bug-free.

For token-efficient sandbox play, use `scripts/chatgpt_play_helper.py`; see
`CHATGPT_PLAY.md` for compact overviews, complete action pages, versioned ids,
private response handoffs, intact references, and explicit Plans. The guide
below describes the legacy, trusted `seljuk.cli` interface against a
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

# 2. Read the situation (human-readable). Note the DECISION owner (which may differ from the active side).
python -m seljuk.cli briefing --file game.json

# 3. Resolve any owed sub-decisions FIRST (see "Pending" below).
python -m seljuk.cli pending --file game.json

# 4. List the decision owner's legal actions (machine-readable JSON palette).
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
non-zero **without changing the game** — pick a different move. Concrete validated rows are probed in the current state; templates and added
parameter combinations still require validation. A stale state can change legality.

### Template actions and optional parameters

Most moves are ready to apply as-is. Some are templates or carry optional
parameters (hinted by `_`-prefixed keys):

- **build_plan** (Campaign Plan step). `legal-moves` gives `_plan_size` (how many
  cards), `_available_lords`, and `_treachery_required`. Build an ordered list
  of that many entries, each a Lord id (whose Command card you play, ≤4 per
  Lord), `"no_command"` (use `_constraints.no_command_max`, normally five,
  six when Treachery adds the extra card), or `"treachery"` (exactly one, only if
  `_treachery_required`). `_no_command_required` includes Treachery and Weather;
  `_constraints` exposes the engine's exact requirements. Example:
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
  EITHER side plays for that combat. Player-facing palettes expose only the
  viewing player's hand, via `_combat_inputs`. A trusted CLI caller collects
  both players' choices; the compact helper supplies explicit private handoffs. Battle (Stand/Sortie) AND Sally
  (D-008) honor the full set R2/S2/S3/S6/R24/R21/S21 (S6/R24 entries are
  dicts naming the Roman Lord: `{"card":"R24","lord":...}`); Storm honors
  R21/S21 plus, for the Roman defender, `"play_sultans_horse": true`
  (R4: Rounds -1, disclosed only to the Roman player).
- **S3 Betrayal.** Seljuk may declare `{"card":"S3","lord":"lord_id"}` in
  `battle_events`. After Reposition, at least two Roman Lords must remain in
  combat and the selected Lord must be a non-Commander in the Front. S3 is
  used once per game when the Lord moves to Reserve. If the target never
  qualifies, keep S3 Held. A bare `"S3"` selects the first eligible Front Lord.
- **R21/S21 Turkic Horse removal.** In `battle_events`, name the exact
  targets, for example `{"card":"R21","targets":[{"lord":"alp_arslan","count":1}]}`.
  You may split up to two removals among eligible Lords at the combat Locale,
  including Besieged Lords and other nonparticipants. To select a unit on a
  Levied Themata marker, add its zero-based `index` on that Lord's mat and
  `"kind":"unit"`. For S21 a whole marker costs one removal. Use
  `"kind":"marker"` and the index, omitting `lord` for a marker defending the
  Stronghold. Compact combat details list visible targets and screen hidden
  mats. The trusted standalone Hold uses the same `targets` in `args` along
  with `locale`. Legacy count-only declarations work for unambiguous enemy
  targets. Name your targets explicitly if friendly Turkic Horse are present.
  Omit the card to keep it Held.
- **steeled_rounds** (R3 Steeled Resolve). Any combat-starting move accepts
  `"steeled_rounds": {LORD: N}` — the Round (default 1) in which that Lord's
  Capability applies.
- **local_scouts** (R18, respond_approach). The Roman Approaching player declares
  R18; the avoiding side selects the Lord and Stand/Withdraw. A trusted CLI
  caller collects that response as `"local_scouts": {"lord": L, "action": "stand"}`.
  The compact helper separates the declaration and the enemy's selection.
- **sally_join** (Relief Sally, 4.8.1). If an Approach leads to Battle, the
  Approaching player may choose any subset of friendly Besieged Lords at the
  Locale. Pass `"sally_join": []` to keep everyone inside, or list the Lords
  who join. The compact helper lists eligible Lords in the Approaching
  player's input window. When playing Local Scouts, the Approaching player
  may wait for the defender's response before choosing. A trusted caller
  supplies the field on `respond_approach`. Omission keeps the legacy
  all-join default.
- **besiege_bypass with surprise** (S1). The menu offers a
  `{"choice":"besiege","surprise":true}` variant when S1 is held and eligible;
  optionally add `storm_decisions` for the immediate Storm. If the Stronghold
  is owed a Themata assignment, that pends FIRST (S1 Clarification) and the
  2 Siege markers + Storm resume after it.
- **Loyalty coin DRMs** (1.4.1). `resolve_loyalty` / `discard_imperial_coffers`
  accept `"coins_for"` (revealing player, +1 each) and `"coins_against"` (that
  player's opponent, -1 each), bounded by the `_max_coins_for` /
  `_max_coins_against` hints (Commander + co-located Unbesieged Lords' Coin;
  no resisting for a Besieged target). The opponent pays even when the target
  already belongs to the revealing player. Amounts must be nonnegative JSON
  integers: strings, fractions, booleans, and negative values are rejected.
  Both payments are validated before any Coin or dice are consumed. Invalid
  Imperial Coffers payments also leave its card and pending decision intact.
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
| `capability_discard` | `{"type":"capability_discard","side":SIDE,"card":CARD}`; choose a board-edge Capability from the menu (4.0) |
| `grow` | `{"type":"grow","side":SIDE,"locale":LOCALE}`; choose an enemy Ravaged marker to remove in Spring (4.7.2) |
| `reset_discard` | `{"type":"reset_discard","side":SIDE,"card":CARD,"lord":LORD_IF_ON_MAT}` to return a card, or `{"type":"reset_done","side":SIDE}` to keep the rest (4.7.5) |
| `deploy_capability` | `{"type":"deploy_capability","card":C,"lord":L}` (L from `eligible`) |
| `event_pending_resolution` | `{"type":"resolve_event","card":C,"args":{...}}` |
| `wastage` | `{"type":"wastage","lord":L,"discard":{"asset":"loot"}}` or `{"discard":{"card":C}}` with the same `type` and `lord` |
| `wastage_target` | `{"type":"wastage_target","raider":L,"target":ENEMY_LORD}` (R22/S22) |
| `approach_response` | `{"type":"respond_approach","choices":{LORD:{"action":"stand"\|"withdraw"\|"avoid","to":LOCALE}}}` |
| `besiege_or_bypass` | `{"type":"besiege_bypass","choice":"besiege"\|"bypass"}` |
| `assign_themata_defenders` | `{"type":"assign_themata_defenders","markers":[...]}` |
| `ravage_defence` | `{"type":"resolve_ravage_defence","defend_with":INDEX_or_null}` |
| `loyalty_check` | `{"type":"resolve_loyalty","target":LORD}` (from `targets`; optional `coins_for`/`coins_against`, see hints) |
| `basil_response` | `{"type":"basil_response","play":true\|false}` |
| `retain_themata` | `{"type":"retain_themata","lord":L,"thema":THEMA,"mode":"pay"}`; or `"return"`, or `"pressed_levy"` when offered (4.7.5/R4) |
| `winter_quarters` | `{"type":"winter_quarters","lord":L,"dest":SEAT}` or `{"lord":L,"stay":true}` (R15/S15; options in the pending's `dests`/`may_stay`) |

Before Planning, Seljuk then Roman players must discard board-edge Capabilities
exceeding their number of Mustered Lords (4.0). Choose one card at a time from
the complete `capability_discard` menu until the required number is returned.
This Lord Capabilities and Held Events do not count toward this limit and
cannot be selected here. Planning begins after both sides finish. The current
owner, remaining quota and choices survive save/load.

At a non-final Spring Campaign's end, Grow pauses for Seljuk then Roman to
remove enemy Ravaged markers. Choose one Locale per `grow` action until the
displayed quota is met. Each side leaves half the enemy's original total,
rounded up; the quota stays fixed during selection. VP totals update after
each removal. Repair, Wastage and Reset follow both players' choices. A side
with zero or one enemy marker has no removal to select.

After Themata retention, unstacking and mandatory seasonal-card cleanup, Reset
lets Seljuk then Roman return any of their Held Events, board-edge Capabilities
and This Lord Capabilities. Select one `reset_discard` at a time, or select
`reset_done` to keep every remaining card. There is no minimum discard; all
subsets remain available. The menu identifies a mat card's Lord. Special-Vassal
card discards also Disband that Vassal and can Disband a Lord left without
Forces. Themata retention does not repeat when cards are discarded. The choices
survive save/load, and Winter or the next Levy waits until both players finish.

Battles, Storms, and Sallies are **auto-resolved** by the engine when you Stand
(or Storm/Sally); the result is returned by `do`. You don't roll dice — the
seeded RNG in the save file does, deterministically. Typed `battle_decisions`
(and `storm_decisions`) accept JSON arrays, for example `[["concede", true]]`.
In Battle and Sally, the attacker may Concede from Round 1. The defender
gets the choice if the attacker fights on. Both sides still fight that
round, with Pursuit, before the concession ends combat. To Concede in a
later round, put a `["concede", false]` in your queue for each earlier
round. A shared script needs both sides' declines. In Storm the attacker
first gets the choice in Round 2.
Tuple-valued choices use a nested array, such as
`[["retreat", ["retreat", "ani"]]]`, subject to the offered destinations.

For Parthian Shot in Battle or Garrison Missiles in Storm, the receiving
player chooses the affected Lord where applicable, then the striker uses
`["select_target_unit", "unit_id"]` for each choice among eligible units.
The Storm attacker must assign Hits to Armored units first, including
Turkic Horse with active Lamellar Armor. Unscripted Select Target choices
use the weakest eligible protection.

For ordinary Hits, the receiving player uses `["hit_absorption", "unit_id"]`.
This also chooses among live Storm Garrison unit types, even when no defending
Lord is present. Garrison units must absorb before any defending Lord. New
Garrison choices accept typed entries and leave legacy bare Lord choices queued.

An Armor penalty reduces active Lamellar Armor, including against Missiles.
In field Melee, Turkic Horse with Lamellar may instead Evade without the Armor
penalty. When these ranges differ, the owner can choose
`["protection_type", "evade"]` (the default) or `["protection_type", "armor"]`
before each roll. Evade is unavailable against Missiles and in Storm.

Non-Garrison Roman Militia have Missile Strikes only while Psiloi (R25) is in
play at the board edge. Garrison Militia retain their own Missile Strikes.

Norman Heavy Cavalry allows one failed Armor reroll against Missiles and one
against either Horse or Foot Melee per Lord per Round. Use
`["norman_reroll", false]` to decline a reroll and keep that allowance
for a later Hit in the same phase. The default is to use it.

In Storm and Sally, the defending player can use
`["initial_placement_defender", "lord_id"]` to choose the initial Front Lord.
Use the defender's private `storm_decisions` or `battle_decisions` input,
respectively. From Round 2, `["reserve_advance", "lord_id"]` advances one
Reserve Lord within the Stronghold's Size. `["reserve_advance", null]`
keeps the Reserve back when the advance is optional. An empty Front
requires a replacement when Reserve remains. In Storm a side must also
match an open opposing Front position when it can during its advance.
Omitted choices use the first eligible Lord.

An `approach_response` is mandatory before another Command or ending the
activation, during both Campaign and Winter (4.3.4). Submit `respond_approach`
to resolve the defenders' Avoid, Withdraw or Stand choices. Local Scouts and
Battle Events remain inputs to that response. Direct commands that skip it
are rejected without changing the board, RNG or history. Resolve any resulting
Besiege/Bypass or Themata defender assignment before continuing.

A Sortie from a Bypassed Friendly Stronghold costs one March action and
opens the same Approach response (4.3.6). Use `group` on `cmd_sortie` to
select a Commander's allies from the offered `_co_marchers`. A Lieutenant
brings his Lower Lord automatically. The Bypassing player responds before
Battle. Supply combat inputs on `respond_approach`.

S11 Javelins fires in one Battle round per Battle, not every round and not in
Storm. Supply `"javelins_rounds": {"ibn_khan": 2}` on `respond_approach`,
or `cmd_sally` to mark round 2 for that Lord. The default is round 1.
The same syntax applies to `steeled_rounds` for R3 Steeled Resolve.

At a non-final Campaign Reset, the Roman player may retain all of a Thema's
Levied/Recruited units on a Lord's mat for **one Coin per Thema**, not per unit or
marker. Resolve each `retain_themata` pending before continuing. `pressed_levy`
is offered for R4's one free unpaid Thema; `return` declines retention. The save
file preserves these choices, including a partially completed Reset.

Returning a Commander's last Thema immediately Disbands the empty Lord to the
Calendar, using the current Turn plus his Service rating (1.6/3.3.2).
Discarding a Special-Vassal Capability also removes its Service marker and
provided units as able (3.4.2). If that leaves the Lord without Forces, he
Disbands too. During Campaign, either loss can end the game immediately if
that side has no Mustered Lords left; Reset and the next Turn then stop.

Wastage precedes Reset and pauses for the affected Lord's owner. Once a Lord
qualifies under 4.7.4, every positive Asset type and every This Lord Capability
on his mat is offered, including singleton Loot or a singleton card. Select
one complete action from the menu. The engine rechecks eligibility after
each occurrence of repeated Wastage. R1 Flooded River routes Alp Arslan's
choices to the Seljuk player, and S25 Mercenary Discipline routes each
affected Roman Lord's choices to the Roman player. Finish these choices
before the next drawn Event or normal play continues. Saves preserve the
pending owner and remaining occurrences.

For R22/S22, the raider's owner selects an adjacent Enemy Lord, then that
Lord's owner selects the discard if he still qualifies. All normal End
Campaign Wastage resolves before these additional occurrences and Themata
retention. Returned Capability cards go to their printed side's deck.

Lords Avoiding to the same destination share spare Carts. Each Lord uses
his own Carts first, then the group's spare capacity. Provender stays on its
original mat. Loot and excess Provender become the Approaching Lords'
Spoils. Carts are pooled only within the group that Avoids together.
The Approaching player can pass `avoid_spoils_decisions` on a trusted
`respond_approach` action or in the compact input window. For each Asset in
order (Loot, then Provender), use `["spoils_recipient", LORD]` followed by
`["spoils_amount", COUNT]`. Repeat to split the pool. The compact window
shows the final pool and room on eligible mats after any Local Scouts
decision. Omitted choices fill the first eligible mats with room, up to
eight of each Asset per Lord. The receipt shows any excess lost to that cap.
Use `battle_decisions` for a Battle that follows. In a response with no
Battle, `battle_decisions` can also supply the Avoid allocation when
`avoid_spoils_decisions` is omitted.

Themata `symbols` are the printed marker capacity. On a Lord's mat, optional
`strength` records surviving units and `routed` records its routed subset; a
missing/null strength means full printed strength. Human Lord/summary views
include the surviving Themata in Forces while displaying their marker identity.
Older saves without these fields remain loadable.

## Hidden information

`state --file game.json --side seljuk --json` returns the machine-readable game
state **filtered for that side**: the opponent's draw deck, held Events, and
unrevealed Plan cards are masked as `"<hidden>"`. Your own are fully visible, as
are the opponent's already-revealed Command cards. The filtered view exposes
only action types from replay history and omits the random seed/state; raw
history includes secret plans and is not a player-safe event log. Human and JSON state/briefing views default to the decision owner and honor
Hidden Mats. With Vassal Service (6.2) enabled, public Calendar markers appear
in the briefing and Calendar and Lord views. In filtered JSON and compact
inspection, look for `public_vassal_service` on Lords with markers. Each
entry gives the Vassal slot or special name and its Service box, including
off-edge positions. Hidden Mats masks the opponent's Vassals on the mat.
`history --raw`, raw save files, and direct render APIs without a viewing side
remain trusted omniscient debugging access.

## Winning

`is_over` is true when `phase == game_over`; the winner is in the status line and
in `winner`. Victory comes from VP (½ per Ruins/Ravaged, 1 per Roman-Conquered),
the Seljuk Unity track, or an Aleppo auto-victory — all scored by the engine.

---

## Mode A — Solo / single chat

One chat drives both sides (or plays one side and makes reasonable moves for the
other). Just run the turn loop; the `decision` side in the status line tells you
who owes the next input (not necessarily the active Command-card player). Nothing else to coordinate.

## Mode B — Head-to-head (two chats)

Two chats play a real game, one as **seljuk** and one as **roman**, sharing a
single save file in a folder both can read/write (e.g. the Cowork workspace).

Setup (either chat, once):
```bash
python -m seljuk.cli new <scenario> --out /path/to/shared/game.json
```

Each chat's turn protocol:
1. `briefing --file game.json` and read the status line. **Act only when
   `decision=` is your side.** The inactive defender can owe an immediate response.
2. View your own state: `state --file game.json --side YOUR_SIDE --json`.
3. Resolve `pending` decisions that are yours, then `legal-moves`, then `do`.
4. After your `do`, the status line shows whose turn is next. Hand off (the file
   is already saved).

Honor system: the harness does **not** stop a chat from reading the opponent's
filtered-out info or applying the opponent's moves. For a fair game, each chat
should only ever call `state --side ITS_OWN_SIDE`, only resolve pending
decisions owed by its side, and only `do` actions for its own Lords. The
`legal-moves` palette follows the actual decision owner. Do not send an
actor's private `do` result to the next decision owner. For enforced presentation
pins and staged joint decisions use the compact helper; the CLI is a trusted
low-level interface, not an authentication boundary.

For fair head-to-head play, keep private action results private: they can
contain a Plan or other hidden choices. `history` and unfiltered save files are
omniscient debugging/replay tools, not public turn logs. Use your side-filtered
state to review public information.

## Quick reference — common action types

You never need to memorise these (use `legal-moves`), but for orientation:
Levy: `pay`, `levy_lord`, `levy_vassal`, `levy_transport`, `levy_capability`,
`levy_themata`, `cta_loot`, `cta_strategic_objective`, `pass_step`.
Campaign: `build_plan`, `cmd_march`, `cmd_tax`, `cmd_forage`, `cmd_ravage`,
`cmd_supply`, `cmd_recruit`, `cmd_siege`, `cmd_storm`, `cmd_sally`, `cmd_pass`,
`end_activation`, `play_hold_event`, `winter_activate`, `winter_proceed`.

## Longest-scenario corrections (2026-10-10)

After an Approach Battle, resolve any `besiege_or_bypass` decision and subsequent
`assign_themata_defenders` decision before recovery. This applies in Winter as
well as normal Campaigns. Battle leaves no further Command actions, including
when Bypass is selected; `end_activation` cannot skip the mandatory decision.

The `build_plan` hint `_no_command_required` covers both Treachery's compulsory
opponent No Command and Unpredictable Weather. Supply at least one `no_command`
when it is true, within the displayed `_plan_size`.

This-Campaign cards return to their decks at Reset. S13 Peace Offering becomes
Gifts Exchanged in the Capability area; its Event effect is tracked by the
seasonal flag, not a second physical card in `this_campaign_events`.
