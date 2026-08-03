#!/usr/bin/env python3
"""Manufacturing — Ported from Rust manufacturing.rs. Production lines, recipes, tick."""
from __future__ import annotations
import json
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

async def run_tick(session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    try:
        lines = await Database.fetch(
            "SELECT pl.id, pl.colony_id, pl.recipe_id, pl.efficiency, pl.status "
            "FROM maya_rp.production_lines pl JOIN maya_rp.colonies c ON pl.colony_id=c.id "
            "WHERE c.session_id=$1 AND pl.status IN ('running','blocked')", session_id)
        events = []
        for l in lines:
            recipe = await Database.fetchrow("SELECT inputs, outputs, name FROM maya_rp.recipes WHERE id=$1", l["recipe_id"])
            if not recipe: continue
            inputs, outputs, rname = recipe["inputs"], recipe["outputs"], recipe["name"]
            if isinstance(inputs, str): inputs = json.loads(inputs)
            if isinstance(outputs, str): outputs = json.loads(outputs)
            sufficient = True
            for mat, needed in inputs.items():
                scaled = needed * (l["efficiency"] or 1.0)
                avail = await Database.fetchval(
                    "SELECT COALESCE(SUM(quantity-reserved),0) FROM maya_rp.material_stockpiles "
                    "WHERE session_id=$1 AND material_name=$2", session_id, mat) or 0
                if avail < scaled: sufficient = False; break
            if not sufficient:
                if l["status"] != "blocked":
                    await Database.execute("UPDATE maya_rp.production_lines SET status='blocked' WHERE id=$1", l["id"])
                    events.append(f"Line {l['id']} blocked: {rname}")
                continue
            if l["status"] == "blocked":
                await Database.execute("UPDATE maya_rp.production_lines SET status='running' WHERE id=$1", l["id"])
                events.append(f"Line {l['id']} unblocked: {rname}")
            for mat, needed in inputs.items():
                remaining = needed * (l["efficiency"] or 1.0)
                sps = await Database.fetch(
                    "SELECT id, quantity-reserved as avail FROM maya_rp.material_stockpiles "
                    "WHERE session_id=$1 AND material_name=$2 AND quantity>reserved ORDER BY quantity DESC",
                    session_id, mat)
                for sp in sps:
                    if remaining <= 0: break
                    take = min(remaining, sp["avail"])
                    await Database.execute("UPDATE maya_rp.material_stockpiles SET quantity=quantity-$1 WHERE id=$2", take, sp["id"])
                    remaining -= take
            for mat, qty in outputs.items():
                q = qty * (l["efficiency"] or 1.0)
                existing = await Database.fetchrow(
                    "SELECT id FROM maya_rp.material_stockpiles WHERE session_id=$1 AND material_name=$2 AND colony_id=$3 LIMIT 1",
                    session_id, mat, l["colony_id"])
                if existing:
                    await Database.execute("UPDATE maya_rp.material_stockpiles SET quantity=quantity+$1 WHERE id=$2", q, existing["id"])
                else:
                    await Database.execute("INSERT INTO maya_rp.material_stockpiles (session_id, colony_id, material_name, quantity) VALUES ($1,$2,$3,$4)", session_id, l["colony_id"], mat, q)
        info("manufacturing", f"Tick: {len(lines)} lines, {len(events)} blocked")
        return {"lines": len(lines), "blocked": len(events)}
    except Exception as e:
        info("manufacturing", f"Error: {e}")
        return {"error": str(e)}
