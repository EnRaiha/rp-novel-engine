#!/usr/bin/env python3
"""INTENT LAYER — Intent-Driven Architecture (CPU-first, LLM-as-parser).

Blueprint: Player text → LLM parses to strict JSON → CPU validates + resolves
→ LLM narrates. The CPU is the ONLY source of truth. This module is the CPU
side of the intent pipeline:

  PlayerIntent (Pydantic strict schema) — what the LLM MUST output
  validate_intent() — CPU checks intent against RAM/DB state
  resolve_intent_dispatch() — routes to the right module resolver

Golden rules enforced here:
  1. LLM never touches state — only produces intent JSON.
  2. Guardrails: every field validated against engine state before resolution.
  3. CPU math decides outcomes; narration is decoration only.
"""
from __future__ import annotations
import asyncio, json
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator
from core.db import Database
from core.config import Config


class PlayerIntent(BaseModel):
    """Strict schema the LLM must emit. CPU validates everything."""

    model_config = {"extra": "forbid"}  # no hallucinated keys

    action_type: Literal[
        "attack", "move", "talk", "use_item", "look",
        "deploy", "trade", "build", "diplomacy", "explore",
        "intel", "assign", "roll", "invalid",
    ] = Field(description="Standard game action")
    target: Optional[str] = Field(default=None, description="Entity/system/ship targeted")
    item_used: Optional[str] = Field(default=None, description="Item/unit being used")
    creative_intent: Optional[str] = Field(default=None, description="Non-standard goal, e.g. 'weld door shut'")
    dialogue: Optional[str] = Field(default=None, description="What the player says aloud")
    amount: Optional[int] = Field(default=None, ge=0, description="Numeric parameter (credits, ships, days)")
    raw_text: Optional[str] = Field(default=None, description="Original player input (fallback)")

    @field_validator("target", "item_used", "creative_intent", "dialogue")
    @classmethod
    def strip_blanks(cls, v):
        if v is not None and not str(v).strip():
            return None
        return v


# ─── Intent registry: action → module resolver ───────────────────────────
RESOLVERS: dict[str, str] = {
    "attack": "modules.battle.resolve_intent",
    "move": "modules.movement.move_fleet",
    "deploy": "modules.fleet_expansion (workflow script)",
    "build": "modules.build_queue",
    "trade": "modules.trade",
    "diplomacy": "modules.diplomacy",
    "explore": "modules.exploration",
    "intel": "modules.espionage",
    "assign": "modules.crew_system.assign",
    "roll": "cli.roll",
    "talk": "narrative-only (no CPU state change)",
    "look": "narrative-only (context read)",
    "use_item": "modules.items (creative → generic resolver)",
    "invalid": "reject — ask player to rephrase",
}


# ─── Guardrail: does the player actually have this? ──────────────────────
async def validate_intent(session_id: int, intent: PlayerIntent) -> tuple[bool, str, dict]:
    """CPU-side validation against engine state. Returns (ok, error, context)."""
    ctx: dict = {"session_id": session_id}

    # 1. inventory check (item_used)
    if intent.item_used:
        have = await Database.fetchval(
            "SELECT COUNT(*) FROM maya_rp.ships WHERE session_id=$1 AND name=$2 AND status IN ('active','standby_alert')",
            session_id, intent.item_used) or 0
        have_char = await Database.fetchval(
            "SELECT COUNT(*) FROM maya_rp.characters WHERE session_id=$1 AND name=$2 AND status='active'",
            session_id, intent.item_used) or 0
        have_corp = await Database.fetchval(
            "SELECT COUNT(*) FROM maya_rp.corporations WHERE session_id=$1 AND name=$2",
            session_id, intent.item_used) or 0
        if not (have or have_char or have_corp):
            return False, f"You do not have '{intent.item_used}'.", ctx

    # 2. target existence
    if intent.target and intent.action_type in ("attack", "talk", "use_item", "trade", "diplomacy"):
        terr = await Database.fetchval(
            "SELECT id FROM maya_rp.territory WHERE session_id=$1 AND system_name ILIKE $2",
            session_id, f"%{intent.target}%")
        fac = await Database.fetchval(
            "SELECT id FROM maya_rp.factions WHERE session_id=$1 AND name ILIKE $2",
            session_id, f"%{intent.target}%")
        if not (terr or fac):
            # target may be a character or ship
            ent = await Database.fetchval(
                "SELECT COUNT(*) FROM maya_rp.characters WHERE session_id=$1 AND name ILIKE $2",
                session_id, f"%{intent.target}%")
            if not ent:
                return False, f"Target '{intent.target}' not found in the sector.", ctx

    # 3. amount sanity
    if intent.amount is not None:
        creds = await Database.fetchval(
            "SELECT credits FROM maya_rp.resources WHERE session_id=$1", session_id) or 0
        if intent.amount > creds:
            return False, f"Insufficient credits: need {intent.amount:,}, have {creds:,}.", ctx

    ctx["resolver"] = RESOLVERS.get(intent.action_type, "invalid")
    return True, "ok", ctx


