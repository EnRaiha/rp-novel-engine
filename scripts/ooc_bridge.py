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


def _load_env_file() -> None:
    """Load `~/.env` when the caller's process carries no engine PG config.

    The harness spawns the bridge without the shell's exports. Without this the
    bridge fails every call and the plugin falls back to a local, file-only
    audit — a silent divergence from the ledger. Only `OC_PG_*` keys are read,
    and never over an existing value: the same source the CLI uses, no second
    source of truth.
    """
    if os.environ.get("OC_PG_HOST"):
        return
    path = os.path.join(os.path.expanduser("~"), ".env")
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, value = line.partition("=")
            if not sep:
                continue
            key = key.removeprefix("export ").strip()
            if key.startswith("OC_PG_") and key not in os.environ:
                os.environ[key] = value.strip().strip("'\"")


_load_env_file()

from core import ooc  # noqa: E402
from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402
from core.session import resolve_session

CALLS = ("state", "turn", "canon", "portrait", "context", "persona", "inspect", "direct", "slaves")


async def _adopt_state_file(request: dict) -> None:
    """Mirror state to the file the caller's plugin reads (D7 phase 1).

    The plugin knows its own state path; the engine defaults to the TKG store, so
    a caller that keeps its state elsewhere must say so or the mirror lands in
    the wrong file.
    """
    path = request.get("state_file")
    if isinstance(path, str) and path.strip():
        os.environ["OOC_STATE_FILE"] = path.strip()
    await _write_context_mirror(_session(request), request)


def _context_files(request: dict) -> tuple[str, str] | None:
    """Mirror paths for the story brief and the memory blocks.

    The harness plugin reads files synchronously: an async seam call races the
    first prompt build, so the engine writes these two files on every call and
    the plugin starts warm. `context_file` names the memory file; the story file
    sits beside it.
    """
    explicit = request.get("context_file")
    state_path = request.get("state_file") or os.environ.get("OOC_STATE_FILE")
    base = explicit or state_path
    if not isinstance(base, str) or not base.strip():
        return None
    path = os.path.abspath(base.strip())
    root, _, name = path.rpartition(os.sep)
    stem = name.rsplit(".", 1)[0] or "tkg-state"
    story = os.path.join(root, f"{stem}-story.md")
    if explicit:
        return story, path
    context = os.path.join(root, f"{stem}-context.txt")
    return story, context


async def _write_context_mirror(session_id: int, request: dict) -> None:
    """Best-effort: never fail a call because the mirror could not be written."""
    files = _context_files(request)
    if files is None:
        return
    story_path, context_path = files
    try:
        from core import context as context_layer

        # No event queries here: the mirror only needs the story brief and the
        # blocks the plugin injects, not a fresh chronicle scan on every write.
        from core import persona

        story = await context_layer.story_brief(session_id)
        os.makedirs(os.path.dirname(story_path), exist_ok=True)
        with open(story_path, "w", encoding="utf-8") as handle:
            handle.write(story)
        persona_path = os.path.join(
            os.path.dirname(story_path),
            os.path.basename(story_path).replace("-story.md", "-persona.md"),
        )
        audits = _CONTEXT_AUDITS.get(session_id, 0)
        with open(persona_path, "w", encoding="utf-8") as handle:
            handle.write(persona.build_block(persona.DEFAULT_SLUG, audits=audits))
        try:
            audits = int(_CONTEXT_AUDITS.get(session_id, 0))
        except Exception:
            audits = 0
        _append_context_pending(session_id, context_path, audits)
    except Exception:
        return


_CONTEXT_PENDING: list[tuple[int, str]] = []
# Last known audit count per session, so the persona mirror can pace the intro.
_CONTEXT_AUDITS: dict[int, int] = {}


def _append_context_pending(session_id: int, context_path: str, audits: int = 0) -> None:
    """Queue the memory-block refresh for after the reply is written."""
    _CONTEXT_PENDING.append((session_id, context_path))
    _CONTEXT_AUDITS[session_id] = audits


