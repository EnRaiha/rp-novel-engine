#!/usr/bin/env python3
"""Alchemy — Ported from Rust alchemy.rs."""
from __future__ import annotations
import json, random
from core.db import Database
from core.config import Config
from core.log import info

async def list_recipes() -> list[dict]:
    rows = await Database.fetch("SELECT id, name, category, inputs, outputs, catalyst, success_rate, tech_tier, lore_text FROM maya_rp.alchemy_recipes ORDER BY category, tech_tier")
    return [dict(r) for r in rows]

async def transmute(recipe_name: str, qty: int = 1, session_id: int | None = None) -> dict:
    """Brew one recipe `qty` times for this session.

    The name matches case-insensitively and may be partial. An exact name wins
    over a substring and the rest are taken in id order, so a partial name that
    matches two recipes resolves the same way every time instead of taking
    whichever row PostgreSQL returned first.

    `catalyst` and `tech_tier` are read and NOT enforced: no recipe consumes its
    catalyst, and nothing gates a transmutation on the tier. Both are reported
    as open items rather than invented here.
    """
    if session_id is None: session_id = Config.SESSION_ID
    if qty < 1:
        raise ValueError(f"qty must be at least 1, got {qty}")
    recipe = await Database.fetchrow(
        "SELECT id, name, category, inputs, outputs, catalyst, success_rate, tech_tier, lore_text "
        "FROM maya_rp.alchemy_recipes WHERE LOWER(name) LIKE LOWER($1) "
        "ORDER BY (LOWER(name) = LOWER($2)) DESC, id LIMIT 1",
        f"%{recipe_name}%", str(recipe_name))
    if not recipe: return {"error": f"Recipe '{recipe_name}' not found"}
    inputs = json.loads(recipe["inputs"]) if isinstance(recipe["inputs"], str) else recipe["inputs"]
    outputs = json.loads(recipe["outputs"]) if isinstance(recipe["outputs"], str) else recipe["outputs"]
    for mat, needed in inputs.items():
        avail = await Database.fetchval("SELECT COALESCE(SUM(quantity),0) FROM maya_rp.material_stockpiles WHERE session_id=$1 AND material_name=$2", session_id, mat) or 0
        if avail < needed * qty: return {"error": f"Need {needed*qty:.0f} {mat}, have {avail:.0f}"}
    for mat, needed in inputs.items():
        remaining = needed * qty
        sps = await Database.fetch("SELECT id, quantity FROM maya_rp.material_stockpiles WHERE session_id=$1 AND material_name=$2 AND quantity>0 ORDER BY quantity DESC", session_id, mat)
        for sp in sps:
            if remaining <= 0: break
            take = min(remaining, sp["quantity"])
            await Database.execute("UPDATE maya_rp.material_stockpiles SET quantity=quantity-$1 WHERE id=$2", take, sp["id"])
            remaining -= take
    successes = 0
    # `success_rate or 1.0` read a declared 0 (never works) as "always works".
    rate = 1.0 if recipe["success_rate"] is None else float(recipe["success_rate"])
    for _ in range(qty):
        if random.random() < rate:
            successes += 1
            for mat, q in outputs.items():
                existing = await Database.fetchrow("SELECT id FROM maya_rp.material_stockpiles WHERE session_id=$1 AND material_name=$2 LIMIT 1", session_id, mat)
                if existing: await Database.execute("UPDATE maya_rp.material_stockpiles SET quantity=quantity+$1 WHERE id=$2", q, existing["id"])
                else: await Database.execute("INSERT INTO maya_rp.material_stockpiles (session_id, material_name, quantity) VALUES ($1,$2,$3)", session_id, mat, q)
    info("alchemy", f"Transmuted {recipe['name']} x{qty}: {successes} successes")
    return {"recipe": recipe["name"], "attempts": qty, "successes": successes}

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    return {"status": "alchemy_ready"}
