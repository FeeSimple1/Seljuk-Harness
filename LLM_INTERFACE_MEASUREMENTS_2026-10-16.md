# End-to-end LLM output measurements

Implementation commit: `36cb5a053b7c357ddeeb08a48913c21d45c9ab04`.
Exact tested source tree: `6ddd4abd055f8114f57b07304aa3af9db89e8e85`.
Untouched comparison baseline: `18d03047effb527dced80679cefcdd01341a2e9c`.
GitHub verification run: **38863606661**, completed successfully.

## Exact output tokens

Each actual printed response is encoded separately with `tiktoken`'s
`o200k_base`. These are output counts for this encoding, not estimates from
characters, billed context/input tokens, or model reasoning tokens.

| Complete sequence | Accepted game actions | Legacy output tokens | Compact output tokens | Reduction |
|---|---:|---:|---:|---:|
| Manzikert | 132 | 162,030 | 109,934 | 32.2% |
| Showdown in Anatolia | 338 | 357,045 | 221,838 | 37.9% |
| Combined | 470 | 519,075 | 331,772 | 36.1% |

The workload includes every requested action retrieval/continuation page,
explicit Plan help, optional/template details, opposing-player input/decline
handoff, consequential-change continuation, and requested card/Lord/state/map/
reference inspection. Public combat detail is included. Two Group March
parameter combinations include full handler-source inspection and versioned
flat submission. No private returned-but-unprinted payload is treated as a free
LLM lookup. All 470 action results and position states match direct-engine
controls; these are replay checks, not new strategic games.

Legacy calls: 177 and 420. Compact calls: 445 and 992. Navigation uses more
responses, but their combined output is smaller. Complete mechanics, Plan
constraints, and opponent-owned decisions deliberately remain longer wherever
needed. This measurement does not promise a universal saving for all strategies,
lookup patterns, tokenizers, or context-management schemes.

## Conservative comparison with incomplete legacy lookups

The headline compares against the smaller unmodified legacy output even though
some legacy lookups are character-clipped. Separately completing those lookups
raises the legacy totals to **167,037** and **366,150** tokens. The compact
outputs are already complete or explicitly paginated; no comparable repair is
necessary. Character and UTF-8 totals reproduced the local report exactly:

- Manzikert: 472,714 -> 359,650 characters; 473,186 -> 359,758 bytes.
- Showdown: 1,049,926 -> 733,443 characters; 1,050,756 -> 733,590 bytes.

## Independent validation and reproduction

The same GitHub run reconstructed the checksummed implementation, regenerated
its unabridged reference bundle, verified the exact tree/commit, and passed:

- **1,067 tests**, zero failures, errors, or skips: 989 existing cases (four
  helper tests adapted to the changed API) and 78 new interface cases.
- **25** clean scenario/seed legal-move sweeps.
- **30** aggressive smoke runs with zero findings.
- Both complete replay-output workloads above.

Only after these checks did it non-forcibly push the clean feature branch.
Temporary publication files remain on a separate branch and are not changes to
the implemented interface. This measurement report is a documentation-only
addition after the implementation was verified.

```bash
python -m pip install -e '.[dev]' tiktoken
git worktree add --detach /tmp/seljuk-interface-base 18d03047effb527dced80679cefcdd01341a2e9c
python scripts/benchmark_llm_interface.py --baseline-root /tmp/seljuk-interface-base --output /tmp/seljuk-interface-metrics
```

The `compact-interface-verification` artifact on run 38863606661 contains all
four complete transcripts, JSON summaries, test results, and tested source.
Artifact SHA-256: `c8533a4a998a282894ab1f04613d420af6a969bf503613310d80d3373f303efc`.
Transcripts combine two private player contexts for verification and are trusted
evidence, not material to send to a single opponent during play.

See `CHATGPT_PLAY.md` for the public API and `LLM_INTERFACE_2026-10-16.md` for
architecture, decision integrity, privacy, complete inspection, and scope limits.
