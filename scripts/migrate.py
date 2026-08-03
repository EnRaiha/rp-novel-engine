#!/usr/bin/env python3
"""Migration runner — applies pending SQL migrations in order."""
import asyncio, sys, os
from pathlib import Path
sys.path.insert(0, str(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.db import Database
from core.config import Config
from core.log import info

async def run_migrations():
    await Database.init()
    await Database.execute(
        "CREATE TABLE IF NOT EXISTS maya_rp._migrations ("
        "id SERIAL PRIMARY KEY, name TEXT UNIQUE, applied_at TIMESTAMPTZ DEFAULT NOW())")

    applied = {r["name"] for r in await Database.fetch("SELECT name FROM maya_rp._migrations")}
    mig_dir = Path(Config.MIGRATIONS_DIR)
    files = sorted(mig_dir.glob("*.sql"))

    if not files:
        print("No migration files found.")
        return

    count = 0
    for f in files:
        if f.name in applied:
            continue
        try:
            sql = f.read_text()
            await Database.execute(sql)
            await Database.execute("INSERT INTO maya_rp._migrations (name) VALUES ($1)", f.name)
            print(f"  ✅ {f.name}")
            count += 1
        except Exception as e:
            print(f"  ❌ {f.name}: {e}")
            return

    if count == 0:
        print("  No pending migrations.")
    else:
        print(f"  Applied {count} migration(s).")
    await Database.close()

if __name__ == "__main__":
    asyncio.run(run_migrations())
