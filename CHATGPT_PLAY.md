# Playing Seljuk through the compact LLM interface

The rules engine makes rulings and rolls dice; the player supplies all choices.
The helper does not rank, prune, construct a Plan, or select a strategic policy.
Copy `src/` and `scripts/` into the sandbox; install `pydantic>=2`. Packaged
reference text is included, so inspection does not need a network or PDFs.

```python
import sys
sys.path[:0] = ["src", "scripts"]
import chatgpt_play_helper as nv
status = nv.start("manzikert", seed=1)
```

`show()` prints a briefing and counts by action category, not every action.
The useful existing public action-type summary and last-three-action history
remain. Each response identifies `viewer`, `decision_owner`, and `version`.
Use the **decision owner**, not merely the active Command-card player: the
inactive defender, Roman Themata allocator, and reaction-card holder can owe
an immediate decision. With `player=None`, one trusted operator routes both
sides. For a dedicated player context, use `player="roman"` or `"seljuk"`;
that context cannot inspect or apply the other player's menu.

## Browse before deciding

```python
page = nv.actions(type="cmd_march", lord="alp_arslan", limit=6)
# Review the rows, then inspect one of their ids:
# detail = nv.details(page["entries"][chosen_index]["id"])
# More rows: nv.actions(cursor=page["next_cursor"])
```

Filters `type`, `kind`, `lord`, `card`, `target`, and `to` match exactly; `q`
searches only player-visible text. `kind` is `"action"` or `"template"`.
Pages state their total, offset, remaining count, and `next_cursor`; follow the
cursor without changing query or page size. Default page size is 6, maximum
100. Every engine-validated row remains in the private menu in original order,
including duplicates and variants. Filtering/pagination do not choose which
options are worthwhile. Template rows retain `_unvalidated`: their supplied
parameters must still pass the engine. Validation is cached once per state.

`details(id)` preserves every visible engine hint and exposes optional fields,
handler help, reference locations, and applicable template constraints. Ready
rows with optional parameters are not mistaken for forced decisions. Group
March, for example, retains group membership and discard choices; group Carts
can change cost. The versioned flat-dictionary path below also accepts legal
combinations not represented by a default concrete row.

## Execute with a state-bound selection

```python
# Use an id copied from the current page, never a bare integer index:
# nv.apply(action_id)
# nv.apply(template_id, parameters={...})

# Advanced/manual combinations remain available, with an explicit version:
# nv.apply({"type":"cmd_march", "lord":"alp_arslan", "to":"ararat",
#           "way_type":"pass", "group":["arisighi"]}, version=status["version"])
```

Ids stay stable across filters and pages while the state is unchanged. They
and all cursors expire after a game action, a staged response, or an external
state edit. Stale submissions fail **before game-state mutation, dice, or
history changes**. Selected fixed fields cannot be silently overwritten by
`parameters`; construct a flat action explicitly for a different combination.
Rejected actions execute on discarded copies, never a partially modified game.

A response is printed once as complete JSON. Assign its return value to inspect
keys; the notebook representation does not echo the entire response again.

## Plans and templates are player decisions

```python
help_ = nv.plan_help()
# At the standard four-card opening of Manzikert, an explicit example is:
nv.plan(["alp_arslan", "sav_tekin", "no_command", "no_command"],
        version=help_["version"])
```

Use the displayed `constraints`, not a remembered hardcoded rule: exact Plan
size, physical Lord cards (maximum four each), required Treachery, compulsory
opponent No Command, Weather, and the applicable No Command cap (normally five;
six when the Treachery-added card applies). On-map Lords are identified for
convenience but do not exclude physically available off-map Command cards.
Optional `lieutenants` are explicit eligible, disjoint pairs. There is no
automatic Plan construction.

Other templates require `args` for immediate Events, a choice for **every**
defending Lord in an Approach, and explicit Themata marker indices (including
`[]` to decline). Details give Avoid destinations, shared withdrawal capacity,
all marker identities including double markers, and the relevant limits.
Full card text and the engine remain the authority for combinations.

## Multi-player inputs, without shared private hands

A Storm, Sally, Sortie, Approach response, Surprise, or Loyalty action can need
inputs from more than one player. The helper stages the first player's declared
action, then routes `supply_inputs`/`decline_inputs` to the other player before
committing dice or game effects. Inspect that response's `details(id)` even
when declining: its own held cards, constraints, and optional fields are there.

```python
# Response template examples (use the currently displayed id):
# nv.apply(response_id, parameters={"inputs":{"coins_against":1}})
# nv.apply(response_id, parameters={"inputs":{
#     "battle_events":{"roman":["R21"]},
#     "battle_decisions":[["concede", True]]}})
```

