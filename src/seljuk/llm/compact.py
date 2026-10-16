"""Versioned, lossless-on-demand player interface over LLMSession.

The entire validated engine palette is cached privately. Pages only organize
that palette; no strategy scoring, top-k cutoff or default Plan is permitted.
All public payloads can be printed once as complete JSON. Raw GameState saves
remain trusted/omniscient artifacts, not a player-visible inspection endpoint.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import hmac
import inspect
import json
from pathlib import Path
import secrets
from typing import Any

from .. import engine, scenarios, static_data as sd, map as gmap, events
from ..invariants import check_invariants
from ..state import GameState, IllegalAction
from . import briefing, contracts, reference, tools, view
from .routing import check_side, current_pending, decision_side, other, visible_pending
from .session import LLMSession


class InterfaceError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _strip(move):
    return {k: deepcopy(v) for k, v in move.items() if not k.startswith("_")}


def _diff(before, after, path=""):
    """Complete structured differences; strings and arrays are never sliced."""
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        changes = []
        for key in sorted(before.keys() | after.keys()):
            if path == "" and key == "history":
                continue
            child = path + "/" + str(key).replace("~", "~0").replace("/", "~1")
            if key not in before or key not in after:
                changes.append({"path": child, "before": before.get(key), "after": after.get(key)})
            else:
                changes.extend(_diff(before[key], after[key], child))
        return changes
    return [{"path": path, "before": deepcopy(before), "after": deepcopy(after)}]


class CompactInterface:
    """One session; ``player=None`` routes both sides, or pin a private player.

    Stable ids/cursors are opaque, salted and bound to exact state + UI version.
    A raw direct action is still available, but requires an explicit version.
    ``apply`` commits only after a successful engine run on a disposable copy.
    """
    def __init__(self, session: LLMSession, player: str | None = None):
        self.session = session
        self.player = check_side(player) if player is not None else None
        self._key = secrets.token_bytes(32)
        self._revision = 0
        self._fingerprint = None
        self._version = ""
        self._cached_menu = None
        self._cursors: dict[str, dict] = {}
        self._joint: dict | None = None
        self._receipts: list[dict] = []
        self.findings: list[dict] = []
        self._sync()

    @property
    def gs(self):
        return self.session.gs

    def _sync(self):
        raw = _json({"state": self.gs.model_dump(mode="json"), "joint": self._joint})
        fingerprint = hashlib.sha256(raw.encode()).hexdigest()
        if fingerprint != self._fingerprint:
            self._revision += 1
            self._fingerprint = fingerprint
            self._version = f"v{self._revision}-" + self._sign(fingerprint + str(self._revision))
            self._cached_menu = None
            self._cursors.clear()
        return self._version

    def _sign(self, value):
        return hmac.new(self._key, value.encode(), hashlib.sha256).hexdigest()[:16]

    @property
    def version(self):
        return self._sync()

    @property
    def owed(self):
        return self._joint["owed_by"] if self._joint else decision_side(self.gs)

    @property
    def viewer(self):
        return self.player or self.owed

    def _envelope(self):
        return {"version": self.version, "viewer": self.viewer, "decision_owner": self.owed}

    def _check_version(self, version):
        if version is None:
            raise InterfaceError("version_required", "Supply the displayed version, or a current action id.")
        if version != self.version:
            raise InterfaceError("stale_selection", "State changed. Call show() and retrieve current actions; nothing was applied.")

    def _check_turn(self):
        if self.viewer != self.owed:
            raise InterfaceError("not_your_decision", f"Decision belongs to {self.owed}; your view remains private.")

    def _menu(self):
        self._sync()
        if self._cached_menu is None:
            moves, drops = engine.validated_legal_moves(self.gs)
            self._cached_menu = deepcopy(moves)
            if not moves and not self.session.is_over():
                self.findings.append({"kind": "no_legal_moves", "version": self.version,
                                      "subphase": self.gs.meta.subphase, "side": decision_side(self.gs)})
            for drop in drops:
                self.findings.append({"kind": "over_enum_filtered", "version": self.version, **deepcopy(drop)})
        return self._cached_menu

    def _rows(self):
        if self.viewer != self.owed:
            return []
        if self._joint:
            rows = [{"type": "supply_inputs", "_unvalidated": True,
                     "_desc": "Supply your own inputs for the committed joint action"}]
            if not (self._joint.get("scouts_requested") or self._joint.get("bad_omens")):
                rows.append({"type": "decline_inputs", "_desc": "Explicitly decline additional inputs"})
            return rows
        return self._menu()

    def _row(self, index, move, detailed=False):
        public = (deepcopy(move) if self._joint else contracts.visible_move(self.gs, move, self.viewer))
        item = {"id": f"{self.version}:a{index}", "kind": "template" if move.get("_unvalidated") else "action",
                "action": _strip(public)}
        # All rule hints travel with their row, not just a lossy description.
        hints = {k: v for k, v in public.items() if k.startswith("_") and k != "_unvalidated"}
        if hints:
            item["hints"] = hints
        help_ = (self._input_contract() if move["type"] == "supply_inputs" else {"parameters": [], "meaning": "Explicitly decline additional inputs"}) if self._joint else contracts.contract(self.gs, public, self.viewer)
        if help_.get("parameters") or help_.get("required"):
            item["parameters_available"] = True
        if detailed:
            item["help"] = help_
        return item

    def _index(self, action_id):
        if not isinstance(action_id, str) or ":a" not in action_id:
            raise InterfaceError("action_id_required", "Use an action id from actions(); unversioned integer indices are not accepted.")
        version, number = action_id.rsplit(":a", 1)
        self._check_version(version)
        self._check_turn()
        if not number.isdigit() or int(number) >= len(self._rows()):
            raise InterfaceError("bad_action_id", "No such action in this version.")
        return int(number)

    def overview(self, include_briefing=True):
        rows = self._rows()
        groups = {}
        for row in rows:
            kind = "templates" if row.get("_unvalidated") else "actions"
            groups.setdefault(row["type"], {"actions": 0, "templates": 0})[kind] += 1
        out = {**self._envelope(), "phase": self.gs.meta.subphase or self.gs.meta.phase,
               "box": self.gs.meta.calendar_box, "actions_remaining": self.gs.meta.actions_remaining,
               "categories": groups, "menu_total": len(rows)}
        if self.session.is_over():
            out["game_over"] = {"winner": self.session.winner(), "reason": self.gs.meta.notes.get("win_reason"),
                                "vp": scenarios.score(self.gs)}
        if include_briefing:
            out["briefing"] = briefing.briefing(self.gs, self.viewer, moves=[], owner=self.owed)
        if self._joint:
            out["pending"] = self._public_joint()
        else:
            out["pending"] = visible_pending(self.gs, self.viewer)
        out["browse"] = ("actions(type=..., kind=..., cursor=...); details(id); state(path=...); lookup_card(id); plan_help()"
                         if include_briefing else "actions(type=...); details(id)")
        if not rows and not self.session.is_over() and self.viewer == self.owed:
            out["warning"] = "No legal actions; inspect pending() and diagnostics(). No decision skipped."
        return out

    @staticmethod
    def _limit(limit):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise InterfaceError("bad_limit", "limit must be an integer from 1 to 100.")
        return limit

    def _cursor(self, spec, offset, limit):
        spec = {**deepcopy(spec), "offset": offset, "limit": limit, "viewer": self.viewer}
        token = self.version + ":p" + self._sign(_json(spec))
        self._cursors[token] = spec
        return token

    def _read_cursor(self, cursor, source):
        if not isinstance(cursor, str) or ":p" not in cursor:
            raise InterfaceError("bad_cursor", "Use the opaque next_cursor from the preceding page.")
        self._check_version(cursor.split(":p", 1)[0])
        spec = self._cursors.get(cursor)
        if not spec or spec["source"] != source or spec["viewer"] != self.viewer:
            raise InterfaceError("bad_cursor", "Cursor belongs to another query, endpoint, or player.")
        return deepcopy(spec)

    def _page(self, entries, spec, offset=0, limit=6):
        self._limit(limit)
        end = min(offset + limit, len(entries))
        return {**self._envelope(), "total": len(entries), "offset": offset,
                "entries": deepcopy(entries[offset:end]), "remaining": len(entries)-end,
                "next_cursor": self._cursor(spec, end, limit) if end < len(entries) else None}

    def actions(self, *, type=None, kind=None, lord=None, card=None, target=None, to=None,
                q=None, cursor=None, limit=None):
        filters = {k: v for k, v in locals().copy().items()
                   if k in ("type", "kind", "lord", "card", "target", "to", "q") and v is not None}
        if kind is not None and kind not in ("action", "template"):
            raise InterfaceError("bad_filter", "kind must be 'action' or 'template'.")
        if any(not isinstance(v, str) for v in filters.values()):
            raise InterfaceError("bad_filter", "Filter values must be strings.")
        if cursor:
            spec = self._read_cursor(cursor, "actions")
            if filters and filters != spec["filters"]:
                raise InterfaceError("cursor_query_mismatch", "A cursor keeps its original filters; start a new query to change them.")
            if limit is not None and limit != spec["limit"]:
                raise InterfaceError("cursor_query_mismatch", "A cursor keeps its original page size.")
            filters, offset, limit = spec["filters"], spec["offset"], spec["limit"]
        else:
            offset, limit = 0, 6 if limit is None else limit
            spec = {"source": "actions", "filters": filters}
        rows = []
        for index, move in enumerate(self._rows()):
            row = self._row(index, move)
            payload = row["action"]
            if any((row["kind"] if k == "kind" else payload.get(k)) != v
                   for k, v in filters.items() if k != "q"):
                continue
            if "q" in filters and filters["q"].casefold() not in _json(row).casefold():
                continue
            rows.append(row)
        return {**self._page(rows, spec, offset, limit), "filters": filters}

    def details(self, action_id):
        index = self._index(action_id)
        return {**self._envelope(), **self._row(index, self._rows()[index], detailed=True)}

    def plan_help(self):
        for i, row in enumerate(self._rows()):
            if row["type"] == "build_plan":
                return self.details(f"{self.version}:a{i}")
        return {**self._envelope(), "message": "No Campaign Plan is owed by this player."}

    def plan(self, cards, *, version, lieutenants=None):
        self._check_version(version)
        row = next((m for m in self._rows() if m["type"] == "build_plan"), None)
        if not row:
            raise InterfaceError("no_plan", "No Campaign Plan is owed by this player.")
        action = {"type": "build_plan", "side": row["side"], "cards": deepcopy(cards)}
        if lieutenants is not None:
            action["lieutenants"] = deepcopy(lieutenants)
        return self.apply(action, version=version)

    def _document(self, source, key):
        if source == "state":
            return view.filtered_state(self.gs, self.viewer)
        if source == "pending":
            return self._public_joint() if self._joint else visible_pending(self.gs, self.viewer)
        if source == "card":
            return {**deepcopy(tools.lookup_card(key)), "reference_text": reference.card_text(key),
                    "authority": "Curated card reference; reference('errata') and reference('decisions') remain authoritative."}
        if source == "lord":
            return {"reference": deepcopy(tools.lookup_lord(key)),
                    "current": view.filtered_state(self.gs, self.viewer)["lords"][key],
                    "full_reference": "reference('lords'); reference('decisions')"}
        if source == "map":
            if key:
                return {**tools.lookup_locale(key), "ways": gmap.ways_from(key),
                        "current": view.filtered_state(self.gs, self.viewer)["locales"][key]}
            return {lid: gmap.ways_from(lid) for lid in sd.all_locale_ids()}
        if source == "result":
            index = len(self._receipts)-1 if key is None else int(key)
            if index < 0 or index >= len(self._receipts):
                return {"message": "No such completed action receipt."}
            return self._receipts[index][self.viewer]
        if source == "diagnostics":
            # Diagnostics can contain arbitrary private failing actions. Expose
            # only classifications; full reports are retained in trusted saves.
            return [{k: v for k, v in item.items() if k in ("kind", "version", "code")}
                    for item in self.findings]
        raise InterfaceError("bad_source", "Unknown inspection source.")

    @staticmethod
    def _node(document, path):
        if not isinstance(path, str) or (path and not path.startswith("/")):
            raise InterfaceError("bad_path", "Use a JSON pointer such as /lords/alp_arslan/assets, or '' for the root.")
        node = document
        for part in path.split("/")[1:]:
            key = part.replace("~1", "/").replace("~0", "~")
            try:
                node = node[int(key)] if isinstance(node, list) else node[key]
            except (KeyError, ValueError, IndexError, TypeError) as exc:
                raise InterfaceError("bad_path", "Path does not exist in this player's filtered document.") from exc
        return node

    def inspect(self, source="state", key=None, *, path="", full=False, cursor=None, limit=None):
        if cursor:
            spec = self._read_cursor(cursor, "inspect")
            if (source != spec["document"] or (key is not None and key != spec["key"])
                    or (path and path != spec["path"]) or full):
                raise InterfaceError("cursor_query_mismatch", "Use this cursor with its original inspection source.")
            if limit is not None and limit != spec["limit"]:
                raise InterfaceError("cursor_query_mismatch", "A cursor keeps its original page size.")
            key, path, offset, limit = spec["key"], spec["path"], spec["offset"], spec["limit"]
        else:
            offset, limit = 0, 6 if limit is None else limit
            spec = {"source": "inspect", "document": source, "key": key, "path": path}
        node = self._node(self._document(source, key), path)
        if full or not isinstance(node, (dict, list)):
            return {**self._envelope(), "source": source, "key": key, "path": path,
                    "data": deepcopy(node), "remaining": 0, "next_cursor": None}
        pairs = list(node.items()) if isinstance(node, dict) else list(enumerate(node))
        entries = []
        for name, value in pairs:
            child = path + "/" + str(name).replace("~", "~0").replace("/", "~1")
            # Scalar strings (even long ones) and per-locale ways are complete.
            expandable = isinstance(value, (dict, list)) and source not in ("map", "result", "diagnostics")
            entries.append({"key": name, "path": child,
                            **({"node_type": "object" if isinstance(value, dict) else "array",
                                "items": len(value), "retrieve": "inspect this path, or full=True"}
                               if expandable else {"value": deepcopy(value)})})
        return {**self._page(entries, spec, offset, limit), "source": source, "key": key,
                "path": path, "node_type": "object" if isinstance(node, dict) else "array",
                "expand": "Use path from any entry, or full=True for the complete selected subtree."}

    def reference(self, source=None, *, cursor=None, limit=None, start_line=1, full=False):
        if source is None:
            return {**self._envelope(), "sources": {k: {"path": v["path"], "lines": len(v["text"].splitlines())}
                                                     for k, v in reference.sources().items()},
                    "usage": "reference(source, start_line=1, limit=40); follow next_cursor; full=True retains all text."}
        if source not in reference.sources():
            raise InterfaceError("bad_source", "Unknown reference. Call reference() for the catalog.")
        data = reference.sources()[source]
        if cursor:
            self._read_cursor(cursor, "reference")
            if full:
                raise InterfaceError("cursor_query_mismatch", "Use full=True without a pagination cursor.")
        if full:
            return {**self._envelope(), "source": source, **deepcopy(data), "remaining": 0, "next_cursor": None}
        if cursor:
            spec = self._read_cursor(cursor, "reference")
            if spec["document"] != source or start_line != 1 or limit is not None and limit != spec["limit"]:
                raise InterfaceError("cursor_query_mismatch", "Follow the reference cursor without changing its source/range.")
            offset, limit = spec["offset"], spec["limit"]
        else:
            if isinstance(start_line, bool) or not isinstance(start_line, int) or start_line < 1:
                raise InterfaceError("bad_range", "start_line must be a positive integer.")
            offset, limit = start_line-1, 40 if limit is None else limit
            spec = {"source": "reference", "document": source}
        lines = data["text"].splitlines(keepends=True)
        if offset > len(lines):
            raise InterfaceError("bad_range", f"Reference has {len(lines)} lines.")
        return {**self._page([{"line": i+1, "text": s} for i, s in enumerate(lines)], spec, offset, limit),
                "source": source, "path": data["path"], "sha256": data["sha256"]}

    def implementation(self, action_type):
        """Optional complete engine handler source, not private runtime state."""
        table = {**engine._HANDLERS, **engine._CAMPAIGN_HANDLERS}
        if action_type not in table:
            raise InterfaceError("bad_action_type", "Unknown engine action type.")
        fn = table[action_type]
        return {**self._envelope(), "handler": fn.__name__, "source": inspect.getsource(fn),
                "note": "Implementation reference only; full rules/clarifications are in reference()."}

    # ---- application, receipts, and multi-player atomic inputs ----
    def apply(self, choice, *, parameters=None, version=None):
        if isinstance(choice, str):
            index = self._index(choice)
            move = self._rows()[index]
            action = _strip(move)
            if move.get("_unvalidated") and parameters is None:
                raise InterfaceError("template_parameters_required", "This is a template, not a ready action. Call details(id) and supply parameters.")
            if parameters is not None:
                if not isinstance(parameters, dict):
                    raise InterfaceError("bad_parameters", "parameters must be an object.")
                if any(k in action and action[k] != v for k, v in parameters.items()):
                    raise InterfaceError("fixed_parameters", "Parameters cannot silently change a selected action's fixed fields.")
                action.update(deepcopy(parameters))
            if version is not None:
                self._check_version(version)
        elif isinstance(choice, dict):
            self._check_version(version)
            self._check_turn()
            action = deepcopy(choice)
        else:
            raise InterfaceError("action_id_required", "Use a versioned action id, or a flat action dict with version=.")
        self._check_turn()
        if self._joint:
            return self._finish_inputs(action)
        if action.get("type") not in {m["type"] for m in self._rows()}:
            raise InterfaceError("not_offered", "This action type is not available at the current decision.")
        # Templates require explicit player input even where the engine's
        # legacy handler supplies an implicit stand/empty/default response.
        required = {"build_plan": "cards", "resolve_event": "args", "respond_approach": "choices",
                    "assign_themata_defenders": "markers"}.get(action.get("type"))
        if required and required not in action:
            raise InterfaceError("template_parameters_required", f"Supply {required} explicitly; details(id) gives the constraints.")
        if action.get("type") == "respond_approach":
            if not isinstance(action["choices"], dict) or set(action["choices"]) != set(current_pending(self.gs)["defenders"]):
                raise InterfaceError("incomplete_response", "Choose explicitly for each defending Lord; no default Stand is substituted.")
        actor = self.owed
        if action.get("type") == "play_hold_event" and action.get("card") == "S24":
            args = action.get("args") or {}
            if not isinstance(args, dict) or ("order" in args and args["order"] not in ("keep", "swap")):
                raise InterfaceError("bad_omens_order", "S24 order is 'keep' or 'swap'. Omit it to inspect before deciding.")
            if "order" not in args:
                probe_action = {**action, "args": {**args, "order": "keep"}}
                probe = LLMSession(GameState.from_json(self.gs.to_json()))
                inspected = probe.apply(probe_action)
                self._joint = {"action": probe_action, "actor": actor, "owed_by": actor,
                               "base_state": hashlib.sha256(self.gs.to_json().encode()).hexdigest(),
                               "bad_omens": True, "inspected": inspected.get("kept", [])}
                self._sync()
                return {"accepted": "Bad Omens declared; inspect and explicitly choose order",
                        **self.overview(include_briefing=False)}
        self._scope_scripts(action, actor)
        self._validate_owned_inputs(action, actor)
        if self._needs_inputs(action):
            # Rule validation on a copy before offering the opponent input;
            # never reveal or commit any speculative dice/results.
            probe = LLMSession(GameState.from_json(self.gs.to_json()))
            probe.apply(action)
            self._joint = {"action": action, "actor": actor, "owed_by": other(actor),
                           "base_state": hashlib.sha256(self.gs.to_json().encode()).hexdigest()}
            self._sync()
            return {"accepted": "awaiting_opponent_inputs", **self.overview(include_briefing=False)}
        return self._execute(action, actor)

    @staticmethod
    def _needs_inputs(action):
        kind = action["type"]
        if kind in ("resolve_loyalty", "discard_imperial_coffers", "cmd_storm", "cmd_sally", "cmd_sortie"):
            return True
        if kind == "besiege_bypass" and action.get("surprise"):
            return True
        if kind == "respond_approach":
            # Local Scouts may affect Avoid even without a proposed Stand.
            return True
        return False

    @staticmethod
    def _scope_scripts(action, actor):
        for key in ("battle_decisions", "storm_decisions"):
            if key in action:
                if isinstance(action[key], list):
                    action[key] = {actor: action[key]}
                if not isinstance(action[key], dict) or set(action[key]) - {actor}:
                    raise InterfaceError("opponent_input", "Supply only your own combat script; the other player has a separate queue.")

    def _validate_owned_inputs(self, action, actor):
        if "battle_events" in action:
            if not isinstance(action["battle_events"], dict) or any(s != actor for s in action["battle_events"]):
                raise InterfaceError("opponent_input", "Supply only your own battle_events; the opponent receives an input window.")
        for key in ("steeled_rounds", "javelins_rounds"):
            if key in action and (not isinstance(action[key], dict) or any(
                    lid not in self.gs.lords or self.gs.lords[lid].side != actor for lid in action[key])):
                raise InterfaceError("opponent_input", f"{key} declarations must refer to your own Lords.")
        if action.get("coins_against", 0) != 0:
            raise InterfaceError("opponent_input", "The opponent supplies coins_against in its own input window.")
        if action.get("play_sultans_horse") and actor != "roman":
            raise InterfaceError("opponent_input", "The Roman player chooses whether to play Sultan's Horse.")
        if action.get("local_scouts") and action.get("type") == "respond_approach":
            raise InterfaceError("opponent_input", "The Approaching player supplies Local Scouts in its input window.")

    def _public_joint(self):
        j = self._joint
        if not j:
            return None
        # Committed primary decision is public; unrevealed events and chosen
        # round declarations remain private until the engine resolves combat.
        public = {k: deepcopy(v) for k, v in j["action"].items()
                  if k in ("type", "lord", "target", "choices", "coins_for")}
        out = {"type": "joint_inputs", "owed_by": j["owed_by"], "committed_action": public,
               "resolution": "No dice committed yet; supply inputs. A decline is offered only when optional."}
        if j.get("bad_omens") and self.viewer == j["actor"]:
            out["inspected_roman_plan_cards"] = deepcopy(j["inspected"])
            out["requirement"] = "Play is declared; order must be chosen before any other action. Cannot cancel after inspection."
        return out

    def _input_contract(self):
        action = self._joint["action"]
        kind = action["type"]
        if self._joint.get("bad_omens"):
            return {"required": {"inputs": "{order: keep or swap}"},
                    "choices": ["keep", "swap"], "card_lookup": "S24"}
        if self._joint.get("scouts_requested"):
            return {"required": {"inputs": "local_scouts: {lord: one of your Avoiding Lords, action: stand or withdraw}"},
                    "avoiding_lords": [lid for lid, ch in action["choices"].items() if ch.get("action") == "avoid"],
                    "notes": "R18 was played by the opponent. YOU select the Lord and Stand/Withdraw (R18); withdrawal capacity still applies."}
        if kind in ("resolve_loyalty", "discard_imperial_coffers"):
            from .. import actions
            _, budget = actions.loyalty_coin_budgets(self.gs, self._joint["actor"], action["target"])
            return {"required": {"inputs": "Object containing coins_against (nonnegative integer), or {} to decline"},
                    "max_coins_against": budget}
        from .. import battle
        allowed = {"R21", "S21"} if kind == "cmd_storm" else battle._BATTLE_HOLDS
        recognized = set(contracts.parameter_names(engine._handlers_for_phase(self.gs.meta.phase)[kind]))
        input_fields = [k for k in ("battle_events", "steeled_rounds", "javelins_rounds",
                                   "battle_decisions", "storm_decisions", "local_scouts", "play_sultans_horse")
                        if k in recognized and k != "local_scouts"]
        if kind == "respond_approach":
            input_fields.append("play_local_scouts")
        return {"required": {"inputs": "Object with your optional combat inputs, or {} to decline"},
                "your_held_events": (sorted(set(self.gs.side_decks(self.viewer).held_events) & allowed)
                                     if "battle_events" in recognized else []),
                "parameters": input_fields,
                "your_sultans_horse_held": self.viewer == "roman" and "R4" in self.gs.roman.held_events,
                "your_local_scouts_held": self.viewer == "roman" and "R18" in self.gs.roman.held_events,
                "script_contract": "Supply your own FIFO list. Per-player queues stay private and are dispatched only to that decision's owner; no overwrite or heuristic merge.",
                "notes": "Use only your own events and round declarations. Engine timing/eligibility still applies.",
                "references": ["battle", "guide", "cards", "decisions", "errata"]}

    def _finish_inputs(self, action):
        if action.get("type") not in ("supply_inputs", "decline_inputs"):
            raise InterfaceError("pending_inputs", "Supply or decline the owed inputs before another game action.")
        if self._joint["base_state"] != hashlib.sha256(self.gs.to_json().encode()).hexdigest():
            raise InterfaceError("stale_joint_action", "The underlying game changed. Cancel the staged action and choose again.")
        if (self._joint.get("scouts_requested") or self._joint.get("bad_omens")) and action["type"] == "decline_inputs":
            raise InterfaceError("required_response", "This declared Event requires an explicit choice; see details(id).")
        inputs = {} if action["type"] == "decline_inputs" else action.get("inputs")
        if not isinstance(inputs, dict):
            raise InterfaceError("bad_parameters", "Supply inputs as an object, including {} for an explicit decline.")
        inputs = deepcopy(inputs)
        combined = deepcopy(self._joint["action"])
        actor = self._joint["actor"]
        if self._joint.get("bad_omens"):
            if set(inputs) != {"order"} or inputs["order"] not in ("keep", "swap"):
                raise InterfaceError("bad_omens_order", "Supply inputs={order: keep or swap}.")
            combined["args"]["order"] = inputs["order"]
            return self._execute(combined, actor)
        if self._joint.get("scouts_requested"):
            selected = inputs.get("local_scouts")
            if (set(inputs) != {"local_scouts"} or not isinstance(selected, dict)
                    or combined["choices"].get(selected.get("lord"), {}).get("action") != "avoid"
                    or selected.get("action") not in ("stand", "withdraw")):
                raise InterfaceError("bad_scouts_response", "Choose one of your Avoiding Lords and either Stand or Withdraw.")
            combined["local_scouts"] = deepcopy(selected)
            return self._execute(combined, actor)
        loyalty = combined["type"] in ("resolve_loyalty", "discard_imperial_coffers")
        allowed = {"coins_against"} if loyalty else set(self._input_contract()["parameters"])
        if set(inputs) - allowed:
            raise InterfaceError("opponent_input", "Inputs contain a field not owned by this response.")
        if not loyalty:
            self._scope_scripts(inputs, self.owed)
            self._validate_owned_inputs(inputs, self.owed)
        scouts = inputs.pop("play_local_scouts", False)
        if scouts and (combined["type"] != "respond_approach" or self.owed != "roman"
                       or "R18" not in self.gs.roman.held_events
                       or not any(ch.get("action") == "avoid" for ch in combined.get("choices", {}).values())):
            raise InterfaceError("bad_scouts_play", "Local Scouts requires your held R18 and an enemy Avoiding Lord.")
        for key, value in inputs.items():
            if key in ("battle_events", "steeled_rounds", "javelins_rounds", "battle_decisions", "storm_decisions"):
                combined.setdefault(key, {}).update(deepcopy(value))
            else:
                combined[key] = deepcopy(value)
        if scouts:
            self._joint.update(action=combined, owed_by=actor, scouts_requested=True)
            self._sync()
            return {"accepted": "Local Scouts; enemy chooses Lord and response", **self.overview(include_briefing=False)}
        return self._execute(combined, actor)

    def cancel_inputs(self, *, version):
        """Recover an externally invalidated staged request; never veto a valid action."""
        self._check_version(version)
        self._check_turn()
        if not self._joint:
            raise InterfaceError("no_pending_inputs", "No staged action exists.")
        if self._joint["base_state"] == hashlib.sha256(self.gs.to_json().encode()).hexdigest():
            raise InterfaceError("required_response", "Complete or explicitly decline the owed inputs; recovery cancellation requires an externally changed game.")
        self._joint = None
        self._sync()
        return {"cancelled": "unexecuted joint request", **self.overview(include_briefing=False)}

    @staticmethod
    def _outcomes(result):
        # These are public resolutions, not arbitrary private replay payloads.
        allowed = {"natural", "modified", "fealty", "switched", "new_side", "target",
                   "surrender_roll", "threshold", "seized", "siegeworks_added", "conquered_by",
                   "ruined", "winner", "rounds", "no_op", "reason", "cost", "avoided", "withdrew", "standers"}
        out = {k: deepcopy(v) for k, v in result.items() if k in allowed}
        for key in ("battle", "storm", "sally", "loyalty", "conquer"):
            if isinstance(result.get(key), dict):
                out[key] = CompactInterface._outcomes(result[key])
        return out

    def _execute(self, action, actor):
        before = {s: view.filtered_state(self.gs, s) for s in ("roman", "seljuk")}
        # Atomic interface boundary, not a change to rules or the dispatcher.
        trial = LLMSession(GameState.from_json(self.gs.to_json()))
        try:
            result = trial.apply(action)
        except IllegalAction:
            raise
        except Exception as exc:
            self.findings.append({"kind": "exception", "version": self.version,
                                  "exception_type": type(exc).__name__, "action": deepcopy(action)})
            raise
        self.session.gs = trial.gs
        self._joint = None
        self._sync()
        outcomes = self._outcomes(result)
        receipts = {}
        for side in ("roman", "seljuk"):
            changes = _diff(before[side], view.filtered_state(self.gs, side))
            combat = {k: deepcopy(v) for k, v in result.items()
                      if k in ("battle", "storm", "sally") and isinstance(v, dict)}
            receipts[side] = {"action": action["type"], "actor": actor, "outcome": deepcopy(outcomes),
                              "changes": changes, "combat_detail": combat,
                              "decision_result": deepcopy(result) if side == actor else {"private_to": actor},
                              "detail_policy": "Full decision result is available to its actor; combat details are public. Other private history remains in the trusted save."}
        self._receipts.append(receipts)
        try:
            violations = check_invariants(self.gs) or []
        except Exception as exc:
            self.findings.append({"kind": "invariant_crash", "version": self.version,
                                  "exception_type": type(exc).__name__, "message": str(exc)})
            violations = []
        for item in violations:
            self.findings.append({"kind": "invariant", "version": self.version, "violation": str(item)})
        receipt = receipts[self.viewer]
        consequential = []
        for change in receipt["changes"]:
            path = change["path"]
            if path.endswith("/draw_deck"):
                # Preserve full ordering in detailed results, but report only
                # movement/count by default rather than repeating shuffled decks.
                a, b = change["before"], change["after"]
                if Counter(a) != Counter(b):
                    consequential.append({"path": path, "removed": list((Counter(a)-Counter(b)).elements()),
                                          "added": list((Counter(b)-Counter(a)).elements())})
            elif not path.endswith("/plan_pointer"):
                consequential.append(change)
        # Never drop change detail: the summary is paged, with an explicit
        # remainder and a full receipt available via inspect('result', full=True).
        page = self._page(consequential, {"source": "changes", "receipt": len(self._receipts)-1}, limit=6)
        # The surrounding receipt already carries this exact envelope. Keep
        # independent continuation pages self-identifying, not repeated here.
        for key in ("version", "viewer", "decision_owner"):
            page.pop(key)
        if page["next_cursor"]:
            page["continue_with"] = "changes(cursor=next_cursor)"
        information = ({k: deepcopy(result[k]) for k in ("kept", "reordered") if k in result}
                       if self.viewer == actor else {})
        return {"applied": action["type"], "actor": actor, "outcome": outcomes,
                **({"private_information": information} if information else {}), "changes": page, "receipt": len(self._receipts)-1,
                "detail": "result(receipt=N, full=True)",
                **self.overview(include_briefing=False)}

    def changes(self, cursor):
        spec = self._read_cursor(cursor, "changes")
        # Reconstruct exactly the same summary as the first page.
        receipt = self._receipts[spec["receipt"]][self.viewer]
        entries = []
        for c in receipt["changes"]:
            if c["path"].endswith("/draw_deck"):
                a, b = Counter(c["before"]), Counter(c["after"])
                if a != b:
                    entries.append({"path": c["path"], "removed": list((a-b).elements()), "added": list((b-a).elements())})
            elif not c["path"].endswith("/plan_pointer"):
                entries.append(c)
        return self._page(entries, spec, spec["offset"], spec["limit"])

    def auto(self, max_steps=300):
        """Only truly forced rows without optional input; never build a Plan.

        Stops at a handoff (including virtual joint inputs), so the other player
        explicitly receives its briefing and access to all its choices.
        """
        if isinstance(max_steps, bool) or not isinstance(max_steps, int) or max_steps < 0:
            raise InterfaceError("bad_limit", "max_steps must be a nonnegative integer.")
        count, owner, reports = 0, self.owed, []
        while count < max_steps and not self.session.is_over() and self.owed == owner and not self._joint:
            rows = self._rows()
            if len(rows) != 1 or rows[0].get("_unvalidated"):
                break
            help_ = contracts.contract(self.gs, rows[0], self.viewer)
            if help_.get("parameters") or self._needs_inputs(_strip(rows[0])):
                break
            res = self.apply(f"{self.version}:a0")
            reports.append({"action": res["applied"], "outcome": res["outcome"], "receipt": res["receipt"]})
            count += 1
        return {"auto_advanced": count, "receipts": reports, **self.overview()}

    def save(self, path):
        self._sync()
        data = {"format": "seljuk-compact-v1", "state_json": self.gs.to_json(),
                "player": self.player, "key": self._key.hex(), "revision": self._revision,
                "fingerprint": self._fingerprint, "version": self.version,
                "joint": self._joint, "cursors": self._cursors,
                "receipts": self._receipts, "findings": self.findings}
        Path(path).write_text(_json(data), encoding="utf-8")
        return {**self._envelope(), "saved": str(path), "warning": "Trusted omniscient save; do not expose its bytes to an opponent."}

    @classmethod
    def load(cls, path, player=None):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        # Old helper saves and plain LLMSession saves are still resumable; their
        # unversioned menu indices deliberately gain no new authority.
        gs = GameState.from_json(data.get("state_json", _json(data)))
        obj = cls(LLMSession(gs), player if player is not None else data.get("player"))
        if data.get("format") == "seljuk-compact-v1":
            obj._key = bytes.fromhex(data["key"])
            obj._revision, obj._fingerprint, obj._version = data["revision"], data["fingerprint"], data["version"]
            obj._joint, obj._cursors = data["joint"], data["cursors"]
            obj._receipts, obj.findings = data["receipts"], data["findings"]
            obj._sync()
        return obj
