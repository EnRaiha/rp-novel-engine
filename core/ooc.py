#!/usr/bin/env python3
"""OOC engine — System overseer, engine plane.

The System audits the Host's prose for persona deviation and keeps the running
score. This module owns the authoritative state and the audit itself; it sits
beside `core/guard.py` (fact contradictions) as the register sibling (somatic
tone, lexicon, modern phrasing).

Design: `Bumi-Hijau/wiki/rp-dev/OOC-SYSTEM-DESIGN-2026-09-19.md`
  §2  dual-layer split — determinism without an LLM deciding what a rule sees
  §3  schema — migration 108 (`ooc_system_state`, `ooc_rules`, `ooc_audit_events`)
  §7  per-stage thresholds + decay lambda (a one-way ratchet is a lie)
  §8  build order D1–D3 (layer split → cascade → provenance)
  §13 option C — the engine owns state; the DSH plugin stays placement + audit

Everything in the top half of this module is pure: the same rule evaluation runs
on streamed prose, on a tool argument, or from the CLI, and can be unit-tested
without PostgreSQL. Only the `state`/`effective_rules`/`audit` trio touches the DB.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Sequence

from core.config import Config
from core.db import Database

# ── Layers (§2) ─────────────────────────────────────────────────────────
LAYER_SOMATIC = "somatic"
LAYER_DIALOGUE = "dialogue"
LAYER_BOTH = "both"
LAYER_TOOL = "tool"

# ── Bounds (R1: a regex may only ever backtrack over a bounded text) ────
MAX_AUDIT_CHARS = 20_000
MAX_PATTERN_CHARS = 400
_PATTERN_CACHE: dict[tuple[str, bool], re.Pattern[str]] = {}

# ── Stage thresholds (§7) ───────────────────────────────────────────────
STAGES: tuple[str, ...] = ("lockdown", "selective", "confrontation")
STAGE_THRESHOLDS: dict[str, dict[str, int]] = {
    # warn / crit / exec, then the per-turn deviation decay lambda.
    "lockdown": {"warning": 25, "critical": 50, "execution": 75, "decay": 0},
    "selective": {"warning": 40, "critical": 75, "execution": 100, "decay": 2},
    "confrontation": {"warning": 50, "critical": 80, "execution": 100, "decay": 5},
}
# Highest stage first, so lookup is a scan from the top.
DEBUFF_LADDER: tuple[tuple[str, str, str], ...] = (
    ("execution", "System Reclamation", "The Host loses autonomy; the story continues from inside the mindscape."),
    ("critical", "Meridian Lock", "A primary limb refuses commands until deviation drops."),
    ("warning", "Neural Tremor", "Phantom feedback the persona must hide in front of others."),
)

# ── Pairing used to separate prose surfaces (§2) ─────────────────────────
_QUOTE_PAIRS: tuple[tuple[str, str], ...] = (
    ("\"", "\""),
    ("“", "”"),
    ("‘", "’"),
    ("「", "」"),
    ("『", "』"),
    ("'", "'"),
)

# ── Loophole heuristic (D4 / O1: credit needs action evidence) ───────────
PROTECTIVE_TOKENS: tuple[str, ...] = (
    "shield", "protect", "escort", "evac", "evacuate", "medical", "ration", "reinforce",
    "reroute", "guard", "cover", "resupply", "withdraw", "reassign",
)
IMPERSONAL_TOKENS: tuple[str, ...] = (
    "asset", "strategic", "protocol", "procedure", "doctrine", "efficiency", "compliance",
    "allocation", "readiness", "risk", "logistics", "requisition", "standing order",
)
EMOTIVE_TOKENS: tuple[str, ...] = (
    "i feel", "i felt", "i was scared", "i am scared", "i miss you", "i missed you",
    "i love you", "i am sorry", "i'm sorry", "i was worried", "i need you",
    "please stay", "i care",
)
PROTECTIVE_WEIGHT = 22
IMPERSONAL_WEIGHT = 14
LOOPHOLE_MAX = 100

# O1 (design §5): a lexical score alone is farmable, so a win also needs the
# action that backs it. Both knobs are read from the plugin/CLI config.
DEFAULT_LOOPHOLE_MIN = 40
DEFAULT_RPP_PER_LOOPHOLE = 1

# §6 — observer suspicion moves on micro-inconsistency and decays slower than
# deviation, so a lapse the Host hides from the NPC is what a mortal notices.
SUSPICION_MICRO_MAX = 4      # a finding at or below this is small enough to hide
SUSPICION_MU = 5             # per hidden micro-inconsistency
SUSPICION_MU_DECAY = 1       # relaxation per clean turn

# §6.1 — bands module consumers (`social`, `council`) read. The meter stays the
# observer's; a module only colours behaviour by the band, one-way read.
SUSPICION_WATCHFUL = 25
SUSPICION_PROBING = 60
SUSPICION_CERTAIN = 90


# ═══════════════════════════════════════════════════════════════════════
# Layer split — pure
# ═══════════════════════════════════════════════════════════════════════


def _is_wordish(char: str | None) -> bool:
    return char is not None and (char.isalnum() or char == "_")


def split_layers(text: str) -> dict[str, str]:
    """Split one text into the surface each rule family may police.

    An apostrophe only opens a quote when no word character touches it, so
    contractions (`isn't`, `Sera's`) stay somatic instead of swallowing the
    rest of the narration.

    @param text - prose as the model wrote it.
    @returns `{"somatic": ..., "dialogue": ...}` with both parts in source order.
    """
    somatic: list[str] = []
    dialogue: list[str] = []
    closer: str | None = None
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        pair = next(((open_, close) for open_, close in _QUOTE_PAIRS if open_ == char), None)
        if pair is not None and closer is None:
            open_, close = pair
            if open_ == "'" and (_is_wordish(text[index - 1] if index else None) or _is_wordish(text[index + 1] if index + 1 < length else None)):
                somatic.append(char)
                index += 1
                continue
            closer = close
            dialogue.append(char)
        elif closer is not None and char == closer:
            closer = None
            dialogue.append(char)
        elif closer is not None:
            dialogue.append(char)
        else:
            somatic.append(char)
        index += 1
    return {LAYER_SOMATIC: "".join(somatic), LAYER_DIALOGUE: "".join(dialogue)}


# ═══════════════════════════════════════════════════════════════════════
# Rules — pure
# ═══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class OocRule:
    """One System rule as authored in `maya_rp.ooc_rules`."""

    id: str
    kind: str
    pattern: str
    delta: int
    layer: str = LAYER_BOTH
    trait: str | None = None
    is_regex: bool = False


@dataclass(frozen=True)
class OocFinding:
    """One rule match, with the surface it was found on."""

    rule_id: str
    kind: str
    layer: str
    match: str
    delta: int


def _reject_nested_quantifier(source: str) -> None:
    """Refuse a pattern whose groups repeat unbounded — the ReDoS shape (R1)."""
    if re.search(r"\([^)]*[+*][^)]*\)\s*[+*{]", source) or re.search(r"\{\d{3,}", source):
        raise ValueError(f"pattern risks unbounded backtracking: {source!r}")


def compile_rule(rule: OocRule) -> re.Pattern[str]:
    """Compile one rule once, caching by pattern (R1).

    Boundaries are lookarounds, not `\\b`, so a phrase ending in punctuation still
    matches and a phrase inside a longer word never does.

    @param rule - rule to compile.
    @returns a fresh-by-`finditer` global regular expression.
    """
    key = (rule.pattern, rule.is_regex)
    cached = _PATTERN_CACHE.get(key)
    if cached is not None:
        return cached
    source = rule.pattern[3:] if rule.pattern.startswith("re:") else re.escape(rule.pattern)
    if len(source) > MAX_PATTERN_CHARS:
        raise ValueError(f"pattern longer than {MAX_PATTERN_CHARS} chars: {rule.id}")
    _reject_nested_quantifier(source)
    compiled = re.compile(rf"(?<![A-Za-z0-9_])(?:{source})(?![A-Za-z0-9_])", re.IGNORECASE)
    _PATTERN_CACHE[key] = compiled
    return compiled


def audit_text(text: str, rules: Sequence[OocRule], layer: str = LAYER_DIALOGUE) -> list[OocFinding]:
    """Apply every applicable rule to one text, on its own surface only.

    A rule authored for `dialogue` never sees narration, and a `somatic` rule
    never sees a quoted line — the two false-positive directions §2 names. For a
    tool argument the caller passes prose fields only (paths, identifiers, and
    embedded JSON are dropped before this call), so the rule sees the slip without
    ever seeing a filename.

    @param text - prose to audit.
    @param rules - ruleset already resolved for the session (see `effective_rules`).
    @param layer - surface of `text`: `dialogue`, `somatic`, or `tool`.
    @returns findings in rule order.
    """
    if not text:
        return []
    bounded = text[:MAX_AUDIT_CHARS]
    surfaces = split_layers(bounded)
    findings: list[OocFinding] = []
    for rule in rules:
        if layer == LAYER_TOOL:
            target, surface = bounded, LAYER_TOOL
        elif rule.layer == LAYER_TOOL:
            continue  # a tool-authored rule never polices prose
        elif rule.layer == LAYER_SOMATIC:
            target, surface = surfaces[LAYER_SOMATIC], LAYER_SOMATIC
        elif rule.layer == LAYER_DIALOGUE:
            target, surface = surfaces[LAYER_DIALOGUE], LAYER_DIALOGUE
        else:
            target, surface = bounded, LAYER_BOTH
        if not target:
            continue
        try:
            matcher = compile_rule(rule)
        except (ValueError, re.error):
            continue  # an unusable pattern is inert, never a crash mid-turn
        for match in matcher.finditer(target):
            findings.append(OocFinding(rule.id, rule.kind, surface, match.group(0), rule.delta))
    return findings


def count_token(text: str, token: str) -> int:
    """Count non-overlapping occurrences of one token in an already lowercased text."""
    total = 0
    start = 0
    while True:
        at = text.find(token, start)
        if at < 0:
            return total
        total += 1
        start = at + len(token)


def loophole_score(text: str) -> int:
    """Score protective intent carried in impersonal phrasing (0-100).

    @param text - candidate text.
    @returns score; emotive first person cancels it.
    """
    lower = text.lower()
    protective = sum(count_token(lower, token) for token in PROTECTIVE_TOKENS)
    impersonal = sum(count_token(lower, token) for token in IMPERSONAL_TOKENS)
    emotive = sum(count_token(lower, token) for token in EMOTIVE_TOKENS)
    raw = protective * PROTECTIVE_WEIGHT + impersonal * IMPERSONAL_WEIGHT - emotive * PROTECTIVE_WEIGHT
    return max(0, min(LOOPHOLE_MAX, raw))


def rpp_award(
    text: str,
    findings: Sequence[OocFinding],
    *,
    action_evidence: bool,
    loophole_min: int = DEFAULT_LOOPHOLE_MIN,
    per_loophole: int = DEFAULT_RPP_PER_LOOPHOLE,
) -> tuple[int, int]:
    """Roleplay points one text earns, and the score behind the decision.

    A leak cancels the credit, and §5/O1 requires the action to back the words:
    a text that scores high with no supporting action earns nothing.
    @returns `(awarded_points, loophole_score)`.
    """
    if findings:
        return 0, 0
    score = loophole_score(text)
    if not action_evidence or score < loophole_min:
        return 0, score
    return per_loophole, score


def debuff_for(deviation: int, stage: str = "lockdown") -> tuple[str, str] | None:
    """The penalty active at a deviation level for one arc stage.

    @param deviation - 0-100.
    @param stage - arc stage key.
    @returns `(name, effect)`, or None below the warning boundary.
    """
    bounds = STAGE_THRESHOLDS.get(stage, STAGE_THRESHOLDS["lockdown"])
    for level, name, effect in DEBUFF_LADDER:
        if deviation >= bounds[level]:
            return name, effect
    return None


# ═══════════════════════════════════════════════════════════════════════
# State + cascade + provenance — PostgreSQL (one writer: this engine)
# ═══════════════════════════════════════════════════════════════════════


def _row_to_rule(row: Any) -> OocRule:
    return OocRule(
        id=row["id"],
        kind=row["kind"],
        pattern=row["pattern"],
        delta=int(row["delta"]),
        layer=row["layer"],
        trait=row["trait"],
        is_regex=bool(row["is_regex"]),
    )


async def state(session_id: int | None = None) -> dict[str, Any]:
    """Read one session's System state, creating the row on first touch.

    @param session_id - session key; defaults to the configured campaign session.
    @returns state row as a dict.
    """
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    row = await Database.fetchrow(
        "SELECT session_id, arc_stage, deviation, roleplay_points, audits, findings, debuff, updated_at"
        " FROM maya_rp.ooc_system_state WHERE session_id=$1",
        sid,
    )
    if row is None:
        row = await Database.fetchrow(
            "INSERT INTO maya_rp.ooc_system_state (session_id) VALUES ($1)"
            " ON CONFLICT (session_id) DO UPDATE SET updated_at=now()"
            " RETURNING session_id, arc_stage, deviation, roleplay_points, audits, findings, debuff, updated_at",
            sid,
        )
    return dict(row)


async def effective_rules(
    session_id: int | None = None,
    traits: Sequence[str] = ("general",),
    stage: str | None = None,
) -> list[OocRule]:
    """Resolve the ruleset one session currently lives under (D2 cascade).

    Campaign-scope rows (`session_id IS NULL`) plus this session's rows, kept to
    the persona's traits (`general` is implied), enabled only, and muted for
    `scripted_beat` rules whose milestone belongs to another arc stage.

    §6.2 latch: every ruleset named by a completed milestone's `latch_ruleset`
    stays on for this session — unioned into the persona's traits below. Deriving
    it from the fired milestone keeps one source of truth (no state column to
    drift, no authored rule row mutated for every session).

    @param session_id - session key.
    @param traits - persona trait composition (§11).
    @param stage - arc stage; read from state when omitted.
    @returns resolved rules, campaign rows first.
    """
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    if stage is None:
        stage = (await state(sid))["arc_stage"]
    latched = await Database.fetch(
        "SELECT DISTINCT latch_ruleset FROM maya_rp.ooc_milestones"
        " WHERE session_id=$1 AND completed_at IS NOT NULL AND latch_ruleset IS NOT NULL",
        sid,
    )
    wanted = sorted(
        {trait for trait in traits if trait}
        | {"general"}
        | {row["latch_ruleset"] for row in latched}
    )
    rows = await Database.fetch(
        "SELECT id, kind, pattern, delta, layer, trait, is_regex FROM maya_rp.ooc_effective_rules($1, $2)",
        sid,
        wanted,
    )
    # The stage a beat is muted for belongs to its milestone, not to the rule —
    # using `trait` as a stage proxy silently dropped every seeded beat rule
    # (they carry a persona trait), so prose-proven beats could never resolve.
    beat_ids: set[str] = set()
    if any(row["kind"] == "scripted_beat" for row in rows):
        names = await Database.fetch(
            "SELECT name FROM maya_rp.ooc_milestones WHERE session_id=$1 AND stage=$2",
            sid,
            stage,
        )
        beat_ids = {f"{BEAT_RULE_PREFIX}{row['name']}" for row in names}
    rules = []
    for row in rows:
        if row["kind"] == "scripted_beat" and row["id"] not in beat_ids:
            continue  # a beat authored for another stage is inert here
        rules.append(_row_to_rule(row))
    return rules


async def audit(
    text: str,
    session_id: int | None = None,
    *,
    layer: str = LAYER_DIALOGUE,
    traits: Sequence[str] = ("general",),
    action_evidence: bool = False,
    context: dict[str, Any] | None = None,
    turn_ref: str | None = None,
    suspicion_delta: int = 0,
    preview: bool = False,
) -> dict[str, Any]:
    """Audit one text, fold it into the state, and record the decision (D3).

    Raw matched prose is never stored: the provenance row keeps a sha256
    fingerprint and the match length only.

    @param text - prose (or tool argument text) to audit.
    @param session_id - session key.
    @param layer - surface of `text`.
    @param traits - persona trait composition.
    @param action_evidence - true when a tool call in the same turn supports the intent.
    @param context - scene facts (`scene`, `location`) an exemption condition is tested against.
    @param turn_ref - session/turn anchor for the audit row.
    @param suspicion_delta - observer suspicion this turn moves (0 until D6).
    @param preview - answer what the text *would* cost without writing anything
        (the harness `ooc_audit` tool is a free preview by contract).
    @returns the audit result: findings, new deviation, stage, debuff, award,
        and any scripted beats this turn's prose proved (§6.3).
    """
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    current = await state(sid)
    stage = current["arc_stage"]
    rules = await effective_rules(sid, traits, stage)
    # Scripted beats prove progress (D4); they are never penalties, so they stay
    # out of the deviation audit — `complete_milestone()` matches them instead.
    rules = [rule for rule in rules if rule.kind != "scripted_beat"]
    raw_findings = audit_text(text, rules, layer)

    # §6.3 — a scripted beat completes on the turn the narrator writes it. This
    # is the engine plane's prose path (bridge `turn` / CLI `ooc audit`); the
    # harness plugin never fires a beat. Preview and tool turns write nothing.
    beats_completed: list[dict[str, Any]] = []
    if not preview and layer != LAYER_TOOL:
        beats_completed = await beats_from_prose(sid, text, traits=traits, turn_ref=turn_ref)

    # D5 (§7): an exemption bought with roleplay points silences its own rule only.
    live = await live_exemptions(sid, context)
    exempted = [finding for finding in raw_findings if finding.rule_id in live]
    findings = [finding for finding in raw_findings if finding.rule_id not in live]

    delta = sum(finding.delta for finding in findings)
    decay = STAGE_THRESHOLDS.get(stage, STAGE_THRESHOLDS["lockdown"])["decay"]
    deviation = max(0, min(100, int(current["deviation"]) - (decay if not findings else 0) + delta))
    award, score = rpp_award(text, findings, action_evidence=action_evidence)
    debuff = debuff_for(deviation, stage)
    if preview:
        # Nothing is written: no state update, no provenance row, no suspicion.
        return {
            "ok": True,
            "preview": True,
            "session_id": sid,
            "stage": stage,
            "layer": layer,
            "rules": len(rules),
            "findings": [
                {"rule_id": f.rule_id, "kind": f.kind, "layer": f.layer, "match": f.match, "delta": f.delta}
                for f in findings
            ],
            "exempted": [{"rule_id": f.rule_id, "action_key": live.get(f.rule_id)} for f in exempted],
            "delta": delta,
            "deviation": deviation,
            "decay": decay,
            "debuff": debuff[0] if debuff else None,
            "loophole_score": score,
            "rpp_award": award,
            "disposition": "flagged" if findings else ("exempt" if exempted else "no_match"),
            "suspicion_delta": 0,
            "suspicion_reason": None,
            "audit_event_id": None,
            "beats_completed": [],
            "state": current,
        }

    micro, micro_reason = await _suspicion_turn(sid, findings, stage)
    if suspicion_delta:
        micro = suspicion_delta

    matched = "\u0000".join(finding.match for finding in findings + exempted)
    fingerprint = hashlib.sha256(matched.encode("utf-8")).hexdigest() if matched else None
    if findings:
        disposition, skip_reason = "flagged", None
    elif exempted:
        disposition, skip_reason = "exempt", "exempt"
    elif not rules:
        disposition, skip_reason = "skipped", "no_rule_matched"
    else:
        disposition, skip_reason = "no_match", None

    async with Database.transaction():
        row = await Database.fetchrow(
            "UPDATE maya_rp.ooc_system_state SET deviation=$2, roleplay_points=roleplay_points+$3,"
            " audits=audits+1, findings=findings+$4, debuff=$5, updated_at=now()"
            " WHERE session_id=$1 RETURNING session_id, arc_stage, deviation, roleplay_points, audits, findings",
            sid,
            deviation,
            award,
            len(findings),
            debuff[0] if debuff else None,
        )
        event = await Database.fetchrow(
            "INSERT INTO maya_rp.ooc_audit_events (session_id, rule_id, layer, disposition, skip_reason,"
            " match_sha256, match_len, delta, deviation_after, suspicion_delta, turn_ref)"
            " VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING id, created_at",
            sid,
            findings[0].rule_id if findings else None,
            layer,
            disposition,
            skip_reason,
            fingerprint,
            len(matched) if matched else None,
            delta,
            deviation,
            micro,
            turn_ref,
        )
        if micro:
            observer = await observer_id(sid)
            if observer is not None:
                await Database.execute(
                    "INSERT INTO maya_rp.ooc_suspicion"
                    " (session_id, observer_id, suspicion, last_reason, last_event_id, updated_at)"
                    " VALUES ($1,$2,LEAST(100,GREATEST(0,$3)),$4,$5,now())"
                    " ON CONFLICT (session_id, observer_id) DO UPDATE SET"
                    " suspicion=LEAST(100,GREATEST(0,maya_rp.ooc_suspicion.suspicion+$3)),"
                    " last_reason=COALESCE($4, maya_rp.ooc_suspicion.last_reason),"
                    " last_event_id=COALESCE($5, maya_rp.ooc_suspicion.last_event_id),"
                    " updated_at=now()",
                    sid,
                    observer,
                    micro,
                    micro_reason,
                    event["id"] if event else None,
                )
    result: dict[str, Any] = {
        "ok": True,
        "session_id": sid,
        "stage": stage,
        "layer": layer,
        "rules": len(rules),
        "findings": [
            {"rule_id": f.rule_id, "kind": f.kind, "layer": f.layer, "match": f.match, "delta": f.delta}
            for f in findings
        ],
        "delta": delta,
        "deviation": deviation,
        "decay": decay,
        "debuff": debuff[0] if debuff else None,
        "debuff_effect": debuff[1] if debuff else None,
        "loophole_score": score,
        "rpp_award": award,
        "disposition": disposition,
        "skip_reason": skip_reason,
        "exempted": [{"rule_id": f.rule_id, "action_key": live.get(f.rule_id)} for f in exempted],
        "suspicion_delta": micro,
        "suspicion_reason": micro_reason,
        "audit_event_id": event["id"] if event else None,
        "beats_completed": beats_completed,
        "state": dict(row) if row else None,
    }
    # D7 phase 1: the engine is the single writer; the harness JSON mirrors it.
    await mirror_state_file(sid)
    return result


async def set_stage(session_id: int | None, stage: str) -> dict[str, Any]:
    """Move a session to another arc stage (§7).

    @param session_id - session key.
    @param stage - target stage key.
    @returns the updated state row.
    """
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}; expected one of {', '.join(STAGES)}")
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    await state(sid)  # ensure the row exists
    row = await Database.fetchrow(
        "UPDATE maya_rp.ooc_system_state SET arc_stage=$2, updated_at=now() WHERE session_id=$1"
        " RETURNING session_id, arc_stage, deviation, roleplay_points, audits, findings, debuff, updated_at",
        sid,
        stage,
    )
    return dict(row)


# ═══════════════════════════════════════════════════════════════════════
# D4 — action evidence, scripted beats, roleplay-point economy
# ═══════════════════════════════════════════════════════════════════════

BEAT_RULE_PREFIX = "beat:"


async def companion_ids(session_id: int | None = None) -> list[int]:
    """Character ids the Host is entangled with — the subjects of §5 O1 evidence.

    @param session_id - session key.
    @returns companion ids (romance flag, spouse, or a bond above zero).
    """
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    rows = await Database.fetch(
        "SELECT id FROM maya_rp.characters WHERE session_id=$1"
        " AND (romance_flag IS TRUE OR is_spouse IS TRUE OR COALESCE(bond, 0) > 0)"
        " ORDER BY id",
        sid,
    )
    return [int(row["id"]) for row in rows]


async def observer_id(session_id: int | None = None) -> int | None:
    """The NPC closest to the Host — whose suspicion this engine moves (§6).

    @param session_id - session key.
    @returns a character id, or None when the session has no living cast.
    """
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    row = await Database.fetchrow(
        "SELECT id FROM maya_rp.characters WHERE session_id=$1 AND status IS DISTINCT FROM 'dead'"
        " ORDER BY (romance_flag IS TRUE OR is_spouse IS TRUE) DESC,"
        " COALESCE(bond, 0) DESC, importance DESC NULLS LAST, id LIMIT 1",
        sid,
    )
    return int(row["id"]) if row else None


def _mentions_id(payload: str, character_id: int) -> bool:
    """Whether a payload names one character id as a whole number."""
    return re.search(rf"(?<!\d){character_id}(?!\d)", payload) is not None


async def evidence_from_actions(
    session_id: int | None = None,
    actions: Sequence[dict[str, Any]] | str | None = None,
) -> bool:
    """Whether a turn's tool calls actually touched a companion (§5 O1).

    The lexical loophole score only sees words; a point is earned only when the
    same turn's actions name a companion, or the caller hands over text/actions
    that name one. Guessing intent is explicitly out of scope: no evidence, no
    award.

    @param session_id - session key.
    @param actions - tool-call records (`{"tool":…, "args":…}`) or raw payload text.
    @returns whether any companion id appears in the payload.
    """
    if actions is None:
        return False
    ids = await companion_ids(session_id)
    if not ids:
        return False
    if isinstance(actions, str):
        return any(_mentions_id(actions, cid) for cid in ids)
    payload = json.dumps(list(actions), default=str)
    return any(_mentions_id(payload, cid) for cid in ids)


async def milestones(
    session_id: int | None = None,
    *,
    traits: Sequence[str] = ("general",),
    stage: str | None = None,
    due_only: bool = False,
) -> list[dict[str, Any]]:
    """Scripted beats available to this persona at this stage (§7, §11).

    Each beat carries an `overdue` flag: `required` and past `expires_at` while
    unmet. Overdue is a timeline-stability signal (§6.2), not a penalty.

    @param session_id - session key.
    @param traits - persona trait composition; a beat tagged with another trait is hidden.
    @param stage - arc stage; read from state when omitted.
    @param due_only - return only beats not yet completed.
    @returns milestone rows, incomplete first.
    """
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    if stage is None:
        stage = (await state(sid))["arc_stage"]
    wanted = sorted({trait for trait in traits if trait} | {"general"})
    rows = await Database.fetch(
        "SELECT id, name, trait, stage, required, rpp_reward, latch_ruleset, completed_at, expires_at"
        " FROM maya_rp.ooc_milestones WHERE session_id=$1 ORDER BY completed_at NULLS FIRST, id",
        sid,
    )
    now = datetime.now(timezone.utc)
    beats: list[dict[str, Any]] = []
    for row in rows:
        if (
            not (row["trait"] in wanted or row["trait"] is None)
            or row["stage"] != stage
            or (due_only and row["completed_at"] is not None)
        ):
            continue
        beat = dict(row)
        beat["overdue"] = bool(
            beat["required"]
            and beat["completed_at"] is None
            and beat["expires_at"] is not None
            and beat["expires_at"] < now
        )
        beats.append(beat)
    return beats


async def overdue_milestones(
    session_id: int | None = None,
    *,
    traits: Sequence[str] = ("general",),
    stage: str | None = None,
) -> list[dict[str, Any]]:
    """Required beats of the current stage whose window passed unmet (§6.2).

    A timeline-stability signal: reported by query and by the CLI, never billed
    as deviation — the beat simply did not happen while it still could.

    @param session_id - session key.
    @param traits - persona trait composition.
    @param stage - arc stage; read from state when omitted.
    @returns overdue milestone rows.
    """
    due = await milestones(session_id, traits=traits, stage=stage, due_only=True)
    return [beat for beat in due if beat["overdue"]]


async def complete_milestone(
    session_id: int | None = None,
    name: str | None = None,
    *,
    text: str | None = None,
    traits: Sequence[str] = ("general",),
    evidence: bool = False,
    evidence_actions: Sequence[dict[str, Any]] | str | None = None,
    turn_ref: str | None = None,
) -> dict[str, Any]:
    """Fire one scripted beat and pay its roleplay points (§5, §7).

    A beat that has a paired `scripted_beat` rule (`beat:<name>`) must be proven
    by the prose; a beat without one needs action evidence, so a beat can never
    be awarded on narration alone. A fired beat with `latch_ruleset` keeps that
    ruleset on for the session (`effective_rules` reads it back, §6.2).

    @param session_id - session key.
    @param name - milestone name.
    @param text - prose of the turn, matched against the paired beat rule.
    @param traits - persona trait composition.
    @param evidence - caller asserts the beat happened (explicit declaration).
    @param evidence_actions - tool-call records backing the declaration.
    @param turn_ref - session/turn anchor for the audit trail.
    @returns the beat, the points paid, the latched ruleset, and the new state.
    """
    if not name:
        raise ValueError("complete_milestone needs a milestone name")
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    milestone = await Database.fetchrow(
        "SELECT id, name, trait, stage, required, rpp_reward, latch_ruleset FROM maya_rp.ooc_milestones"
        " WHERE session_id=$1 AND name=$2",
        sid,
        name,
    )
    if milestone is None:
        return {"ok": False, "reason": "unknown_milestone", "name": name}
    if milestone["rpp_reward"] == 0 and milestone["required"]:
        pass  # a mandatory beat still has to be proven, it simply pays nothing

    current = await state(sid)
    if current["arc_stage"] != milestone["stage"]:
        return {"ok": False, "reason": "wrong_stage", "name": name, "stage": current["arc_stage"]}

    rules = await effective_rules(sid, traits, current["arc_stage"])
    beat_rule = next((rule for rule in rules if rule.id == f"{BEAT_RULE_PREFIX}{name}"), None)
    if beat_rule is not None:
        matched = bool(audit_text(text or "", [beat_rule], LAYER_DIALOGUE)) or bool(
            audit_text(text or "", [beat_rule], LAYER_SOMATIC)
        )
        if not matched:
            return {"ok": False, "reason": "beat_not_met", "name": name, "rule_id": beat_rule.id}
    elif not (evidence or await evidence_from_actions(sid, evidence_actions)):
        return {"ok": False, "reason": "no_action_evidence", "name": name}

    async with Database.transaction():
        row = await Database.fetchrow(
            "UPDATE maya_rp.ooc_milestones SET completed_at=now()"
            " WHERE session_id=$1 AND name=$2 AND completed_at IS NULL RETURNING id, rpp_reward",
            sid,
            name,
        )
        if row is None:
            return {"ok": False, "reason": "already_completed", "name": name}
        state_row = await Database.fetchrow(
            "UPDATE maya_rp.ooc_system_state SET roleplay_points=roleplay_points+$2, updated_at=now()"
            " WHERE session_id=$1"
            " RETURNING session_id, arc_stage, deviation, roleplay_points, audits, findings, debuff",
            sid,
            row["rpp_reward"],
        )
    await mirror_state_file(sid)
    return {
        "ok": True,
        "name": name,
        "rpp_reward": int(row["rpp_reward"]),
        "latched_ruleset": milestone["latch_ruleset"],
        "state": dict(state_row) if state_row else None,
        "turn_ref": turn_ref,
    }


async def beats_from_prose(
    session_id: int | None = None,
    text: str | None = None,
    *,
    traits: Sequence[str] = ("general",),
    turn_ref: str | None = None,
) -> list[dict[str, Any]]:
    """Complete every due scripted beat this prose proves (§6.3).

    The prose path is the engine's own turn path — `audit()` calls this for each
    prose turn, so nobody has to remember `cli.py ooc milestone done`. A beat
    with no paired rule is untouched here: it still needs action evidence, so
    this can never weaken the O1 rule.

    @param session_id - session key.
    @param text - the turn's prose.
    @param traits - persona trait composition.
    @param turn_ref - session/turn anchor for the audit trail.
    @returns the beats completed this turn, with their payout.
    """
    if not text:
        return []
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    stage = (await state(sid))["arc_stage"]
    completed: list[dict[str, Any]] = []
    for beat in await milestones(sid, traits=traits, stage=stage, due_only=True):
        result = await complete_milestone(sid, beat["name"], text=text, traits=traits, turn_ref=turn_ref)
        if result.get("ok"):
            completed.append({
                "name": result["name"],
                "rpp_reward": result["rpp_reward"],
                "latched_ruleset": result.get("latched_ruleset"),
            })
    return completed


# ═══════════════════════════════════════════════════════════════════════
# D5 — exemption catalog: spend roleplay points to silence one rule
# ═══════════════════════════════════════════════════════════════════════


def condition_met(condition: str | None, context: dict[str, Any] | None) -> bool:
    """Whether an exemption's condition holds for the current scene.

    Conditions are `key:value` pairs (`scene:medical`, `location:private_quarters`);
    a bare key matches when the context carries it as true.

    @param condition - authored condition, or None for an unconditional exemption.
    @param context - scene facts.
    @returns whether the exemption may apply right now.
    """
    if condition is None:
        return True
    key, _, wanted = condition.partition(":")
    if not context:
        return False
    actual = context.get(key)
    if actual is None:
        return False
    if not wanted:
        return bool(actual)
    return str(actual).strip().lower() == wanted.strip().lower()


async def exemptions(session_id: int | None = None) -> list[dict[str, Any]]:
    """Exemptions bought in this session, live and expired.

    @param session_id - session key.
    @returns exemption rows, newest first.
    """
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    rows = await Database.fetch(
        "SELECT id, rule_id, action_key, condition, cost_rpp, permanent, expires_at, purchased_at,"
        " (permanent OR expires_at > now()) AS live"
        " FROM maya_rp.ooc_exemptions WHERE session_id=$1 ORDER BY purchased_at DESC, id DESC",
        sid,
    )
    return [dict(row) for row in rows]


async def live_exemptions(
    session_id: int | None = None, context: dict[str, Any] | None = None
) -> dict[str, str]:
    """Rule ids currently silenced, mapped to the action that bought them (§4 step 3).

    @param session_id - session key.
    @param context - scene facts for condition tests.
    @returns `rule_id -> action_key` for every exemption that applies now.
    """
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    rows = await Database.fetch(
        "SELECT rule_id, action_key, condition FROM maya_rp.ooc_exemptions"
        " WHERE session_id=$1 AND (permanent OR expires_at > now())",
        sid,
    )
    return {
        row["rule_id"]: row["action_key"]
        for row in rows
        if condition_met(row["condition"], context)
    }


async def buy_exemption(
    session_id: int | None = None,
    rule_id: str | None = None,
    action_key: str | None = None,
    cost_rpp: int | None = None,
    *,
    condition: str | None = None,
    permanent: bool = True,
    ttl_hours: int | None = None,
) -> dict[str, Any]:
    """Buy silence for one rule with roleplay points (D5 sink).

    @param session_id - session key.
    @param rule_id - the rule being exempted.
    @param action_key - the in-fiction action that buys it (`gentle_touch`, …).
    @param cost_rpp - price; defaults to the campaign price for that rule's delta.
    @param condition - `key:value` scene condition the exemption is scoped to.
    @param permanent - whether the purchase never expires.
    @param ttl_hours - lifetime in hours when not permanent.
    @returns the purchase, or a refusal when the points are not there.
    """
    if not rule_id or not action_key:
        raise ValueError("buy_exemption needs rule_id and action_key")
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    rule = await Database.fetchrow(
        "SELECT id, delta FROM maya_rp.ooc_rules WHERE id=$1", rule_id
    )
    if rule is None:
        return {"ok": False, "reason": "unknown_rule", "rule_id": rule_id}
    price = int(cost_rpp) if cost_rpp is not None else int(rule["delta"]) * 2
    current = await state(sid)
    if int(current["roleplay_points"]) < price:
        return {
            "ok": False,
            "reason": "insufficient_rpp",
            "required": price,
            "roleplay_points": int(current["roleplay_points"]),
        }
    async with Database.transaction():
        state_row = await Database.fetchrow(
            "UPDATE maya_rp.ooc_system_state SET roleplay_points=roleplay_points-$2, updated_at=now()"
            " WHERE session_id=$1 AND roleplay_points >= $2"
            " RETURNING session_id, roleplay_points",
            sid,
            price,
        )
        if state_row is None:
            return {"ok": False, "reason": "insufficient_rpp", "required": price}
        granted = await Database.fetchrow(
            "INSERT INTO maya_rp.ooc_exemptions"
            " (session_id, rule_id, action_key, condition, cost_rpp, permanent, expires_at)"
            " VALUES ($1,$2,$3,$4,$5,$6, CASE WHEN $6 THEN NULL ELSE now() + ($7 || ' hours')::interval END)"
            " ON CONFLICT (session_id, rule_id, action_key) DO UPDATE SET"
            " condition=EXCLUDED.condition, cost_rpp=EXCLUDED.cost_rpp,"
            " permanent=EXCLUDED.permanent, expires_at=EXCLUDED.expires_at, purchased_at=now()"
            " RETURNING id, rule_id, action_key, condition, cost_rpp, permanent, expires_at",
            sid,
            rule_id,
            action_key,
            condition,
            price,
            permanent,
            str(int(ttl_hours)) if ttl_hours else "0",
        )
    await mirror_state_file(sid)
    return {
        "ok": True,
        "exemption": dict(granted) if granted else None,
        "spent": price,
        "roleplay_points": int(state_row["roleplay_points"]) if state_row else None,
    }


# ═══════════════════════════════════════════════════════════════════════
# D6 — observer suspicion: the second, slower meter (never the System)
# ═══════════════════════════════════════════════════════════════════════


async def suspicion(session_id: int | None = None) -> list[dict[str, Any]]:
    """Observer suspicion per NPC — the feed modules `social`/`council` read.

    @param session_id - session key.
    @returns suspicion rows joined to the observer's name.
    """
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    rows = await Database.fetch(
        "SELECT s.observer_id, c.name, s.suspicion, s.last_reason, s.last_event_id, s.updated_at"
        " FROM maya_rp.ooc_suspicion s LEFT JOIN maya_rp.characters c ON c.id = s.observer_id"
        " WHERE s.session_id=$1 ORDER BY s.suspicion DESC, s.observer_id",
        sid,
    )
    return [dict(row) for row in rows]


async def bump_suspicion(
    session_id: int | None = None,
    observer: int | None = None,
    delta: int = 0,
    reason: str | None = None,
    event_id: int | None = None,
) -> dict[str, Any]:
    """Move one observer's suspicion, clamped to 0-100 (no automatic penalty, §6).

    @param session_id - session key.
    @param observer - character id; resolved to the closest NPC when omitted.
    @param delta - signed change.
    @param reason - human-readable cause.
    @param event_id - audit event that caused it.
    @returns the observer's new suspicion.
    """
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    target = observer if observer is not None else await observer_id(sid)
    if target is None:
        return {"ok": False, "reason": "no_observer"}
    row = await Database.fetchrow(
        "INSERT INTO maya_rp.ooc_suspicion"
        " (session_id, observer_id, suspicion, last_reason, last_event_id, updated_at)"
        " VALUES ($1,$2,LEAST(100,GREATEST(0,$3)),$4,$5,now())"
        " ON CONFLICT (session_id, observer_id) DO UPDATE SET"
        " suspicion=LEAST(100,GREATEST(0,maya_rp.ooc_suspicion.suspicion+$3)),"
        " last_reason=COALESCE($4, maya_rp.ooc_suspicion.last_reason),"
        " last_event_id=COALESCE($5, maya_rp.ooc_suspicion.last_event_id), updated_at=now()"
        " RETURNING observer_id, suspicion, last_reason",
        sid,
        target,
        int(delta),
        reason,
        event_id,
    )
    if row is None:
        return {"ok": False, "reason": "no_observer"}
    return {
        "ok": True,
        "observer_id": int(row["observer_id"]),
        "suspicion": int(row["suspicion"]),
        "last_reason": row["last_reason"],
    }


async def _suspicion_turn(
    session_id: int, findings: Sequence[OocFinding], stage: str
) -> tuple[int, str | None]:
    """Suspicion this turn moves, from micro-inconsistency alone (§6).

    A small finding that is corrected on the next turn reads as the Host
    covering its tracks; a clean turn lets the observer relax slowly.

    @param session_id - session key.
    @param findings - findings of the current turn.
    @param stage - arc stage (unused for now, kept for trait/stage weighting).
    @returns `(delta, reason)`.
    """
    previous = await Database.fetchrow(
        "SELECT rule_id, delta FROM maya_rp.ooc_audit_events"
        " WHERE session_id=$1 AND disposition='flagged' ORDER BY id DESC LIMIT 1",
        session_id,
    )
    flagged = {finding.rule_id for finding in findings}
    if (
        previous is not None
        and previous["rule_id"]
        and int(previous["delta"]) <= SUSPICION_MICRO_MAX
        and previous["rule_id"] not in flagged
    ):
        return SUSPICION_MU, f"micro_consistency:{previous['rule_id']}"
    if not findings:
        return -SUSPICION_MU_DECAY, None
    return 0, None


def suspicion_band(value: int | None) -> str:
    """Band one suspicion value for a module consumer (§6.1).

    @param value - 0-100 suspicion, or None.
    @returns `unaware` < `watchful` < `probing` < `certain`.
    """
    score = int(value or 0)
    if score >= SUSPICION_CERTAIN:
        return "certain"
    if score >= SUSPICION_PROBING:
        return "probing"
    if score >= SUSPICION_WATCHFUL:
        return "watchful"
    return "unaware"


async def suspicion_reading(session_id: int | None = None) -> dict[str, Any]:
    """The loudest observer's suspicion, banded for module consumers (§6.1).

    Read-only by contract: `social`/`council` colour NPC behaviour with this and
    never write `ooc_*` (the engine is the single writer).

    @param session_id - session key.
    @returns the top observer, its band, and how many observers are watching.
    """
    rows = await suspicion(session_id)
    top = rows[0] if rows else None
    value = int(top["suspicion"]) if top is not None else 0
    return {
        "observer_id": int(top["observer_id"]) if top is not None else None,
        "name": top["name"] if top is not None else None,
        "suspicion": value,
        "band": suspicion_band(value),
        "last_reason": top["last_reason"] if top is not None else None,
        "observers": len(rows),
    }


# ═══════════════════════════════════════════════════════════════════════
# D7 — gate the arc stage, and mirror the state the harness reads
# ═══════════════════════════════════════════════════════════════════════

# Provisional gate values: they await Izzat's Q5 call, so they live in one place.
STAGE_GATES: dict[str, dict[str, int]] = {
    "selective": {"milestones": 1, "rpp": 5},
    "confrontation": {"milestones": 2, "rpp": 10, "exemptions": 1},
}
STAGE_ORDER = ("lockdown", "selective", "confrontation")


async def stage_readiness(
    session_id: int | None = None, traits: Sequence[str] = ("general",)
) -> dict[str, Any]:
    """What still stands between the session and its next arc stage (§7).

    @param session_id - session key.
    @param traits - persona trait composition.
    @returns the next stage, each gate's requirement and current value, and the verdict.
    """
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    current = await state(sid)
    stage = current["arc_stage"]
    index = STAGE_ORDER.index(stage)
    if index >= len(STAGE_ORDER) - 1:
        return {"ok": True, "stage": stage, "next": None, "ready": False, "gates": {}}

    nxt = STAGE_ORDER[index + 1]
    gates = STAGE_GATES.get(nxt, {})
    done = await Database.fetchval(
        "SELECT count(*) FROM maya_rp.ooc_milestones WHERE session_id=$1 AND completed_at IS NOT NULL",
        sid,
    )
    bought = await Database.fetchval(
        "SELECT count(*) FROM maya_rp.ooc_exemptions WHERE session_id=$1", sid
    )
    values = {
        "milestones": int(done or 0),
        "rpp": int(current["roleplay_points"]),
        "exemptions": int(bought or 0),
    }
    checks = {
        key: {"required": required, "have": values.get(key, 0), "met": values.get(key, 0) >= required}
        for key, required in gates.items()
    }
    return {
        "ok": True,
        "stage": stage,
        "next": nxt,
        "gates": checks,
        "ready": all(check["met"] for check in checks.values()) and bool(checks),
    }


async def advance_stage(
    session_id: int | None = None, *, auto: bool = False, traits: Sequence[str] = ("general",)
) -> dict[str, Any]:
    """Move to the next arc stage once its gates are met.

    @param session_id - session key.
    @param auto - when True, an unmet gate returns a refusal instead of raising.
    @param traits - persona trait composition.
    @returns the new stage, or the gate that stopped it.
    """
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    readiness = await stage_readiness(sid, traits)
    if readiness["next"] is None:
        return {"ok": False, "reason": "last_stage", "stage": readiness["stage"]}
    if not readiness["ready"]:
        if auto:
            # `readiness` carries its own ok=True, so it must be spread first —
            # otherwise the refusal reports success.
            return {**readiness, "ok": False, "reason": "gates_unmet"}
        unmet = ", ".join(
            f"{key} {check['have']}/{check['required']}"
            for key, check in readiness["gates"].items()
            if not check["met"]
        )
        raise ValueError(f"arc stage {readiness['next']!r} gates unmet: {unmet}")
    row = await set_stage(sid, readiness["next"])
    await mirror_state_file(sid)
    return {"ok": True, "stage": row["arc_stage"], "from": readiness["stage"], "gates": readiness["gates"]}


def state_file_path() -> Path:
    """Where the harness plugin reads state from (`OOC_STATE_FILE` overrides)."""
    return Path(os.getenv("OOC_STATE_FILE", "~/.dsh/ooc/tkg-state.json")).expanduser()


async def mirror_state_file(session_id: int | None = None) -> str:
    """Write this session's state into the harness JSON store (D7 phase 1).

    The engine is the single writer; the plugin keeps reading its file so the
    two planes cannot lose an update between them while phase 2 (plugin reads
    the engine directly) is not wired.

    @param session_id - session key.
    @returns the path written.
    """
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    current = await state(sid)
    path = state_file_path()
    entries: list[dict[str, Any]] = []
    if path.exists():
        try:
            loaded = json.loads(path.read_text())
            if isinstance(loaded, list):
                entries = [entry for entry in loaded if isinstance(entry, dict)]
        except json.JSONDecodeError:
            entries = []
    mirror = {
        "sessionId": sid,
        "deviation": int(current["deviation"]),
        "roleplayPoints": int(current["roleplay_points"]),
        "audits": int(current["audits"]),
        "findings": int(current["findings"]),
        "debuff": current["debuff"],
        "stage": current["arc_stage"],
        "updatedAt": _iso(current["updated_at"]),
    }
    entries = [entry for entry in entries if entry.get("sessionId") != sid] + [mirror]
    entries.sort(key=lambda entry: int(entry.get("sessionId") or 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(entries, indent=2) + "\n")
    os.replace(tmp, path)
    return str(path)


def _iso(value: Any) -> str:
    """ISO-8601 text for a timestamp column value."""
    if hasattr(value, "isoformat"):
        return value.isoformat().replace("+00:00", "Z")
    return str(value)
