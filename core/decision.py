#!/usr/bin/env python3
"""Decision provenance helper — record & walk causal chains.

Part of the Semantica-inspired decision-provenance layer (plan 2026-08-18).
Zero-LLM: every function is pure SQL. The LLM may narrate a chain; it can
never produce one.

Sources of truth:
  - maya_rp.cabinet_decrees   (extended: parent_id, game_day, event_ids,
                               state_before, state_after)
  - maya_rp.decision_stream   (unified view: decrees + grand_plan items)
  - maya_rp.events            (evidence, linked via event_ids)
"""
from __future__ import annotations
import json
from typing import Any, Optional
from core.db import Database
from core.log import warn


async def record(
    actor: str,
    decision_type: str,
    title: str,
    *,
    description: str = "",
    parent_id: Optional[int] = None,
    game_day: Optional[int] = None,
    state_delta: Optional[dict] = None,
    state_before: Optional[dict] = None,
    event_ids: Optional[list[int]] = None,
    decree_id: Optional[int] = None,
    priority: str = "standard",
    secrecy: str = "shadow",
    session_id: Optional[int] = None,
) -> int:
    """Append a decision to the provenance chain. Returns decision id.

    If decree_id is given, updates that existing cabinet_decree row with the
    provenance columns instead of inserting (single source of truth). Returns
    None when that row does not exist in this session, so a miss is not reported
    as a write.

    jsonb parameters are bound as `json.dumps` text: `core.db` registers no jsonb
    codec, so asyncpg rejected a dict with `DataError: expected str, got dict` and
    every call failed. The INSERT writes `state_delta` to both `state_after` and
    `impact_deltas`: `by_fact` and `chain` read both columns, so the delta must be
    visible in each.

    The UPDATE leaves an unset argument alone (`COALESCE($n, col)`). Defaulting
    to `[]`/`{}` overwrote parent_id, game_day, event_ids and state_before that
    `link_event` or an earlier record had written, erasing the provenance the
    call was meant to extend. To clear a column, pass an explicit empty value.

    @param actor - issuing party, stored in `issued_by`.
    @param decision_type - a `decree_type` allowed by the table check constraint.
    @param title - decision title.
    @param description - free text, INSERT only.
    @param parent_id - decision this one follows from; None keeps the stored value on UPDATE.
    @param game_day - game day; None keeps the stored value on UPDATE.
    @param state_delta - dict written to `state_after` (and `impact_deltas` on INSERT).
    @param state_before - dict written to `state_before`.
    @param event_ids - evidence event ids; None keeps the stored value on UPDATE.
    @param decree_id - existing decree to update instead of inserting.
    @param priority - INSERT only.
    @param secrecy - INSERT only.
    @param session_id - session, used as given when not None; resolved per call via `require_session` when None.
    @returns the decision id, or None when `decree_id` is not in this session.
    """
    # Resolved per call: Config.SESSION_ID is fixed at import, so a long-lived
    # process kept writing decisions into the session that was current at start.
    from core.session import require_session
    # An explicit id is read as given, 0 included; only an omitted one resolves per call.
    sid = session_id if session_id is not None else require_session(None)
    before = None if state_before is None else json.dumps(state_before)
    after = None if state_delta is None else json.dumps(state_delta)
    if decree_id is not None:
        tag = await Database.execute(
            "UPDATE maya_rp.cabinet_decrees SET "
            "parent_id=COALESCE($1, parent_id), game_day=COALESCE($2, game_day), "
            "event_ids=COALESCE($3::int[], event_ids), "
            "state_before=COALESCE($4::jsonb, state_before), "
            "state_after=COALESCE($5::jsonb, state_after) "
            "WHERE id=$6 AND session_id=$7",
            parent_id, game_day, event_ids, before, after, decree_id, sid,
        )
        if tag.rsplit(" ", 1)[-1] == "0":
            warn("decision", f"decree {decree_id} not found in session {sid}; "
                             "provenance not written")
            return None
        return decree_id
    row = await Database.fetchrow(
        "INSERT INTO maya_rp.cabinet_decrees "
        "(session_id, issued_by, decree_type, title, description, status, priority, "
        " secrecy_level, parent_id, game_day, event_ids, state_before, state_after, impact_deltas) "
        "VALUES ($1,$2,$3,$4,$5,'executing',$6,$7,$8,$9,$10::int[],$11::jsonb,$12::jsonb,$12::jsonb) "
        "RETURNING id",
        sid, actor, decision_type, title, description, priority, secrecy,
        parent_id, game_day, event_ids or [], before or "{}", after or "{}",
    )
    return row["id"]


async def chain(session_id: int, decision_id: int, depth: int = 20) -> list[dict]:
    """Walk parent_id chain from a decision back to genesis (or depth cap)."""
    out: list[dict] = []
    cur = decision_id
    for _ in range(depth):
        row = await Database.fetchrow(
            "SELECT d.id, d.parent_id, d.game_day, d.issued_by AS actor, "
            "       d.decree_type AS decision_type, d.title, d.description, "
            "       d.status, d.priority, d.impact_deltas, d.state_after, "
            "       d.event_ids, d.issued_at AS occurred_at "
            "FROM maya_rp.cabinet_decrees d WHERE d.id=$1 AND d.session_id=$2",
            cur, session_id,
        )
        if not row:
            break
        out.append(dict(row))
        if row["parent_id"] is None:
            break
        cur = row["parent_id"]
    return out


