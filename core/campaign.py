#!/usr/bin/env python3
"""Campaign layer — lorebook, endings, director notes, act snapshots (fasa 6, M28-M31).

Everything here is campaign bookkeeping around the audit: lore that enters only
when a keyword does, endings that fire when a stat threshold does, player-side
director notes that are recorded but never audited, and act snapshots for
starting a later act directly.

@module core.campaign
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from core.config import Config
from core.db import Database
from core.log import warn

OPS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
}


# ── Lorebook (M29) ──────────────────────────────────────────────────────────

async def lore_entries(session_id: int | None = None, stage: str | None = None) -> list[dict[str, Any]]:
    """Enabled lore entries for this session and stage (campaign-wide included)."""
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    rows = await Database.fetch(
        "SELECT id, keywords, title, content, stage FROM maya_rp.ooc_lorebook"
        " WHERE enabled AND (session_id IS NULL OR session_id=$1)"
        "   AND (stage IS NULL OR stage=$2) ORDER BY id",
        sid,
        stage,
    )
    return [dict(row) for row in rows]


def lore_for(text: str | None, entries: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Entries whose keywords appear in the text; first keyword wins per entry."""
    haystack = (text or "").lower()
    if not haystack:
        return []
    hits: list[dict[str, Any]] = []
    for entry in entries:
        for keyword in entry.get("keywords") or []:
            token = str(keyword).lower()
            if token and token in haystack:
                hits.append(entry)
                break
    return hits


def render_lore(hits: Sequence[dict[str, Any]], limit: int = 4) -> str:
    """The `[LORE]` block for the entries this turn triggered."""
    if not hits:
        return ""
    lines = ["[LORE]"]
    for entry in list(hits)[:limit]:
        lines.append(f"- {entry['title']}: {str(entry['content'])[:320]}")
    return "\n".join(lines)


# ── Endings (M28) ───────────────────────────────────────────────────────────

async def stats(session_id: int) -> dict[str, Any]:
    """The numbers ending conditions are written against."""
    sid = int(session_id)
    state = await Database.fetchrow(
        "SELECT deviation, roleplay_points, audits, findings FROM maya_rp.ooc_system_state WHERE session_id=$1",
        sid,
    )
    values: dict[str, Any] = dict(state) if state else {
        "deviation": 0, "roleplay_points": 0, "audits": 0, "findings": 0,
    }
    values["suspicion_max"] = int(
        await Database.fetchval("SELECT COALESCE(MAX(suspicion),0) FROM maya_rp.ooc_suspicion WHERE session_id=$1", sid) or 0
    )
    values["bond_max"] = int(
        await Database.fetchval("SELECT COALESCE(MAX(bond),0) FROM maya_rp.characters WHERE session_id=$1", sid) or 0
    )
    values["beats_done"] = int(
        await Database.fetchval(
            "SELECT count(*) FROM maya_rp.ooc_milestones WHERE session_id=$1 AND completed_at IS NOT NULL", sid
        )
        or 0
    )
    return values


_WARNED_STATS: set[str] = set()


def condition_met(condition: str | dict[str, Any], values: dict[str, Any]) -> bool:
    """Evaluate one ending condition against the stat map.

    @param condition - JSON text or dict with `stat`, `op`, `value`.
    @param values - stat map from `stats()`.
    @returns False for an unknown stat (warned once), an unknown op or an unreadable condition.
    """
    if isinstance(condition, str):
        try:
            condition = json.loads(condition)
        except json.JSONDecodeError:
            return False
    if not isinstance(condition, dict):
        return False
    stat = condition.get("stat")
    op = OPS.get(str(condition.get("op") or ">="))
    if stat is None or op is None:
        return False
    # An unknown stat read as 0, so a `<`/`<=` ending naming a misspelled stat fired at once and
    # `triggered_endings` stamped it permanently. A stat the map does not carry is not evidence.
    if stat not in values:
        if stat not in _WARNED_STATS:
            _WARNED_STATS.add(stat)
            warn("campaign", f"ending condition names unknown stat {stat!r}; treated as not met")
        return False
    try:
        left = float(values.get(stat, 0) or 0)
        right = float(condition.get("value", 0) or 0)
    except (TypeError, ValueError):
        return False
    return op(left, right)


async def endings(session_id: int | None = None) -> list[dict[str, Any]]:
    """Every registered ending with its condition met/unmet."""
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    rows = await Database.fetch(
        "SELECT id, name, kind, condition, prose, triggered_at FROM maya_rp.ooc_endings"
        " WHERE session_id=$1 ORDER BY id",
        sid,
    )
    values = await stats(sid)
    out: list[dict[str, Any]] = []
    for row in rows:
        entry = dict(row)
        entry["met"] = condition_met(entry["condition"], values)
        out.append(entry)
    return out