A player cannot submit the other side's cards, counterpayment, or scripted
choices. Per-player combat FIFOs are kept separate; neither replaces or answers
the other player's decisions. `battle_decisions`/`storm_decisions` retain typed
choices and the engine's existing fallback for unscripted internal choices.
Combat remains **atomic**, not a new per-strike interactive engine. Round
choices, events, and complete public combat traces remain obtainable.

Local Scouts is a three-stage interaction: the defenders choose Avoid, the
Roman attacker declares R18, then the avoiding side chooses the affected Lord
and Stand/Withdraw. Bad Omens may be declared without `args.order`: the Seljuk
player then inspects the two cards privately and explicitly chooses keep/swap.
After inspection or a mandatory Event response, it cannot be cancelled. An
explicit preselected Bad Omens order remains supported. `cancel_inputs` is a
recovery operation only if the underlying game was externally changed; ordinary
responses must be completed or explicitly declined when decline is legal.

## Results and intact inspection

`apply()` returns public outcomes, a page of consequential changes, the next
decision, and category counts. It does not repeat the full briefing or menu.
Follow `changes(cursor=...)` until `remaining` is zero, or request a specific
receipt with `result(receipt=N, full=True)`. Full decision results stay available
to their submitting player; public combat details are available to both. Secret
plans and event-granted intelligence do not become an opponent's turn log.

```python
nv.state()                              # structured root catalog
nv.state(path="/lords/alp_arslan/assets", full=True)
nv.pending(full=True)
nv.lookup_card("S1")                    # full data AND curated clarification
nv.lookup_lord("alp_arslan")            # full static data + filtered current mat
nv.map("ani")                           # all Ways + locale mechanics/markers
page = nv.map(limit=6)                  # all Locales, explicit pages
# nv.map(cursor=page["next_cursor"])
nv.result(path="/combat_detail", full=True)
nv.reference()                          # original-text catalog
page = nv.reference("rules", limit=40)
# nv.reference("rules", cursor=page["next_cursor"])
nv.reference("errata", full=True)
nv.implementation("cmd_march")          # optional full handler-source inspection
```

Structured catalogs name every expandable JSON-pointer path; retrieve that
path with the **same function**, or `full=True`. Card/Lord lookups default to
full; when requesting their paginated catalogs use `full=False` on subsequent
cursor calls too. No string, JSON object, card, or Way is character-sliced.
Reference pagination uses complete numbered lines; even a very long line is
returned intact. Full originals carry source paths and SHA-256 provenance.
`reference("decisions")` and `reference("errata")` remain accessible alongside
card text. Rebuild packaged references after source changes with
`python scripts/build_llm_references.py`.

## Saves, diagnostics, and the trust boundary

```python
nv.save("game.json")
nv.resume("game.json")
nv.findings_report(full=True)
```

Saves include state, staged inputs, ids/cursors, receipts, and diagnostics.
Unchanged save/resume preserves selections; later edits invalidate them. Old
raw/LLMSession/helper saves can be resumed, but old unversioned integer menu
indices do not gain authority. Dedicated-player saves retain their player pin.

Save bytes and Python internals are **trusted, omniscient** storage. Do not give
them to an opponent or treat this presentation layer as operating-system
access control. A trusted host may switch player contexts, but must deliver
each response only to its named viewer. Self-play in one chat is not independent
information isolation. Player-facing diagnostics give safe classifications;
complete private reproduction details remain in the save for trusted review.

`auto()` advances only a single concrete action with no optional parameters;
it never builds Plans or crosses an unacknowledged player-input handoff.

The legacy CLI remains an explicit full-palette/raw-action interface. Its
briefing, default state views, menus, and pending display use the decision
owner. `history` defaults to public action types; `history --raw` is an explicit
trusted-debug command. CLI `do` labels its result recipient on stderr because
that result may include private information; unlike the compact helper, it
assumes a trusted caller has already collected joint inputs.

## Reproducible output measurements

```bash
git worktree add /tmp/seljuk-interface-baseline 18d03047effb527dced80679cefcdd01341a2e9c
python scripts/benchmark_llm_interface.py \
  --baseline-root /tmp/seljuk-interface-baseline --output /tmp/interface-metrics
```

The benchmark replays fixed complete Manzikert and Showdown games, includes
navigation, template/Plan help, lookups, every result-change continuation, and
combat details. It checks unchanged results and positions, not just text size.
It reports actual UTF-8 bytes/characters, and exact `o200k_base` token counts
when optional `tiktoken` is installed; it never relabels characters as tokens.
Raw legacy output and separately counted completions of incomplete legacy
lookups are both reported. The reference executions are regression oracles,
not player strategy or new playtests. Transcripts combine both players and
must be treated as trusted test evidence.
