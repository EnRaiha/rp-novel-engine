#!/usr/bin/env python3
"""OOC engine bridge — the seam the stateless harness calls (design §13).

The plugin owns what the engine cannot see (tool arguments before the model
speaks, the prompt slot); the engine owns what the plugin must not (the single
writable state, the rules, the economy). Exactly three calls cross the seam:

    {"call": "state", "session_id": 3}
    {"call": "turn",  "session_id": 3, "text": "…", "layer": "dialogue",
     "traits": ["aloof"], "context": {"scene": "medical"},
     "evidence_actions": [{"tool": "assign", "args": {"character_id": 20}}],
     "preview": false, "turn_ref": "turn-42"}
    {"call": "canon", "session_id": 3}

One JSON object in on stdin, one JSON object out on stdout. A failure is
reported as `{"ok": false, "error": …}` on stdout **and** a non-zero exit code,
never as a plausible default — a silent fallback here would corrupt the ledger.

Usage:
    echo '{"call":"state","session_id":3}' | python3 scripts/ooc_bridge.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from core import ooc  # noqa: E402
from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402

CALLS = ("state", "turn", "canon")


def _adopt_state_file(request: dict) -> None:
    """Mirror state to the file the caller's plugin reads (D7 phase 1).

    The plugin knows its own state path; the engine defaults to the TKG store, so
    a caller that keeps its state elsewhere must say so or the mirror lands in
    the wrong file.
    """
    path = request.get("state_file")
    if isinstance(path, str) and path.strip():
        os.environ["OOC_STATE_FILE"] = path.strip()


def _session(request: dict) -> int:
    """Session key for one request, defaulting to the configured campaign."""
    value = request.get("session_id")
    return int(value if value is not None else Config.SESSION_ID)


async def handle(request: dict) -> dict:
    """Answer one bridge request.

    @param request - parsed request object (`call` plus its arguments).
    @returns the reply object; `ok` is False when the call is unusable.
    """
    call = request.get("call")
    if call not in CALLS:
        return {"ok": False, "error": f"unknown call {call!r}; expected one of {', '.join(CALLS)}"}
    sid = _session(request)

    _adopt_state_file(request)
    if call == "state":
        return {"ok": True, "call": call, "state": await ooc.state(sid)}

    if call == "canon":
        observers = await ooc.suspicion(sid)
        return {
            "ok": True,
            "call": call,
            "session_id": sid,
            "companions": await ooc.companion_ids(sid),
            "observer_id": await ooc.observer_id(sid),
            "suspicion": [
                {"observer_id": row["observer_id"], "name": row["name"], "suspicion": row["suspicion"],
                 "last_reason": row["last_reason"]}
                for row in observers
            ],
            "milestones": [
                {"name": beat["name"], "trait": beat["trait"], "stage": beat["stage"],
                 "rpp_reward": beat["rpp_reward"], "completed": beat["completed_at"] is not None}
                for beat in await ooc.milestones(sid, traits=tuple(request.get("traits") or ("general",)))
            ],
        }

    _adopt_state_file(request)
    text = request.get("text")
    if not isinstance(text, str) or not text:
        return {"ok": False, "error": "turn needs a non-empty text"}
    actions = request.get("evidence_actions")
    layer = request.get("layer") or ooc.LAYER_DIALOGUE
    if layer == "tool" and not request.get("preview"):
        # The plugin already filtered which argument values count as prose (R2);
        # the engine audits the whole text it is handed on the tool surface.
        layer = ooc.LAYER_TOOL
    result = await ooc.audit(
        text,
        sid,
        layer=layer,
        traits=tuple(request.get("traits") or ("general",)),
        action_evidence=await ooc.evidence_from_actions(sid, actions),
        context=request.get("context"),
        turn_ref=request.get("turn_ref"),
        preview=bool(request.get("preview")),
    )
    result["call"] = call
    if not request.get("preview"):
        result["suspicion"] = [
            {"observer_id": row["observer_id"], "name": row["name"], "suspicion": row["suspicion"]}
            for row in await ooc.suspicion(sid)
        ]
        result["milestones"] = [
            beat["name"]
            for beat in await ooc.milestones(sid, traits=tuple(request.get("traits") or ("general",)),
                                             due_only=True)
        ]
    return result


async def main() -> int:
    """Read one request from stdin, answer it, and exit."""
    raw = sys.stdin.read()
    try:
        request = json.loads(raw or "{}")
    except json.JSONDecodeError as error:
        json.dump({"ok": False, "error": f"invalid JSON request: {error}"}, sys.stdout)
        sys.stdout.write("\n")
        return 2
    if not isinstance(request, dict):
        json.dump({"ok": False, "error": "request must be a JSON object"}, sys.stdout)
        sys.stdout.write("\n")
        return 2

    await Database.init()
    try:
        reply = await handle(request)
    except Exception as error:  # noqa: BLE001 — the seam reports, it never guesses
        reply = {"ok": False, "error": f"{type(error).__name__}: {error}"}
        code = 1
    else:
        code = 0 if reply.get("ok") else 1
    finally:
        await Database.close()
    json.dump(reply, sys.stdout, default=str)
    sys.stdout.write("\n")
    return code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