async def triggered_endings(session_id: int | None = None) -> list[dict[str, Any]]:
    """Endings whose condition is met now; the first firing is stamped."""
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    hits = [entry for entry in await endings(sid) if entry["met"]]
    for entry in hits:
        if entry["triggered_at"] is None:
            await Database.execute(
                "UPDATE maya_rp.ooc_endings SET triggered_at=now()"
                " WHERE id=$1 AND session_id=$2 AND triggered_at IS NULL",
                entry["id"],
                sid,
            )
    return hits


def near_endings(entries: Sequence[dict[str, Any]], values: dict[str, Any], ratio: float = 0.8) -> list[str]:
    """Hints for conditions close to firing, so the turn can feel the edge."""
    hints: list[str] = []
    for entry in entries:
        condition = entry.get("condition")
        if isinstance(condition, str):
            try:
                condition = json.loads(condition)
            except json.JSONDecodeError:
                continue
        if not isinstance(condition, dict):
            continue
        stat = condition.get("stat")
        # The hint measures distance up to the target, which is only true for `>=`/`>`. For `<`/`<=`
        # it printed a stat already below the line as "near".
        if str(condition.get("op") or ">=") not in (">=", ">") or stat not in values:
            continue
        try:
            target = float(condition.get("value", 0) or 0)
            current = float(values.get(stat, 0) or 0)
        except (TypeError, ValueError):
            continue
        if target > 0 and not entry.get("met") and current >= target * ratio:
            hints.append(f"- endings near: {entry['name']} ({current:.0f}/{target:.0f})")
    return hints


# ── Director notes (M30) ────────────────────────────────────────────────────

async def add_directive(session_id: int | None = None, note: str = "") -> dict[str, Any]:
    """Record one out-of-character note; it is never audited as prose.

    @param session_id - session key; the configured session when omitted.
    @param note - the note text.
    @raises FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    if not note.strip():
        raise ValueError("directive needs a non-empty note")
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    # A frozen campaign is reference. `add_directive` wrote into one with no check, so the one
    # door that `audit` and the ooc writers keep shut was open here. Guard on the resolved
    # id, before any read-then-write.
    from core.ooc import _refuse_frozen

    _refuse_frozen(sid)
    row = await Database.fetchrow(
        "INSERT INTO maya_rp.ooc_directives (session_id, note) VALUES ($1,$2) RETURNING id, note, created_at",
        sid,
        note.strip(),
    )
    return dict(row)


async def directives(session_id: int | None = None, limit: int = 5) -> list[dict[str, Any]]:
    """Recent director notes, newest first."""
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    rows = await Database.fetch(
        "SELECT id, note, created_at FROM maya_rp.ooc_directives WHERE session_id=$1 ORDER BY id DESC LIMIT $2",
        sid,
        int(limit),
    )
    return [dict(row) for row in rows]


# ── RPP sinks (M7) ──────────────────────────────────────────────────────────

SPEND_PRICES = {
    "skip_beat": 25,       # complete a required beat without prose proof
    "calm_observer": 15,   # -10 suspicion on an observer
    "reveal_intel": 10,    # record an intel request as a director note
}


async def spend(session_id: int | None = None, kind: str = "", target: str | None = None) -> dict[str, Any]:
    """Spend roleplay points through a sink (M7).

    Kept deliberately small and honest: an unknown sink refuses rather than
    guessing, and a spend the balance cannot cover is refused with the price.

    @param session_id - session key; the configured session when omitted.
    @param kind - sink name from `SPEND_PRICES`.
    @param target - milestone name or intel text, depending on the sink.
    @raises FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    # A frozen campaign is reference. `spend` wrote into one with no check, so the one
    # door that `audit` and the ooc writers keep shut was open here. Guard on the resolved
    # id, before any read-then-write.
    from core.ooc import _refuse_frozen

    _refuse_frozen(sid)
    price = SPEND_PRICES.get(kind)
    if price is None:
        raise ValueError(f"unknown sink {kind!r}; known: {', '.join(sorted(SPEND_PRICES))}")
    if kind == "skip_beat" and not target:
        raise ValueError("skip_beat needs the milestone name")
    # Two concurrent `skip_beat` calls both read balance 25, both completed the beat, and the second
    # debit then broke `roleplay_points >= 0`: one payment, two completions. The debit is one
    # conditional statement and runs first, so the balance check and the spend are the same
    # atomic step; only the caller that wins the debit applies the effect.
    debited = await Database.fetchval(
        "UPDATE maya_rp.ooc_system_state SET roleplay_points=roleplay_points-$2, updated_at=now()"
        " WHERE session_id=$1 AND COALESCE(roleplay_points,0)>=$2 RETURNING roleplay_points",
        sid,
        price,
    )
    if debited is None:
        balance = int(
            await Database.fetchval(
                "SELECT COALESCE(roleplay_points,0) FROM maya_rp.ooc_system_state WHERE session_id=$1", sid)
            or 0
        )
        raise ValueError(f"{kind} costs {price} rpp; the crown holds {balance}")
    try:
        detail = await _apply_spend(sid, kind, target)
    except BaseException:
        # The effect failed after the debit: give the points back so a refused spend costs nothing.
        await Database.execute(
            "UPDATE maya_rp.ooc_system_state SET roleplay_points=roleplay_points+$2, updated_at=now()"
            " WHERE session_id=$1",
            sid,
            price,
        )
        raise
    return {"ok": True, "sink": kind, "price": price, "spent_from": int(debited) + price, "detail": detail}


