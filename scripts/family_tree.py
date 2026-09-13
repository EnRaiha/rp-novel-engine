#!/usr/bin/env python3
"""Family Tree — dual-system lineage for TKG RP.

Two family systems:
  - old_way      (most factions): patrilineal, clan name = identity, house_name == birth_house
  - setia_new_way (House al-Dabaran): al-Dabaran is TITLE only, birth names preserved,
                   all children are heirs (all_heirs succession)

Usage:
  python3 scripts/family_tree.py tree                 # full tree (King root)
  python3 scripts/family_tree.py tree <name>          # subtree from character
  python3 scripts/family_tree.py children <name>      # children of X
  python3 scripts/family_tree.py spouses <name>       # spouses of X
  python3 scripts/family_tree.py house <house_name>   # all members of a house
  python3 scripts/family_tree.py pregnant             # all active pregnancies w/ mothers
"""
import asyncio
import os
import sys
from datetime import datetime

import asyncpg

SESSION_ID = 3


async def connect():
    return await asyncpg.connect(
        host=os.environ.get("POSTGRES_HOST", "100.65.243.60"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        user=os.environ.get("POSTGRES_USER", "rp_engine"),
        password=os.environ.get("POSTGRES_PASS", ""),
        database=os.environ.get("POSTGRES_DB", "maya_memory"),
    )


def fmt_char(c):
    sys2 = c.get("family_system", "old_way")
    tag = "🌿" if sys2 == "setia_new_way" else "🏴"
    birth = c.get("birth_house") or "?"
    house = c.get("house_name") or "?"
    line = f"{tag} {c['name']}"
    if sys2 == "setia_new_way":
        line += f"  [{birth} → {house} · all_heirs]"
    else:
        line += f"  [{house} clan · patrilineal]"
    if c.get("is_spouse"):
        line += " 👑"
    return line


async def get_children(conn, char_id):
    rows = await conn.fetch(
        """SELECT c.id, c.name, c.birth_house, c.house_name, c.family_system, c.succession, c.is_spouse
           FROM maya_rp.characters c
           WHERE (c.mother_id = $1 OR c.father_id = $1) AND c.id != $1
           ORDER BY c.id""", char_id)
    return [dict(r) for r in rows]


async def get_spouses(conn, char_id):
    rows = await conn.fetch(
        """SELECT c.id, c.name, c.birth_house, c.house_name, c.family_system, c.succession, c.is_spouse
           FROM maya_rp.family_relations fr
           JOIN maya_rp.characters c ON c.id = fr.related_id
           WHERE fr.session_id = $1 AND fr.member_id = $2 AND fr.relation_type = 'spouse'
           ORDER BY c.id""", SESSION_ID, char_id)
    return [dict(r) for r in rows]


async def find_char(conn, name):
    row = await conn.fetchrow(
        "SELECT * FROM maya_rp.characters WHERE name ILIKE $1 ORDER BY id LIMIT 1",
        f"%{name}%")
    return dict(row) if row else None


async def cmd_tree(conn, root_name=None):
    if root_name:
        root = await find_char(conn, root_name)
        if not root:
            print(f"Not found: {root_name}")
            return
    else:
        root = await find_char(conn, "King Izzat")

    print(f"== FAMILY TREE — root: {root['name']} ==")
    print(fmt_char(root))

    spouses = await get_spouses(conn, root["id"])
    if spouses:
        print("  └─ Spouses:")
        for s in spouses:
            print(f"     👑 {fmt_char(s)}")

    children = await get_children(conn, root["id"])
    if children:
        print("  └─ Children:")
        for ch in children:
            print(f"     • {fmt_char(ch)}")
            # grandchildren
            g = await get_children(conn, ch["id"])
            for gc in g:
                print(f"         └ {fmt_char(gc)}")


async def cmd_children(conn, name):
    c = await find_char(conn, name)
    if not c:
        print(f"Not found: {name}")
        return
    print(f"Children of {c['name']}:")
    for ch in await get_children(conn, c["id"]):
        print(f"  • {fmt_char(ch)}")


async def cmd_spouses(conn, name):
    c = await find_char(conn, name)
    if not c:
        print(f"Not found: {name}")
        return
    print(f"Spouses of {c['name']}:")
    for s in await get_spouses(conn, c["id"]):
        print(f"  👑 {fmt_char(s)}")


async def cmd_house(conn, house):
    rows = await conn.fetch(
        """SELECT id, name, birth_house, house_name, family_system, succession, is_spouse
           FROM maya_rp.characters
           WHERE house_name ILIKE $1 OR birth_house ILIKE $1
           ORDER BY family_system, id""", f"%{house}%")
    print(f"== HOUSE {house.upper()} ==")
    for r in rows:
        print(fmt_char(dict(r)))


async def cmd_pregnant(conn):
    rows = await conn.fetch(
        """SELECT p.mother_name, p.status, p.due_game_day, p.trimester,
                  c.birth_house, c.house_name, c.family_system
           FROM maya_rp.pregnancies p
           LEFT JOIN maya_rp.characters c ON c.id = p.mother_id
           WHERE p.session_id = $1 AND p.status = 'active'
           ORDER BY p.mother_id""", SESSION_ID)
    print("== ACTIVE PREGNANCIES ==")
    for r in rows:
        bh = r["birth_house"] or "?"
        hs = r["house_name"] or "?"
        print(f"  🤰 {r['mother_name']} [{bh} → {hs}] · due D{r['due_game_day']} · T{r['trimester']}")


async def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    conn = await connect()
    try:
        if cmd == "tree":
            await cmd_tree(conn, sys.argv[2] if len(sys.argv) > 2 else None)
        elif cmd == "children":
            await cmd_children(conn, sys.argv[2] if len(sys.argv) > 2 else "")
        elif cmd == "spouses":
            await cmd_spouses(conn, sys.argv[2] if len(sys.argv) > 2 else "")
        elif cmd == "house":
            await cmd_house(conn, sys.argv[2] if len(sys.argv) > 2 else "")
        elif cmd == "pregnant":
            await cmd_pregnant(conn)
        else:
            print(__doc__)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