async def by_fact(session_id: int, fact_key: str, fact_value: Any = None,
                  limit: int = 25) -> list[dict]:
    """Find decisions whose state_after/impact_deltas touch a fact.

    fact_key examples: 'treasury', 'ships', 'status', 'queens', 'bonds'.
    If fact_value given, matches it (JSONB equality or containment).
    """
    if fact_value is None:
        rows = await Database.fetch(
            "SELECT id, game_day, issued_by AS actor, decree_type AS decision_type, "
            "       title, status, impact_deltas, state_after, event_ids "
            "FROM maya_rp.cabinet_decrees "
            "WHERE session_id=$1 AND (state_after ? $2 OR impact_deltas ? $2) "
            "ORDER BY COALESCE(game_day, 0) DESC, id DESC LIMIT $3",
            session_id, fact_key, limit,
        )
    else:
        # json.dumps, not f'"{value}"': a number carried as a JSON string never
        # equals the number in the column, so every numeric lookup returned nothing.
        rows = await Database.fetch(
            "SELECT id, game_day, issued_by AS actor, decree_type AS decision_type, "
            "       title, status, impact_deltas, state_after, event_ids "
            "FROM maya_rp.cabinet_decrees "
            "WHERE session_id=$1 AND (state_after->$2 = $3::jsonb "
            "   OR impact_deltas->$2 = $3::jsonb) "
            "ORDER BY COALESCE(game_day, 0) DESC, id DESC LIMIT $4",
            session_id, fact_key, json.dumps(fact_value), limit,
        )
    return [dict(r) for r in rows]


async def link_event(session_id: int, decision_id: int, event_id: int) -> None:
    """Attach an evidence event to a decision (idempotent).

    Raises nothing and returns nothing by contract, so a miss is logged: the
    update is scoped to the decision's own session and a mismatched id used to
    complete in silence.
    """
    tag = await Database.execute(
        "UPDATE maya_rp.cabinet_decrees SET event_ids = "
        "ARRAY(SELECT DISTINCT unnest(event_ids || ARRAY[$1::int])) "
        "WHERE id=$2 AND session_id=$3",
        event_id, decision_id, session_id,
    )
    if tag.rsplit(" ", 1)[-1] == "0":
        warn("decision", f"event {event_id} not linked: decision {decision_id} "
                         f"is not in session {session_id}")


async def decisions(session_id: int, *, day: Optional[int] = None,
                    kind: Optional[str] = None, status: Optional[str] = None,
                    limit: int = 20) -> list[dict]:
    """Unified decision list (decrees + plan) with optional filters.

    `day` matches `game_day`, which the view reports as NULL for every plan row,
    so a `day` filter returns decrees only.

    The `decision_stream` view select-lists both branches without their
    `session_id`, so filtering has to ask the base tables which row belongs to
    this session. Without it the call returned every campaign's decisions. The
    base predicate is parenthesised as a whole: the appended `AND` filters bound
    only to the plan branch of the `OR`, so `status`/`kind`/`day` let every
    decree through.
    """
    sql = ["SELECT kind, decision_id, parent_id, game_day, actor, decision_type, "
           "       title, status, priority, secrecy_level, impact_deltas, "
           "       event_ids, occurred_at FROM maya_rp.decision_stream "
           "WHERE ((kind = 'decree' AND decision_id IN "
           "         (SELECT id FROM maya_rp.cabinet_decrees WHERE session_id = $1)) "
           "   OR (kind = 'plan' AND decision_id IN "
           "         (SELECT id FROM maya_rp.grand_plan WHERE session_id = $1)))"]
    args: list = [session_id]
    if day is not None:
        args.append(day)
        sql.append(f"AND game_day = ${len(args)}")
    if kind is not None:
        args.append(kind)
        sql.append(f"AND kind = ${len(args)}")
    if status is not None:
        args.append(status)
        sql.append(f"AND status = ${len(args)}")
    args.append(limit)
    sql.append(f"ORDER BY occurred_at DESC, decision_id DESC LIMIT ${len(args)}")
    return [dict(r) for r in await Database.fetch(" ".join(sql), *args)]


async def add_cli(argv: list[str]) -> dict:
    """CLI front for record() — parses --key value pairs."""
    kv = _parse_flags(argv)
    actor = kv.get("actor", "Izzat")
    dtype = kv.get("type", "directive")
    title = kv.get("title", "Decision")
    parent = int(kv["parent"]) if kv.get("parent") else None
    day = int(kv["day"]) if kv.get("day") else None
    delta = _json(kv.get("delta"))
    before = _json(kv.get("before"))
    events = [int(x) for x in kv["events"].split(",")] if kv.get("events") else None
    did = await record(
        actor, dtype, title,
        description=kv.get("desc", ""),
        parent_id=parent, game_day=day, state_delta=delta,
        state_before=before, event_ids=events,
        priority=kv.get("priority", "standard"),
        secrecy=kv.get("secrecy", "shadow"),
    )
    return {"decision_id": did, "title": title}


def _parse_flags(argv: list[str]) -> dict:
    out: dict[str, str] = {}
    it = iter(argv)
    for a in it:
        if a.startswith("--"):
            key = a[2:]
            val = next(it, "")
            out[key] = val
    return out


def _json(s: Optional[str]) -> Optional[dict]:
    if not s:
        return None
    import json
    try:
        return json.loads(s)
    except Exception:
        return {"raw": s}