async def _apply_spend(sid: int, kind: str, target: str | None) -> str:
    """Apply one sink's effect after its price has been debited.

    @param sid - resolved session id.
    @param kind - sink name from `SPEND_PRICES`.
    @param target - milestone name or intel text.
    @returns the detail line for the spend result.
    @raises ValueError - the effect cannot apply (no open beat, no observer, sink without a branch).
    """
    if kind == "skip_beat":
        row = await Database.fetchrow(
            "UPDATE maya_rp.ooc_milestones SET completed_at=now()"
            " WHERE session_id=$1 AND name=$2 AND completed_at IS NULL RETURNING name",
            sid,
            target,
        )
        if row is None:
            raise ValueError(f"no open beat named {target}")
        return f"beat {target} paid past"
    if kind == "calm_observer":
        from core import ooc

        observer = await ooc.observer_id(sid)
        if observer is None:
            raise ValueError("no observer to calm")
        await ooc.bump_suspicion(sid, observer, -10, f"paid:{kind}")
        return f"observer {observer} relaxed by 10"
    if kind == "reveal_intel":
        await add_directive(sid, f"[paid:{kind}] {target or 'intel request'}")
        return "intel request recorded"
    # A price without a branch would spend the points and record a director note as if the
    # caller had asked for intel. The table and the branches are two lists; this refuses to
    # let them disagree.
    raise ValueError(f"sink {kind!r} has a price but no branch in spend()")


# ── Debuff effects (M6) ─────────────────────────────────────────────────────

DEBUFF_EFFECTS = {
    "Neural Tremor": {"battle_penalty": 1, "romance_blocked": False, "crew_morale": -2,
                      "note": "the hands shake under pressure"},
    "Meridian Lock": {"battle_penalty": 3, "romance_blocked": True, "crew_morale": -5,
                      "note": "the flesh refuses the command"},
    "System Reclamation": {"battle_penalty": 6, "romance_blocked": True, "crew_morale": -10,
                           "note": "the shell answers, the person does not"},
}


async def debuff_effects(session_id: int | None = None) -> dict[str, Any]:
    """The active penalty as concrete modifiers (M6).

    Modules read this instead of parsing the ladder themselves; wiring each
    module to it is follow-up work, the mapping is here so it cannot drift.
    """
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    state = await Database.fetchrow("SELECT debuff, deviation FROM maya_rp.ooc_system_state WHERE session_id=$1", sid)
    debuff = (state or {}).get("debuff")
    effects = DEBUFF_EFFECTS.get(debuff or "", {"battle_penalty": 0, "romance_blocked": False, "crew_morale": 0,
                                                "note": "none"})
    return {"debuff": debuff, "deviation": (state or {}).get("deviation", 0), **effects}


# ── Character-scoped rules (M9) ─────────────────────────────────────────────

async def character_rules(session_id: int | None = None, name: str = "") -> dict[str, Any]:
    """Rules whose trait matches one character's traits (M9).

    The audit itself resolves rules against the Host's persona; this is the
    lookup a scene uses when an NPC's own register should colour the exchange.
    """
    from core import portraits

    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    character = await portraits.find_character(sid, name)
    if character is None:
        raise ValueError(f"character not found: {name}")
    traits = portraits.parse_traits(character.get("traits"))
    if not traits:
        return {"character": character["name"], "traits": [], "rules": []}
    rows = await Database.fetch(
        "SELECT id, kind, pattern FROM maya_rp.ooc_rules"
        " WHERE enabled AND trait = ANY($1::text[])"
        "   AND (session_id IS NULL OR session_id=$2) ORDER BY id LIMIT 20",
        [str(t) for t in traits],
        sid,
    )
    return {"character": character["name"], "traits": traits, "rules": [dict(row) for row in rows]}