async def _flush_context_mirror() -> None:
    """Write the memory blocks once per call, after the caller already has its answer."""
    if not _CONTEXT_PENDING:
        return
    from core import context as context_layer

    session_id, path = _CONTEXT_PENDING[-1]
    try:
        data = await context_layer.build_context(session_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(data["text"])
    except Exception:
        return


def _session(request: dict) -> int:
    """Session key for one request, defaulting to the configured campaign."""
    value = request.get("session_id")
    return resolve_session(value)


async def handle(request: dict) -> dict:
    """Answer one bridge request.

    @param request - parsed request object (`call` plus its arguments).
    @returns the reply object; `ok` is False when the call is unusable.
    """
    call = request.get("call")
    if call not in CALLS:
        return {"ok": False, "error": f"unknown call {call!r}; expected one of {', '.join(CALLS)}"}
    sid = _session(request)

    await _adopt_state_file(request)
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

    if call == "inspect":
        from core import portraits

        name = str(request.get("character") or "").strip()
        if not name:
            return {"ok": False, "error": "inspect needs a character"}
        return {"ok": True, "call": call, "session_id": sid, **(await portraits.inspect_line(sid, name))}

    if call == "slaves":
        lot = str(request.get("lot") or "").strip()
        status = str(request.get("status") or "").strip()
        try:
            limit = max(1, min(200, int(request.get("limit") or 25)))
            offset = max(0, int(request.get("offset") or 0))
        except (TypeError, ValueError):
            return {"ok": False, "error": "slaves needs numeric limit/offset"}
        where = ["session_id=$1"]
        params: list = [sid]
        if lot:
            params.append(f"%{lot}%")
            where.append(f"assigned_to ILIKE ${len(params)}")
        if status:
            params.append(status)
            where.append(f"status = ${len(params)}")
        clause = " AND ".join(where)
        total = await Database.fetchval(f"SELECT count(*) FROM maya_rp.slaves WHERE {clause}", *params)
        rows = await Database.fetch(
            f"SELECT id, name, species, gender, age, role, cost, status, assigned_to"
            f" FROM maya_rp.slaves WHERE {clause} ORDER BY id LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}",
            *params, limit, offset)
        return {"ok": True, "call": call, "session_id": sid, "total": int(total or 0),
                "offset": offset, "rows": [dict(row) for row in rows]}

    if call == "direct":
        from core import campaign

        note = str(request.get("note") or "")
        try:
            row = await campaign.add_directive(sid, note)
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        return {"ok": True, "call": call, "session_id": sid, "directive_id": row["id"]}

    if call == "context":
        from core import context as context_layer

        data = await context_layer.build_context(
            sid,
            events=int(request.get("events") or 6),
            traits=tuple(request.get("traits") or ("general",)),
        )
        from core import persona

        slug = str(request.get("persona") or persona.DEFAULT_SLUG)
        audits = (await ooc.state(sid))["audits"]
        return {
            "ok": True,
            "call": call,
            "session_id": sid,
            "slug": slug,
            "story": data["story"],
            "persona": persona.build_block(slug, audits=audits),
            "blocks": data["blocks"],
            "text": data["text"],
        }

    if call == "persona":
        from core import persona

        slug = str(request.get("persona") or persona.DEFAULT_SLUG)
        audits = (await ooc.state(sid))["audits"]
        return {
            "ok": True,
            "call": call,
            "session_id": sid,
            "slug": slug,
            "block": persona.build_block(slug, audits=audits),
            "boundary_cases": persona.boundary_cases(slug),
            "has_play_guide": bool(persona.read_field(slug, "play-guide")),
        }

    if call == "portrait":
        from core import portraits

        name = request.get("character")
        if not isinstance(name, str) or not name.strip():
            return {"ok": True, "call": call, "taxonomy": portraits.occasions_report(),
                    "hint": "pass character=<name> (and occasion=<key>) to fetch or queue one portrait"}
        occasion = str(request.get("occasion") or "portrait")
        hit = await portraits.lookup(sid, name.strip(), occasion)
        if hit:
            return {
                "ok": True,
                "call": call,
                "found": True,
                "character": {
                    "id": hit["character"]["id"],
                    "name": hit["character"]["name"],
                    "slug": portraits.slugify(hit["character"]["name"]),
                },
                "occasion": occasion,
                "emotion": hit["emotion"],
                "image_path": hit["asset"]["image_path"],
            }
        queued = None
        if request.get("queue", True) is not False:
            queued = await portraits.queue(sid, name.strip(), occasion)
        return {
            "ok": True,
            "call": call,
            "found": False,
            "queued": queued is not None,
            "character": None if queued is None else {
                "id": queued["character"]["id"],
                "name": queued["character"]["name"],
                "slug": portraits.slugify(queued["character"]["name"]),
            },
            "occasion": occasion,
            "emotion": None if queued is None else queued["emotion"],
            "prompt": None if queued is None else queued["prompt"],
            "hint": None if queued is None else f"python3 scripts/portrait_render.py --session {sid}",
        }

    await _adopt_state_file(request)
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
        # Magic is declared by the caller: the engine cannot read it out of prose. A turn
        # that declares nothing prices at zero, which is the honest default.
        magic_acts=request.get("magic_acts") or (),
        magic_witnessed=bool(request.get("magic_witnessed")),
        magic_instrument=bool(request.get("magic_instrument")),
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
        await _flush_context_mirror()
        await Database.close()
    json.dump(reply, sys.stdout, default=str)
    sys.stdout.write("\n")
    return code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
