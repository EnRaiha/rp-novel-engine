#!/usr/bin/env python3
"""Batch embed all un-embedded events via local GTX 1060 (Ollama). Run once."""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.db import Database
from core.log import info
import core.memory as mem

async def embed_all(session_id: int = 3):
    await Database.init()
    evs = await Database.fetch("SELECT id,title,description FROM maya_rp.events WHERE session_id=$1 AND embedding IS NULL ORDER BY id", session_id)
    total = len(evs)
    if total == 0:
        print("All events already embedded.")
        return
    print(f"Embedding {total} events via GTX 1060 (Ollama nomic-embed-text)...")
    for i, ev in enumerate(evs):
        try:
            await mem.store_event(ev["id"], ev["title"], ev.get("description",""), session_id)
            if (i+1) % 10 == 0:
                print(f"  {i+1}/{total} embedded")
        except Exception as e:
            print(f"  Error on event {ev['id']}: {e}")
    print(f"Done. {total} events embedded.")
    await Database.close()

if __name__ == "__main__":
    asyncio.run(embed_all())