# ── Knowledge ledger (M4, data layer) ───────────────────────────────────────

async def learn(session_id: int | None, observer_id: int, fact_key: str, source: str = "") -> dict[str, Any]:
    """Record that a character learned a fact (M4).

    @param session_id - session key; the configured session when omitted.
    @param observer_id - the character who learned it.
    @param fact_key - the fact.
    @param source - where it was learned from.
    @raises FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    if not fact_key.strip():
        raise ValueError("fact_key must be non-empty")
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    # A frozen campaign is reference. `learn` wrote into one with no check, so the one
    # door that `audit` and the ooc writers keep shut was open here. Guard on the resolved
    # id, before any read-then-write.
    from core.ooc import _refuse_frozen

    _refuse_frozen(sid)
    row = await Database.fetchrow(
        "INSERT INTO maya_rp.character_knowledge (session_id, character_id, fact_key, source)"
        " VALUES ($1,$2,$3,$4)"
        " ON CONFLICT (session_id, character_id, fact_key) DO UPDATE SET source=EXCLUDED.source"
        " RETURNING character_id, fact_key, learned_at",
        sid,
        int(observer_id),
        fact_key.strip(),
        source.strip() or None,
    )
    return dict(row)


async def knowledge_of(session_id: int | None, observer_id: int) -> list[dict[str, Any]]:
    """What one character has witnessed, newest first (M4)."""
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    rows = await Database.fetch(
        "SELECT fact_key, source, learned_at FROM maya_rp.character_knowledge"
        " WHERE session_id=$1 AND character_id=$2 ORDER BY learned_at DESC LIMIT 50",
        sid,
        int(observer_id),
    )
    return [dict(row) for row in rows]


# ── Act snapshots (M31) ─────────────────────────────────────────────────────

async def snapshot(session_id: int | None = None) -> dict[str, Any]:
    """State + milestones + exemptions + suspicion: enough to resume an act."""
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    state = await Database.fetchrow("SELECT * FROM maya_rp.ooc_system_state WHERE session_id=$1", sid)
    milestones = await Database.fetch(
        "SELECT name, trait, stage, required, rpp_reward, latch_ruleset, completed_at, expires_at"
        " FROM maya_rp.ooc_milestones WHERE session_id=$1 ORDER BY id",
        sid,
    )
    exemptions = await Database.fetch(
        "SELECT rule_id, action_key, condition, cost_rpp, permanent, expires_at FROM maya_rp.ooc_exemptions"
        " WHERE session_id=$1 ORDER BY id",
        sid,
    )
    suspicion = await Database.fetch(
        "SELECT observer_id, suspicion, last_reason FROM maya_rp.ooc_suspicion WHERE session_id=$1 ORDER BY observer_id",
        sid,
    )
    return {
        "version": 1,
        "session_id": sid,
        "state": {k: v for k, v in dict(state).items()} if state else {},
        "milestones": [dict(row) for row in milestones],
        "exemptions": [dict(row) for row in exemptions],
        "suspicion": [dict(row) for row in suspicion],
    }


def save_snapshot(data: dict[str, Any], path: str | Path) -> Path:
    """Write a snapshot to disk (JSON)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, default=str, indent=2), encoding="utf-8")
    return target