# ─── Generic Resolution Framework (creative actions) ─────────────────────
async def resolve_creative(session_id: int, intent: PlayerIntent) -> dict:
    """CPU generic resolver for non-hardcoded creative intents.
    Rolls skill check; outcome decided by CPU math, narrated by LLM."""
    skill = intent.creative_intent or intent.item_used or "action"
    # simple deterministic check: 70% baseline success, 30% partial/fail
    roll = await Database.fetchval("SELECT (random()*99+1)::int")
    if roll <= 70:
        return {"success": True, "event": "creative_success", "roll": roll,
                "narrative_hint": f"{skill} succeeded."}
    elif roll <= 90:
        return {"success": True, "event": "creative_partial", "roll": roll,
                "narrative_hint": f"{skill} partially succeeded — side effect."}
    return {"success": False, "event": "creative_failed", "roll": roll,
            "narrative_hint": f"{skill} failed — no state change."}


# ─── Main dispatch: intent → CPU resolution ──────────────────────────────
async def resolve_intent_dispatch(session_id: int, intent: PlayerIntent) -> dict:
    """The ONLY entry point for player actions. Returns a Result Event."""
    # narrative-only actions need no CPU math
    if intent.action_type in ("talk", "look"):
        return {"success": True, "event": f"{intent.action_type}_handled",
                "dialogue": intent.dialogue, "narrative_only": True}

    ok, err, ctx = await validate_intent(session_id, intent)
    if not ok:
        return {"success": False, "error": err}

    # creative fallback
    if intent.creative_intent or intent.action_type == "use_item":
        return await resolve_creative(session_id, intent)

    # standard actions — route to module resolvers
    if intent.action_type == "attack":
        try:
            from modules.battle import resolve_intent
            # `resolve_intent(session_id, action, target, fleet_name="")`. This call used to pass
            # (target, item_used), so the target landed in `action`, which the resolver ignores, and
            # the item landed in `target`, which is the string the narrative and the defeat branch
            # name. The resolver's own docstring records the disagreement with the other caller.
            result = await resolve_intent(session_id, intent.action_type, intent.target or "",
                                          intent.item_used or "")
            return {"success": True, "event": "combat_resolved", **result}
        except Exception as e:
            # Logged before it is turned into a player-facing failure: this handler catches the
            # resolver's own bugs too, and without a line here a defect reads as a failed action.
            from core.log import error

            error("intent", f"combat resolution failed for {intent.target or 'no target'}: {e}")
            return {"success": False, "error": f"Combat resolver error: {e}"}

    if intent.action_type == "roll":
        expr = f"{intent.amount or 100}" if intent.target is None else intent.target
        # roll is handled by CLI; here we just acknowledge
        return {"success": True, "event": "roll_requested", "expr": expr}

    # Everything else names a resolver in RESOLVERS that this entry point never imports or calls.
    # It used to answer `success: True` with `event: <action>_queued` and a note about a workflow,
    # so the CLI printed a successful event to the player for an action nothing had run. The
    # registry is a map of names, not of callables: the dispatch refuses instead of claiming one.
    resolver = ctx.get("resolver")
    return {"success": False, "event": f"{intent.action_type}_not_dispatched",
            "resolver": resolver,
            "error": f"{intent.action_type} is registered to {resolver} and this entry point does"
                     f" not invoke it"}


# ─── Parse helper: LLM output → strict PlayerIntent ──────────────────────
def parse_to_intent(raw: str | dict) -> PlayerIntent:
    """Parse LLM JSON output into validated PlayerIntent.
    Raises ValidationError on malformed/hallucinated output (LLM retries)."""
    if isinstance(raw, dict):
        return PlayerIntent.model_validate(raw)
    return PlayerIntent.model_validate_json(raw)
