#!/usr/bin/env python3
"""Alchemy — Ported from Rust alchemy.rs."""
from __future__ import annotations
import json, random
from decimal import Decimal
from core.db import Database
from core.log import info
from core.session import require_session


def _writable_session(session_id: int | None) -> int:
    """Resolve the session for one call and refuse a frozen campaign.

    Sessions 3 and 5 are reference data; a writer that skipped this check mutated them.

    @param session_id - caller's session; `None` resolves through `core.session.require_session`.
    @returns the resolved session id.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    from core.ooc import _refuse_frozen

    sid = require_session(session_id)
    _refuse_frozen(sid)
    return sid


def _like_escape(text: str) -> str:
    """Escape `\\`, `%` and `_` so a recipe name matches as literal text under `ESCAPE '\\'`.

    @param text - user-supplied recipe name.
    @returns the text with LIKE wildcards neutralised.
    """
    return str(text).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _dec(value) -> Decimal:
    """Read a JSON recipe quantity as Decimal.

    `material_stockpiles.quantity` is numeric, so asyncpg returns Decimal. A float recipe quantity
    minus a Decimal stock raised TypeError after earlier materials were already consumed.

    @param value - int, float or numeric string from the recipe JSON.
    @returns the exact Decimal.
    """
    return Decimal(str(value))

async def list_recipes() -> list[dict]:
    rows = await Database.fetch("SELECT id, name, category, inputs, outputs, catalyst, success_rate, tech_tier, lore_text FROM maya_rp.alchemy_recipes ORDER BY category, tech_tier")
    return [dict(r) for r in rows]

async def transmute(recipe_name: str, qty: int = 1, session_id: int | None = None) -> dict:
    """Brew one recipe `qty` times for this session.

    The name matches case-insensitively and may be partial. An exact name wins
    over a substring and the rest are taken in id order, so a partial name that
    matches two recipes resolves the same way every time instead of taking
    whichever row PostgreSQL returned first. `%` and `_` in the name match
    literally.

    The availability check, every decrement and every output upsert run in one
    transaction under a per-session advisory lock. Two concurrent brews used to
    both pass the check and drive a stockpile negative, and a TypeError mid-loop
    left earlier materials consumed.

    `catalyst` and `tech_tier` are read and NOT enforced: no recipe consumes its
    catalyst, and nothing gates a transmutation on the tier. Both are reported
    as open items rather than invented here.

    @param recipe_name - full or partial recipe name.
    @param qty - number of brews, at least 1.
    @param session_id - campaign; `None` resolves through `require_session`.
    @returns `{recipe, attempts, successes}`, or `{error}` for an unknown recipe or a shortfall.
    @raises ValueError - `qty` is below 1.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    if qty < 1:
        raise ValueError(f"qty must be at least 1, got {qty}")
    recipe = await Database.fetchrow(
        "SELECT id, name, category, inputs, outputs, catalyst, success_rate, tech_tier, lore_text "
        "FROM maya_rp.alchemy_recipes WHERE LOWER(name) LIKE LOWER($1) ESCAPE '\\' "
        "ORDER BY (LOWER(name) = LOWER($2)) DESC, id LIMIT 1",
        f"%{_like_escape(recipe_name)}%", str(recipe_name))
    if not recipe: return {"error": f"Recipe '{recipe_name}' not found"}
    inputs = json.loads(recipe["inputs"]) if isinstance(recipe["inputs"], str) else recipe["inputs"]
    outputs = json.loads(recipe["outputs"]) if isinstance(recipe["outputs"], str) else recipe["outputs"]
    # `success_rate or 1.0` read a declared 0 (never works) as "always works".
    rate = 1.0 if recipe["success_rate"] is None else float(recipe["success_rate"])
    successes = 0
    async with Database.transaction() as conn:
        # Serialises brews per session: the stockpile table has no unique key on
        # (session_id, material_name), so row locks alone cannot stop two inserts.
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext('alchemy'), $1)", session_id)
        piles: dict[str, list] = {}
        for mat, needed in inputs.items():
            rows = await conn.fetch(
                "SELECT id, quantity FROM maya_rp.material_stockpiles "
                "WHERE session_id=$1 AND material_name=$2 AND quantity>0 "
                "ORDER BY quantity DESC, id FOR UPDATE", session_id, mat)
            avail = sum((_dec(r["quantity"]) for r in rows), Decimal(0))
            need = _dec(needed) * qty
            if avail < need:
                return {"error": f"Need {need:.0f} {mat}, have {avail:.0f}"}
            piles[mat] = rows
        for mat, needed in inputs.items():
            remaining = _dec(needed) * qty
            for sp in piles[mat]:
                if remaining <= 0: break
                take = min(remaining, _dec(sp["quantity"]))
                await conn.execute(
                    "UPDATE maya_rp.material_stockpiles SET quantity=quantity-$1 WHERE id=$2",
                    take, sp["id"])
                remaining -= take
        for _ in range(qty):
            if random.random() < rate:
                successes += 1
        if successes:
            for mat, q in outputs.items():
                gained = _dec(q) * successes
                existing = await conn.fetchrow(
                    "SELECT id FROM maya_rp.material_stockpiles WHERE session_id=$1 AND material_name=$2 "
                    "ORDER BY id LIMIT 1", session_id, mat)
                if existing:
                    await conn.execute(
                        "UPDATE maya_rp.material_stockpiles SET quantity=COALESCE(quantity,0)+$1 WHERE id=$2",
                        gained, existing["id"])
                else:
                    await conn.execute(
                        "INSERT INTO maya_rp.material_stockpiles (session_id, material_name, quantity) VALUES ($1,$2,$3)",
                        session_id, mat, gained)
    info("alchemy", f"Transmuted {recipe['name']} x{qty}: {successes} successes")
    return {"recipe": recipe["name"], "attempts": qty, "successes": successes}

async def run_tick(session_id: int | None = None) -> dict:
    """No-op tick. @raises core.ooc.FrozenSession - the campaign is frozen."""
    _writable_session(session_id)
    return {"status": "alchemy_ready"}
