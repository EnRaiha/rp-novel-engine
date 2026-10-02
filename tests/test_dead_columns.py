"""A column nothing reads is a column nobody has.

This gate exists because of one specific mistake: `affection` was added to carry the King's
carryover, and a later audit found the code never named it. The value existed and the engine could
not see it, which is the same shape as the earlier `bond_level` trap.

The check is a ratchet. The columns listed below are dead today, measured against `core/`, `modules/`
and `scripts/`. A NEW dead column fails the test, and a column that becomes live also fails, because
that is the moment to strike it off the list. Nothing here is a judgement about whether those columns
should be used; it is a guard against adding a field and never reading it.
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CODE_DIRS = ("core", "modules", "scripts")

#: Measured 2026-10-02. Each entry is a column no Python in this repo names.
KNOWN_DEAD: dict[str, set[str]] = {
    "characters": {"scene_territory_id"},
    "factions": {"last_economic_tick", "last_diplomatic_tick", "pirate_reputation",
                 "slave_trade_reputation"},
    "ships": {"fighter_capacity", "is_colony_ship", "colonists", "shield_generators",
              "engine_type", "combat_modules"},
    "territory": {"defensive_rating", "last_battle_session", "last_campaign",
                  "military_consumption"},
    "character_assets": {"lora"},
    "commodities": set(),
    "research_queue": set(),
}


def _code() -> str:
    text = ""
    for folder in CODE_DIRS:
        for path in (ROOT / folder).rglob("*.py"):
            text += path.read_text(encoding="utf-8", errors="replace")
    return text


def _dead_columns(table: str) -> set[str]:
    import os
    import re
    import psycopg2

    env = pathlib.Path.home() / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, _, value = line.partition("=")
                key = key.removeprefix("export ").strip()
                if key.startswith(("OC_PG_", "POSTGRES_")) and key not in os.environ:
                    os.environ[key] = value.strip().strip("'\"")
    if not os.environ.get("OC_PG_HOST"):
        pytest.skip("no OC_PG_* settings; the column list comes from the live schema")
    conn = psycopg2.connect(host=os.environ["OC_PG_HOST"], port=int(os.environ.get("OC_PG_PORT", 5432)),
                            user=os.environ["OC_PG_USER"], password=os.environ.get("OC_PG_PASS"),
                            dbname=os.environ.get("OC_PG_DB", "maya_memory"))
    try:
        cur = conn.cursor()
        cur.execute("""SELECT column_name FROM information_schema.columns
                       WHERE table_schema='maya_rp' AND table_name=%s""", (table,))
        columns = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()
    assert columns, f"{table} has no columns; the table name may have changed"
    code = _code()
    return {column for column in columns if not re.search(rf"\b{re.escape(column)}\b", code)}


@pytest.mark.parametrize("table", sorted(KNOWN_DEAD))
def test_no_new_dead_column(table):
    dead = _dead_columns(table)
    added = dead - KNOWN_DEAD[table]
    assert not added, (
        f"{table}: these columns are never named in code: {sorted(added)}. Either read them or "
        f"strike them off KNOWN_DEAD deliberately"
    )


@pytest.mark.parametrize("table", sorted(KNOWN_DEAD))
def test_a_column_that_became_live_is_struck_off(table):
    dead = _dead_columns(table)
    revived = KNOWN_DEAD[table] - dead
    assert not revived, (
        f"{table}: {sorted(revived)} are now named in code; remove them from KNOWN_DEAD so the "
        f"list keeps meaning something"
    )
