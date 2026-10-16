"""Compact ChatGPT sandbox play helper; all rules remain in the engine.

    status = nv.start("manzikert", seed=1)
    page = nv.actions(type="cmd_march", limit=6)
    help_ = nv.details(page["entries"][0]["id"])
    result = nv.apply(page["entries"][0]["id"], parameters={"group": [...]})

show() is an overview, NOT a full menu. actions() pages every validated option;
templates are explicitly labelled and require supplied parameters. Versioned
ids and cursors cannot be used after a state change. Direct actions are still
supported via apply({...}, version=status["version"]). No strategy pruning,
Plan construction, or opponent decision-making happens in this helper.

Return values contain exactly the printed public payload, not a hidden full
menu. Assign the return value for programmatic access. In notebooks the custom
representation avoids echoing the full payload a second time.
"""
from __future__ import annotations

import json
from seljuk import scenarios
from seljuk.llm import LLMSession
from seljuk.llm.compact import CompactInterface, InterfaceError
from seljuk.state import IllegalAction

SCENARIOS = list(scenarios.SCENARIOS)
_UI: CompactInterface | None = None
# Retained for trusted instrumentation, NOT for player-visible menu access.
_S = {"session": None, "scenario": None, "history": [], "findings": [], "turn": 0}


class DisplayResult(dict):
    def __repr__(self):
        return "<Seljuk response already printed; use its keys for programmatic access>"

    def _repr_pretty_(self, printer, cycle):
        printer.text("")


def _interface():
    if _UI is None:
        raise InterfaceError("no_game", "Call start(scenario) or resume(path) first.")
    return _UI


def _emit(payload):
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return DisplayResult(payload)


def _call(fn, *args, **kwargs):
    try:
        return _emit(fn(*args, **kwargs))
    except (InterfaceError, IllegalAction) as exc:
        # Input/stale errors do not trigger another full briefing or menu.
        return _emit({"error": getattr(exc, "code", type(exc).__name__), "message": str(exc),
                      "recovery": "show() refreshes the version; actions() and details(id) expose choices/constraints."})


def _active_side():
    return _interface().owed


def _menu(log_drops=True):
    """Trusted instrumentation only; public retrieval goes through actions()."""
    from copy import deepcopy
    return deepcopy(_interface()._menu())


def start(scenario, seed=1, *, options=None, player=None):
    """Start with explicit optional rules; player=None routes both sides.

    Pin player='roman' or 'seljuk' for a separate player context. A pinned
    player cannot fetch the opponent's menus or execute its decisions.
    """
    global _UI
    _UI = CompactInterface(LLMSession.start_new(scenario, seed, options=options), player)
    _S.update(session=_UI.session, scenario=scenario, history=[], findings=_UI.findings, turn=0)
    return show()


def show():
    """Compact briefing, current decision owner, categories and retrieval hints."""
    return _call(_interface().overview)


def actions(*, type=None, kind=None, lord=None, card=None, target=None, to=None,
            q=None, cursor=None, limit=None):
    """All validated rows are discoverable. Filters are exact, except q search.

    kind is 'action' or 'template'. Follow next_cursor without changing filters.
    IDs stay the same across filters/pages, but expire when the state changes.
    """
    return _call(_interface().actions, type=type, kind=kind, lord=lord, card=card,
                 target=target, to=to, q=q, cursor=cursor, limit=limit)


def details(action_id):
    """Complete action/template hints, optional parameters and decision contract."""
    return _call(_interface().details, action_id)


def apply(choice, *, parameters=None, version=None):
    """Use a versioned ID, or a flat action dict with an explicit version.

    Never defaults a template. Joint actions first route an input/decline window
    to the other player; only then does the unchanged engine resolve the action.
    """
    result = _call(_interface().apply, choice, parameters=parameters, version=version)
    _S["session"] = _interface().session
    _S["turn"] = len(_interface().gs.history)
    return result


def plan_help():
    return _call(_interface().plan_help)


def plan(cards, *, version, lieutenants=None):
    """Explicit ordered Plan plus optional Lieutenant pairs; engine validates."""
    return _call(_interface().plan, cards, version=version, lieutenants=lieutenants)


def auto(max_steps=300):
    """Advance only truly forced rows with no optional decisions; stop at handoff."""
    return _call(_interface().auto, max_steps=max_steps)


def state(*, path="", full=False, cursor=None, limit=None):
    """Filtered state catalog/subtree for the owed or pinned player.

    Example: state(path='/lords/alp_arslan/assets', full=True).
    Each expandable entry gives its path. No string or JSON is cut mid-field.
    """
    return _call(_interface().inspect, "state", path=path, full=full, cursor=cursor, limit=limit)


def pending(*, full=False, cursor=None, limit=None):
    return _call(_interface().inspect, "pending", full=full, cursor=cursor, limit=limit)


def lookup_card(card_id, *, path="", full=True, cursor=None, limit=None):
    """Full short data AND complete curated mechanics/clarifications by default."""
    return _call(_interface().inspect, "card", card_id, path=path, full=full, cursor=cursor, limit=limit)


def lookup_lord(lord_id, *, path="", full=True, cursor=None, limit=None):
    """Full static stats plus the current player-filtered mat, never clipped."""
    return _call(_interface().inspect, "lord", lord_id, path=path, full=full, cursor=cursor, limit=limit)


def map(locale=None, *, path="", full=False, cursor=None, limit=None):
    """Complete Way rows, paged by Locale; locale=X also includes its rules data."""
    return _call(_interface().inspect, "map", locale, path=path,
                 full=full or locale is not None and cursor is None, cursor=cursor, limit=limit)


def result(*, receipt=None, path="", full=False, cursor=None, limit=None):
    """Public outcomes and every visible state change; never raw private history."""
    return _call(_interface().inspect, "result", receipt, path=path, full=full, cursor=cursor, limit=limit)


def changes(cursor):
    return _call(_interface().changes, cursor)


def reference(source=None, *, start_line=1, limit=None, cursor=None, full=False):
    """Packaged original rules, card/Lord references, errata and adjudications."""
    return _call(_interface().reference, source, start_line=start_line, limit=limit, cursor=cursor, full=full)


def implementation(action_type):
    return _call(_interface().implementation, action_type)


def findings_report(*, full=False, cursor=None, limit=None):
    """Player-safe diagnostic classifications; full private records are saved."""
    return _call(_interface().inspect, "diagnostics", full=full, cursor=cursor, limit=limit)


def cancel_inputs(*, version):
    return _call(_interface().cancel_inputs, version=version)


def save(path="chatgpt_game.json"):
    return _call(_interface().save, path)


def resume(path="chatgpt_game.json", *, player=None):
    """Restore game, staged inputs, IDs/cursors, receipts and private diagnostics."""
    global _UI
    _UI = CompactInterface.load(path, player=player)
    _S.update(session=_UI.session, scenario=_UI.gs.meta.scenario, findings=_UI.findings,
              history=[], turn=len(_UI.gs.history))
    return show()
