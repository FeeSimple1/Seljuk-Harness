# Compact, decision-complete LLM interface

Base: `18d03047effb527dced80679cefcdd01341a2e9c`.

## Scope

The principal entry point remains `scripts/chatgpt_play_helper.py`. Its default
`show()` now combines the existing concise briefing and three-action recent
history with an action-category overview rather than expanding every legal
move. `apply()` reports outcomes, paginated consequential changes, and the new
decision owner/categories without repeating the full briefing or menu.

The adapter caches the entire engine-validated palette, including all hints and
parameterized templates. Exact filters and pages only organize that palette;
there is no scoring, strategic preference, top-k selection, or automatic Plan.
Concrete rows retain their complete fixed action fields. Optional parameters
remain discoverable through `details(id)`; full implementation and original
rules/reference text are also inspectable. Parameter combinations not represented
by a default concrete row retain the versioned flat-action submission path.

## Decision integrity and privacy

- Opaque stable action IDs and pagination cursors include the state version.
  Filters do not change row IDs. Advancing or externally changing the state,
  starting a new game, or moving to a staged decision invalidates old selections.
  Rejection leaves the game, dice, history and staged inputs unchanged.
- Plan templates explicitly expose ordered cards, physical Lord-card limits,
  No Command bounds, applicable Treachery/Weather requirements, and Lieutenant
  options. The engine and interface use the same Plan constraints. No cards,
  Lieutenant assignments, or responses are chosen by the adapter.
- Shared decision routing honors engine pending priority, inactive defenders,
  reaction holders, and repeated-event choice owners. Pinning a player gives
  waiting players only their own filtered view, not the opponent's menu.
- Joint loyalty/combat inputs are collected from the relevant player before
  resolution, including an explicit decline where optional. Own battle-event
  and round declarations cannot overwrite the other side's inputs. Local
  Scouts returns the forced response choice to the avoiding player. Bad Omens
  permits private inspection before the player chooses keep/swap and cannot be
  cancelled after inspection.
- Per-player combat-script queues dispatch only to decisions owned by that
  player. Legacy shared FIFO scripts still work unchanged for engine clients.
  Combat remains the existing atomic engine: unspecified internal decisions
  retain its documented fallback. This work does not claim a new interruptible,
  strike-by-strike combat protocol.
- Player views, briefings, inspection, and projected menus share the same hidden
  information policy. Opponent held events, unrevealed Plans, RNG state, raw
  replay history and Hidden Mats details do not leak through another display.
  Full actor-specific results and public combat results remain available as
  inspectable receipts. Raw save files and `history --raw` are explicitly
  trusted/omniscient, not player-visible channels.

## Complete inspection and persistence

State, Lord, card, map, pending and result inspection use complete structured
subtrees or pages with explicit counts, remaining entries, and continuation
cursors. No output is cut by a character budget. Scalars are complete even when
long. Card lookup includes the complete curated mechanics/clarification section.

Packaged `llm_references.json` contains the unabridged existing repository
reference sources and their byte checksums. `reference()` lists them; numbered
line pagination or `full=True` retrieves them. `scripts/build_llm_references.py`
regenerates this derived file without summarizing or changing its authorities.
It makes detailed reference inspection available in an installed offline package.

Trusted saves preserve the game, staged private choices, IDs/cursors, receipts
and diagnostics. Unchanged saves resume with the same tokens; older plain-state
and helper saves also remain loadable. Old unversioned integer selections gain
no authority in the new interface. `DisplayResult` avoids a second notebook
print of the same public payload; it never returns a hidden raw menu.

## Validation

Local full suite: **1,067 passed**, no failures, errors or skips. This comprises
all 989 existing cases (four helper tests adapted to the intentionally changed
public API) and **78 new interface cases**. No existing replay hashes changed.

Coverage includes all five scenarios and multiple seeds, both sides, complete
palette enumeration through all pages, exact filters, explicit Plan constraints,
pending reactions, save/resume, stale IDs/cursors, hidden information, long
lookup fields, full reference reconstruction, opposing script ownership, and
CLI view/history restrictions. Actual accepted game choices are replayed for:

- Manzikert: **132 actions**, Seljuk no-Lords victory; displayed VP 3.5-1.
- Showdown: **338 actions**, Roman final-scoring victory; displayed VP 14-1.5.

All action results and position fields, including RNG, match a direct engine
control after each action. Position comparison omits only the history encoding
of legacy shared scripts versus the equivalent separate player scripts. Tests
reload JSON after every action and perform complete UI save/resume repeatedly.
These are replay-based checks, not two new independent strategic playtests.

Existing legal-move sweep: **25 scenario/seed runs clean**. Existing aggressive
smoke checks: **30 runs, zero findings**. Existing unrelated Showdown rule defects
are intentionally not rewritten by this interface change; identical replay
results are not evidence that every inherited rule implementation is correct.

## End-to-end output measurement

`scripts/benchmark_llm_interface.py` imports an **untouched baseline checkout**
in a separate process. It captures actual helper stdout for the complete 132-
and 338-action sequences. It counts every action retrieval page, explicit Plan
help, optional/template detail request, owner handoff, input/decline response,
result-change continuation page, and requested state/Lord/map/card/reference
inspection. It includes detailed combat results and two complete handler
lookups for legacy Group March parameter combinations. No returned-but-unprinted
private payload is counted as a free player-visible lookup.

Exact local measurements (tokenizer not installed locally; no character/4
estimate is substituted):

| Workload | Legacy printed chars | New printed chars | Reduction | Legacy calls | New calls |
|---|---:|---:|---:|---:|---:|
| Manzikert (132 actions) | 472,714 | 359,650 | 23.9% | 177 | 445 |
| Showdown (338 actions) | 1,049,926 | 733,443 | 30.1% | 420 | 992 |

UTF-8 bytes respectively: **473,186 -> 359,758**, and **1,050,756 -> 733,590**.
The old clipped/incomplete lookups also receive a separately reported repair
baseline, not a concealed benefit: completing those requests yields 489,612
and 1,082,841 legacy characters. The headline comparison above conservatively
uses the smaller original output, despite its missing/clipped information.

Some output deliberately grows: complete cards/Lords/maps, full Plan constraints,
and explicit opponent choices are longer than old partial or implicit results.
Navigation also increases the number of responses. Total output shrinks through
reduced repeated menus and envelopes, not by discarding these decisions or
inspections. The workload is reproducible rather than a claim of a universal
saving for every strategy or lookup pattern.

Installing the optional `tiktoken` benchmark dependency adds exact per-response
`o200k_base` token counts to the same JSON report. These are encoding-specific
output counts, not billed input/context or reasoning tokens, and are not a claim
that every model uses that encoding. Transcripts combine both player contexts
for testing and should be kept trusted.

```bash
python -m pytest -q
PYTHONPATH=src python scripts/roundtrip_sweep.py --seeds 1,2,3,4,5
PYTHONPATH=src python scripts/smoke_fuzz.py --rounds 2 --seeds 1,2,3
git worktree add --detach /tmp/seljuk-interface-base 18d03047effb527dced80679cefcdd01341a2e9c
python scripts/benchmark_llm_interface.py --baseline-root /tmp/seljuk-interface-base --output /tmp/seljuk-interface-metrics
```

The complete public helper guide is `CHATGPT_PLAY.md`.
