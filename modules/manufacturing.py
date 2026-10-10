#!/usr/bin/env python3
"""Manufacturing — Ported from Rust manufacturing.rs. Production lines, recipes, tick.

`production_lines` takes `session_id` from migration 138, `material_stockpiles` from the baseline
schema, so every read and every write names the campaign. `recipes` is a catalogue and stays
unscoped.
"""
from __future__ import annotations
import json
from typing import Any
from core.db import Database
from core.log import info, error
from core.session import require_session


class _StockShort(Exception):
    """Raised inside a line's transaction when a take finds less stock than the sufficiency read saw. Rolls the line back."""


async def run_tick(session_id: int | None = None) -> dict:
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    try:
        # Both the line and its colony must name this campaign. A line whose colony sits elsewhere is
        # a defect the pair refuses, and the pair is what every write below matches on.
        lines = await Database.fetch(
            "SELECT pl.id, pl.colony_id, pl.recipe_id, pl.efficiency, pl.status "
            "FROM maya_rp.production_lines pl JOIN maya_rp.colonies c ON pl.colony_id=c.id "
            "WHERE pl.session_id=$1 AND c.session_id=$1 AND pl.status IN ('running','blocked')", session_id)
        events = []
        blocked = 0
        unblocked = 0
        for l in lines:
            # One malformed recipe JSON used to abort the whole tick: every line
            # in the campaign stopped because one row could not be read.
            try:
                recipe = await Database.fetchrow("SELECT inputs, outputs, name FROM maya_rp.recipes WHERE id=$1", l["recipe_id"])
                if not recipe:
                    error("manufacturing", f"line {l['id']} has no recipe {l['recipe_id']} — skipped")
                    continue
                inputs, outputs, rname = recipe["inputs"], recipe["outputs"], recipe["name"]
                if isinstance(inputs, str): inputs = json.loads(inputs)
                if isinstance(outputs, str): outputs = json.loads(outputs)
            except (TypeError, ValueError) as e:
                error("manufacturing", f"line {l['id']} recipe is unreadable ({e}) — skipped")
                continue
            # efficiency is nullable with a default of 1.0, and `efficiency or 1.0` also read a real
            # zero as one: a line set to no throughput consumed and produced at full rate.
            eff = l["efficiency"] if l["efficiency"] is not None else 1.0
            sufficient = True
            for mat, needed in inputs.items():
                scaled = needed * eff
                avail = await Database.fetchval(
                    "SELECT COALESCE(SUM(quantity-reserved),0) FROM maya_rp.material_stockpiles "
                    "WHERE session_id=$1 AND material_name=$2", session_id, mat) or 0
                if avail < scaled: sufficient = False; break
            if not sufficient:
                if l["status"] != "blocked":
                    await Database.execute(
                        "UPDATE maya_rp.production_lines SET status='blocked' "
                        "WHERE id=$1 AND colony_id=$2 AND session_id=$3",
                        l["id"], l["colony_id"], session_id)
                    blocked += 1
                    events.append(f"line {l['id']} blocked: {rname}")
                continue
            # The sufficiency read above is advisory. One transaction per line takes the inputs under a
            # stock guard and writes the outputs, so two ticks cannot spend one stockpile twice and an
            # output error returns the inputs.
            try:
                async with Database.transaction() as conn:
                    for mat, needed in inputs.items():
                        remaining = needed * eff
                        sps = await conn.fetch(
                            "SELECT id, quantity-reserved as avail FROM maya_rp.material_stockpiles "
                            "WHERE session_id=$1 AND material_name=$2 AND quantity>reserved ORDER BY quantity DESC",
                            session_id, mat)
                        for sp in sps:
                            if remaining <= 0: break
                            take = min(remaining, sp["avail"])
                            tag = await conn.execute(
                                "UPDATE maya_rp.material_stockpiles SET quantity=quantity-$1 "
                                "WHERE id=$2 AND session_id=$3 AND quantity-reserved>=$1",
                                take, sp["id"], session_id)
                            if tag != "UPDATE 1": raise _StockShort(mat)
                            remaining -= take
                        if remaining > 0: raise _StockShort(mat)
                    for mat, qty in outputs.items():
                        q = qty * eff
                        if q <= 0:
                            # A line at zero throughput produced a nought-quantity stockpile row, which is a
                            # new material at the colony that no recipe ever made.
                            continue
                        existing = await conn.fetchrow(
                            "SELECT id FROM maya_rp.material_stockpiles WHERE session_id=$1 AND material_name=$2 AND colony_id=$3 LIMIT 1",
                            session_id, mat, l["colony_id"])
                        if existing:
                            await conn.execute(
                                "UPDATE maya_rp.material_stockpiles SET quantity=quantity+$1 "
                                "WHERE id=$2 AND session_id=$3",
                                q, existing["id"], session_id)
                        else:
                            await conn.execute("INSERT INTO maya_rp.material_stockpiles (session_id, colony_id, material_name, quantity) VALUES ($1,$2,$3,$4)", session_id, l["colony_id"], mat, q)
                    if l["status"] == "blocked":
                        await conn.execute(
                            "UPDATE maya_rp.production_lines SET status='running' "
                            "WHERE id=$1 AND colony_id=$2 AND session_id=$3",
                            l["id"], l["colony_id"], session_id)
            except _StockShort:
                if l["status"] != "blocked":
                    await Database.execute(
                        "UPDATE maya_rp.production_lines SET status='blocked' "
                        "WHERE id=$1 AND colony_id=$2 AND session_id=$3",
                        l["id"], l["colony_id"], session_id)
                    blocked += 1
                    events.append(f"line {l['id']} blocked: {rname}")
                continue
            if l["status"] == "blocked":
                unblocked += 1
                events.append(f"line {l['id']} unblocked: {rname}")
        # The counter said "blocked" and counted every event, unblockings included, so a line that had
        # just started running again was reported as blocked.
        info("manufacturing", f"Tick: {len(lines)} lines, {blocked} blocked, {unblocked} unblocked")
        if events:
            info("manufacturing", " | ".join(events))
        return {"lines": len(lines), "blocked": blocked, "unblocked": unblocked}
    except Exception as e:
        error("manufacturing", f"Error: {e}")
        return {"error": str(e)}
