"""Nevsky advisory §2: the validated agent-facing palette probes each concrete
candidate on a discarded deep copy, drops handler-rejected (over-enumerated)
moves with a structured diagnostic, and never disturbs the real game's RNG."""
from seljuk import scenarios as S, engine
from seljuk.llm import LLMSession


def _campaign_command_state(seed=1):
    """Drive Manzikert to a campaign.command state with a real command menu."""
    s = LLMSession.start_new("manzikert", seed)
    s.apply({"type": "build_plan", "side": "seljuk",
             "cards": ["alp_arslan", "no_command", "no_command", "no_command"]})
    s.apply({"type": "build_plan", "side": "roman",
             "cards": ["romanos_diogenes", "no_command", "no_command", "no_command"]})
    return s


def test_validated_palette_drops_over_enumerated_move_and_logs(monkeypatch):
    s = _campaign_command_state()
    real = engine.legal_moves(s.gs)
    bogus = {"type": "cmd_march", "lord": "alp_arslan", "to": "ani", "way_type": "road",
             "_desc": "BOGUS non-adjacent march the handler must reject"}
    monkeypatch.setattr(engine, "legal_moves", lambda gs: list(real) + [bogus])
    moves = s.legal_actions(validated=True)
    assert bogus not in moves, "validator kept an over-enumerated move"
    assert any(d["action"]["type"] == "cmd_march" and d["action"]["to"] == "ani"
               for d in s.palette_diagnostics), "drop not logged as a diagnostic"
    assert s.palette_diagnostics[0]["code"]  # carries a machine-readable code


def test_validated_palette_keeps_legal_and_marks_templates():
    s = LLMSession.start_new("manzikert")  # campaign.plan -> only build_plan (a template)
    moves = s.legal_actions(validated=True)
    assert s.palette_diagnostics == []
    assert all(m.get("_unvalidated") for m in moves if m["type"] == "build_plan")
    # a real command menu: every concrete move survives validation (engine is clean)
    s2 = _campaign_command_state(seed=2)
    raw = [m for m in engine.legal_moves(s2.gs) if not m["type"]
           in engine._PALETTE_TEMPLATES]
    kept = s2.legal_actions(validated=True)
    assert s2.palette_diagnostics == [], s2.palette_diagnostics
    assert len([m for m in kept if not m.get("_unvalidated")]) == len(raw)


def test_validated_palette_does_not_consume_real_rng():
    s = _campaign_command_state()
    before = engine._save_roller  # noqa: ensure module import
    rng_before = list(s.gs.meta.rng_state) if s.gs.meta.rng_state else None
    s.legal_actions(validated=True)  # probes (e.g. Siege rolls) happen on copies
    assert (list(s.gs.meta.rng_state) if s.gs.meta.rng_state else None) == rng_before
