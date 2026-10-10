# Seed 20261012 regression checkpoints

From the recorded Emperor and the Lion game on `b1ace4bb`:
- `surrender-before.json`: before action 950, Artuk's Melitene Surrender.
- `loyalty-before.json`: before action 990, the Seljuk Treachery window.

Only the old `history` list is cleared to avoid duplicating hundreds of unrelated
turn records. Position, pending decisions, RNG state, and all other fields are
unchanged. The loyalty checkpoint therefore contains the earlier, already
missing Melitene markers; it is used to test payments, not marker conservation.
