#!/usr/bin/env python3
"""Rebuild The System's List: the beauty-ranked roster, women first, with prisoners set apart.

King's ruling (D3): the list is a list of prospective wives, built by beauty, after the
women are separated out. Women from the imported rosters are eligible; the three Gate
prisoners belong to the list but are prisoners, not candidates.

    python3 scripts/beauty_list.py                      # proposal, nothing written
    python3 scripts/beauty_list.py --basis rank --apply # writes, and says what it changed

The beauty **basis** is the one thing this script will not decide for the King:

- `kept`   - keep the value a row already carries; new rows get `--floor` (default 9.0)
- `rank`   - 9.5 where the row's role names a top rank (`5-star`, `S-rank`), else the floor
- `uniform` - every new row gets the floor

A proposal is printed as a table with the count per category and the ordered list, so the
King can sign off on numbers before anything is written. Nothing is written without
`--apply`, and `--apply` refuses to run without an explicit `--basis`.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

VAULT = pathlib.Path(__file__).resolve().parents[2]
TOP_RANK = re.compile(r"\b(5-star|S-rank)\b", re.IGNORECASE)
CATALOG_CEILING = 1000
PRISONER_TRAIT = "prisoner"


def load_rows(cur) -> list[dict]:
    """Read the roster candidates from the engine.

    @param cur - an open cursor.
    @returns rows for every session-5 character that is female or a prisoner, with the
        fields the list needs.
    """
    # A woman is recognised three ways, in this order: the gender tag from her source
    # roster, a spouse flag in the frozen session 3 matched by exact name, or the fact that
    # she already sits on this list. Session 5 records no spouses of its own.
    cur.execute("SELECT name FROM maya_rp.characters WHERE session_id = 3 AND COALESCE(is_spouse, false)")
    spouses = {row[0] for row in cur.fetchall()}
    cur.execute("""SELECT id, name, role, traits::text, beauty_standard, beauty_catalog_id,
                          COALESCE(appearance,'') <> '' OR COALESCE(description,'') <> '' AS has_text
                   FROM maya_rp.characters WHERE session_id = 5 ORDER BY id""")
    rows = []
    for cid, name, role, traits, standard, catalog, has_text in cur.fetchall():
        traits = traits or ""
        is_woman = ('"female"' in traits or name in spouses or bool(standard)
                    or PRISONER_TRAIT in traits)
        if not is_woman:
            continue
        rows.append({
            "id": cid, "name": name, "role": role or "", "traits": traits,
            "standard": bool(standard), "catalog": catalog, "has_text": bool(has_text),
            "imported": "imported" in traits, "prisoner": PRISONER_TRAIT in traits,
            "spouse": name in spouses, "listed": bool(standard),
        })
    return rows


def beauty_for(row: dict, basis: str, floor: float) -> float:
    """The beauty a row carries on this basis.

    @param row - a roster row.
    @param basis - kept | rank | uniform.
    @param floor - the value a row without its own number receives.
    @returns the beauty value as a float.
    """
    if basis == "kept" and row["catalog"] is not None:
        return float(row["catalog"]) if row["catalog"] < 100 else floor
    if basis == "rank" and TOP_RANK.search(row["role"]):
        return 9.5
    return floor


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--basis", choices=("kept", "rank", "uniform"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--floor", type=float, default=9.0)
    parser.add_argument("--show", type=int, default=15)
    parser.add_argument("--cap", type=int, default=0,
                        help="0 means no cap; the list takes every candidate")
    args = parser.parse_args()
    if args.apply and not args.basis:
        print("refusing to write without an explicit --basis; the beauty basis is the King's call")
        return 2
    basis = args.basis or "rank"

    import psycopg2
    import os

    env = pathlib.Path.home() / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, _, value = line.partition("=")
                key = key.removeprefix("export ").strip()
                if key.startswith(("OC_PG_", "POSTGRES_")) and key not in os.environ:
                    os.environ[key] = value.strip().strip("'\"")

    conn = psycopg2.connect(host=os.environ["OC_PG_HOST"], port=int(os.environ.get("OC_PG_PORT", 5432)),
                            user=os.environ["OC_PG_USER"], password=os.environ.get("OC_PG_PASS"),
                            dbname=os.environ.get("OC_PG_DB", "maya_memory"))
    cur = conn.cursor()
    rows = load_rows(cur)
    for row in rows:
        row["beauty"] = beauty_for(row, basis, args.floor)

    candidates = [r for r in rows if not r["prisoner"]]
    prisoners = [r for r in rows if r["prisoner"]]
    candidates.sort(key=lambda r: (-r["beauty"], r["id"]))
    dropped = 0
    if args.cap:
        dropped = max(0, len(candidates) - args.cap)
        candidates = candidates[: args.cap]
    prisoners.sort(key=lambda r: r["id"])

    print(f"basis {basis} · floor {args.floor}")
    print(f"women and prisoners in session 5: {len(rows)} · candidates {len(candidates)} · "
          f"prisoners {len(prisoners)}")
    print(f"  of the candidates: imported {sum(1 for r in candidates if r['imported'])}, "
          f"spouses {sum(1 for r in candidates if r['spouse'])}, "
          f"already listed {sum(1 for r in candidates if r['listed'])}, "
          f"with text {sum(1 for r in candidates if r['has_text'])}")
    already = [r for r in candidates if r["catalog"] is not None]
    fresh = [r for r in candidates if r["catalog"] is None]
    print(f"  already on the list: {len(already)} · new rows an apply would add: {len(fresh)}"
          + (f" · dropped by cap {args.cap}: {dropped}" if args.cap else ""))
    print("top of the list:")
    for row in candidates[: args.show]:
        print(f"  {row['beauty']:.1f}  {row['name'][:34]:<34} id {row['id']:<5} "
              f"{'import' if row['imported'] else 'canon'}")
    if prisoners:
        print("prisoner section (not candidates):")
        for row in prisoners:
            print(f"  {row['beauty']:.1f}  {row['name'][:34]:<34} id {row['id']}")

    if not args.apply:
        print("proposal only: nothing written")
        conn.close()
        return 0

    free = max([r["catalog"] for r in rows if r["catalog"] is not None and r["catalog"] < CATALOG_CEILING] or [54]) + 1
    changed = 0
    for row in candidates:
        if row["standard"] and row["catalog"] is not None and basis == "kept":
            continue
        cur.execute("UPDATE maya_rp.characters SET beauty_standard = true, beauty_catalog_id = %s WHERE id = %s",
                    (free, row["id"]))
        free += 1
        changed += 1
    conn.commit()
    print(f"applied: {changed} rows now carry beauty_standard and a catalog id")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