def load_snapshot(path: str | Path) -> dict[str, Any]:
    """Read a snapshot written by `save_snapshot`."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _as_datetime(value: Any) -> Any:
    """A snapshot timestamp, back as a datetime.

    `save_snapshot` writes JSON, so every datetime in a loaded snapshot is text, and asyncpg refuses
    text for a timestamptz parameter. The in-process caller (`snapshot()` straight into
    `restore_snapshot()`) hands over real datetimes, so both shapes arrive here.
    """
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"snapshot carries an unreadable timestamp {value!r}") from exc


async def restore_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    """Apply a snapshot: state, milestone completions, exemptions, suspicion.

    Used to start a later act directly (their "Starting Scenario 2"): the
    snapshot owns the numbers, the beats and the meters for that moment.

    All four are written. The exemptions and the suspicion rows used to be counted in the return
    value without being applied, so an act resumed from a file lost every purchased exemption and
    every observer's suspicion while the result said they had come back.

    @param data - snapshot as `snapshot()` or `load_snapshot()` returns it; its `session_id` is the target.
    @raises FrozenSession - the session the file names is frozen and maintenance is not armed.
    """
    sid = int(data.get("session_id") or Config.SESSION_ID)
    # A frozen campaign is reference. `restore_snapshot` wrote into one with no check, so the one
    # door that `audit` and the ooc writers keep shut was open here. Guard on the resolved
    # id, before any read-then-write.
    from core.ooc import _refuse_frozen

    _refuse_frozen(sid)
    state = data.get("state") or {}
    # Validate before the first write. A bad row used to raise after state, milestones and
    # exemptions were already committed, leaving the target half-restored.
    for observer in data.get("suspicion") or []:
        if observer.get("observer_id") is None:
            raise ValueError("snapshot carries a suspicion row with no observer_id")
    for milestone in data.get("milestones") or []:
        _as_datetime(milestone.get("completed_at"))
    for exemption in data.get("exemptions") or []:
        _as_datetime(exemption.get("expires_at"))
    milestones = 0
    exemptions = 0
    observers = 0
    # One transaction on the yielded connection: an FK failure on rule_id or any later row rolls
    # back every earlier write. Every statement goes through `conn`; a `Database.execute` here
    # would autocommit on another pool connection and escape the rollback.
    async with Database.transaction() as conn:
        if state:
            await conn.execute(
                "INSERT INTO maya_rp.ooc_system_state"
                " (session_id, arc_stage, deviation, roleplay_points, audits, findings, debuff)"
                " VALUES ($1,$2,$3,$4,$5,$6,$7)"
                " ON CONFLICT (session_id) DO UPDATE SET arc_stage=EXCLUDED.arc_stage,"
                " deviation=EXCLUDED.deviation, roleplay_points=EXCLUDED.roleplay_points,"
                " audits=EXCLUDED.audits, findings=EXCLUDED.findings, debuff=EXCLUDED.debuff, updated_at=now()",
                sid,
                state.get("arc_stage", "lockdown"),
                int(state.get("deviation", 0) or 0),
                int(state.get("roleplay_points", 0) or 0),
                int(state.get("audits", 0) or 0),
                int(state.get("findings", 0) or 0),
                state.get("debuff"),
            )
        for milestone in data.get("milestones") or []:
            applied = await conn.fetchval(
                "UPDATE maya_rp.ooc_milestones SET completed_at=$3"
                " WHERE session_id=$1 AND name=$2 RETURNING name",
                sid,
                milestone.get("name"),
                _as_datetime(milestone.get("completed_at")),
            )
            # Counted only when a row was there: a snapshot can name a beat the target session does not
            # carry, and the return value must not report that as restored.
            milestones += 1 if applied else 0
        for exemption in data.get("exemptions") or []:
            await conn.execute(
                "INSERT INTO maya_rp.ooc_exemptions"
                " (session_id, rule_id, action_key, condition, cost_rpp, permanent, expires_at)"
                " VALUES ($1,$2,$3,$4,$5,$6,$7)"
                " ON CONFLICT (session_id, rule_id, action_key) DO UPDATE SET"
                " condition=EXCLUDED.condition, cost_rpp=EXCLUDED.cost_rpp,"
                " permanent=EXCLUDED.permanent, expires_at=EXCLUDED.expires_at",
                sid,
                exemption.get("rule_id"),
                exemption.get("action_key"),
                exemption.get("condition"),
                int(exemption.get("cost_rpp") or 0),
                bool(exemption.get("permanent")),
                _as_datetime(exemption.get("expires_at")),
            )
            exemptions += 1
        for observer in data.get("suspicion") or []:
            if observer.get("observer_id") is None:
                raise ValueError("snapshot carries a suspicion row with no observer_id")
            await conn.execute(
                "INSERT INTO maya_rp.ooc_suspicion (session_id, observer_id, suspicion, last_reason)"
                " VALUES ($1,$2,$3,$4)"
                " ON CONFLICT (session_id, observer_id) DO UPDATE SET"
                " suspicion=EXCLUDED.suspicion, last_reason=EXCLUDED.last_reason, updated_at=now()",
                sid,
                int(observer["observer_id"]),
                int(observer.get("suspicion") or 0),
                observer.get("last_reason"),
            )
            observers += 1
    return {"ok": True, "session_id": sid, "state": bool(state), "milestones": milestones,
            "exemptions": exemptions, "suspicion": observers}
