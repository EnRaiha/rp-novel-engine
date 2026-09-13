#!/usr/bin/env python3
"""Name Resolution CLI — char:query / loc:query / ship:query.

Solves the three RP name-typing problems (session-review driven):
  1. TYPOS        — "calissta" → Callista  (difflib fuzzy + Levenshtein)
  2. NICKNAMES    — "the forge", "kitty", "anchor", "dsn"
                    (data/roster.yaml aliases + auto role-token matching)
  3. SAME NAME,
     DIFFERENT JOB — "Nadia Voss" ×2, "Kira" ×3, "Zara" ×3, "Aina" ×2
                    (returns ALL candidates ranked by bond; the GM picks)
  4. GROUPS       — char:query queens | ministers | command | royal_children
                    | immortals (curated YAML roster, live-validated vs DB)

Usage:
  python3 scripts/char_query.py char "calissta"
  python3 scripts/char_query.py char "nadia"
  python3 scripts/char_query.py char queens
  python3 scripts/char_query.py groups
  python3 scripts/char_query.py alias list | alias "<a>" | alias add "<a>" "<char>"
  python3 scripts/char_query.py loc "Mastika"      # territory/system by name
  python3 scripts/char_query.py loc "741,280"      # 1000-grid system nearest
  python3 scripts/char_query.py loc "12,12"        # sector grid (0–24) nearest
  python3 scripts/char_query.py ship "Nusantara"   # ship by name/class/type
  --json on any command for machine-readable output.
"""
from __future__ import annotations
import asyncio, difflib, json, os, re, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import yaml
from core.db import Database
from core.config import Config

ROSTER_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "roster.yaml")
# 1000-grid system coordinates (Voronoi Day-178 scale; system names are "X-Y")
TERR_1000_FILE = os.path.expanduser("~/backups/territory_1000_20260808.json")

ROSTER_HEADER = ("# Roster — curated character reference for char:query.\n"
                 "# DB (maya_rp.characters) is always truth; this file is the convenience layer.\n"
                 "# char:query <group> resolves every entry live and flags stale names.\n"
                 "# aliases:  nickname / role-keyword → canonical character name\n")


# ─── Fuzzy engine (stdlib only) ──────────────────────────────────────────

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def _base(name: str) -> str:
    """'Nadia Voss (General of the North)' → 'nadia voss'"""
    return _norm(name.split(" (")[0])

def _first(name: str) -> str:
    return _base(name).split(" ")[0]

def _lev(a: str, b: str) -> int:
    if len(a) > len(b):
        a, b = b, a
    prev = list(range(len(a) + 1))
    for i, cb in enumerate(b, 1):
        cur = [i]
        for j, ca in enumerate(a, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1,
                           prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


# ─── Roster (YAML: aliases + groups) ─────────────────────────────────────

def _load_roster() -> dict:
    d = {}
    if os.path.exists(ROSTER_FILE):
        with open(ROSTER_FILE) as f:
            d = yaml.safe_load(f) or {}
    return {
        "aliases": {_norm(k): v for k, v in (d.get("aliases") or {}).items()},
        "groups": {_norm(k): [str(n) for n in v]
                   for k, v in (d.get("groups") or {}).items()},
    }

def _save_roster(roster: dict) -> None:
    os.makedirs(os.path.dirname(ROSTER_FILE), exist_ok=True)
    with open(ROSTER_FILE, "w") as f:
        f.write(ROSTER_HEADER)
        yaml.safe_dump({"aliases": roster["aliases"], "groups": roster["groups"]},
                       f, allow_unicode=True, sort_keys=False, default_flow_style=False)


# ─── Character resolution ────────────────────────────────────────────────

async def _load_characters() -> list[dict]:
    return [dict(r) for r in await Database.fetch(
        "SELECT id, name, role, bond, status, scene_location, is_spouse, house_name "
        "FROM maya_rp.characters WHERE session_id=$1 AND status IN ('active','married',"
        "'maternity_leave','friendly','hidden') ORDER BY COALESCE(bond,0) DESC, name",
        Config.SESSION_ID)]


def _fmt_char(c: dict, aliases: dict) -> str:
    crown = " 👑" if c.get("is_spouse") else ""
    own_aliases = [a for a, t in aliases.items()
                   if _norm(t) == _norm(c["name"]) or _base(t) == _base(c["name"])]
    lines = [f"{c['name']}  [bond {c.get('bond') or 0}]{crown}"]
    lines.append(f"   role: {c['role'] or '—'}")
    if c.get("scene_location"):
        lines.append(f"   scene: {c['scene_location']}")
    if c.get("house_name"):
        lines.append(f"   house: {c['house_name']}")
    if own_aliases:
        lines.append(f"   aliases: {', '.join(sorted(own_aliases))}")
    return "\n".join(lines)


def resolve_char(query: str, chars: list[dict], aliases: dict) -> dict:
    """Resolution pipeline: group → alias → exact → base → first → role → fuzzy."""
    q = _norm(query)
    if not q:
        return {"ok": False, "error": "empty query"}

    def pick(names: list, kind: str) -> dict | None:
        if len(names) == 1:
            return {"ok": True, "kind": kind, "candidates": names}
        if len(names) > 1:
            return {"ok": True, "kind": "ambiguous", "candidates": names,
                    "note": f"{len(names)} characters share that name — "
                            f"re-query with full name or job"}
        return None

    # 1. alias
    target = aliases.get(q)
    if target:
        hits = [c for c in chars if _norm(c["name"]) == _norm(target)]
        if hits:
            r = pick(hits, "alias")
            if r:
                r["alias_used"] = q
                return r

    # 2. exact full name
    r = pick([c for c in chars if _norm(c["name"]) == q], "exact")
    if r: return r

    # 3. exact base name (collision-aware: Nadia Voss ×2)
    r = pick([c for c in chars if _base(c["name"]) == q], "exact-base")
    if r: return r

    # 4. exact first name (Kira ×3, Zara ×3)
    r = pick([c for c in chars if _first(c["name"]) == q], "first-name")
    if r: return r

    # 5. exact role phrase
    role_hits = [c for c in chars if q in _norm(c["role"] or "")]
    if len(role_hits) == 1:
        return {"ok": True, "kind": "role", "candidates": role_hits}
    if len(role_hits) > 1:
        return {"ok": True, "kind": "ambiguous", "candidates": role_hits,
                "note": f"{len(role_hits)} characters match role text — re-query with a name"}

    # 6. fuzzy across names + aliases
    pool = {}
    for c in chars:
        base, first = _base(c["name"]), _first(c["name"])
        for key in (base, first, _norm(c["name"])):
            if key:
                pool[key] = c
    for a, t in aliases.items():
        pool.setdefault(a, next((c for c in chars if _norm(c["name"]) == _norm(t)), None))

    matches = difflib.get_close_matches(q, list(pool), n=8, cutoff=0.68)
    if not matches and len(q) <= 8:
        matches = [k for k in pool if _lev(q, k) <= (1 if len(q) <= 4 else 2)]
    seen, fuzzy = set(), []
    for m in matches:
        c = pool[m]
        if c and c["id"] not in seen:
            seen.add(c["id"])
            fuzzy.append(c)
    if fuzzy:
        return {"ok": True, "kind": "fuzzy", "candidates": fuzzy,
                "note": f"typo? matched '{fuzzy[0]['name']}' "
                        f"(similarity {difflib.SequenceMatcher(None, q, _base(fuzzy[0]['name'])).ratio():.2f})"}
    return {"ok": False, "error": f"no character matches '{query}'",
            "suggestions": [c["name"] for c in chars[:5]]}


def resolve_group(group: str, roster: dict, chars: list[dict]) -> dict:
    entries = roster["groups"].get(_norm(group))
    if not entries:
        return {"ok": False, "error": f"no group '{group}'. groups: "
                + ", ".join(sorted(roster["groups"]))}
    members, stale = [], []
    for entry in entries:
        r = resolve_char(entry, chars, roster["aliases"])
        if r.get("ok") and r.get("kind") != "ambiguous":
            members.append(r["candidates"][0])
        elif r.get("ok") and r.get("kind") == "ambiguous":
            members.append({"name": entry, "role": f"⚠ AMBIGUOUS ({len(r['candidates'])} matches)",
                            "bond": None, "is_spouse": False,
                            "scene_location": None, "house_name": None})
        else:
            stale.append(entry)
            members.append({"name": entry, "role": "⚠ STALE — not in DB",
                            "bond": None, "is_spouse": False,
                            "scene_location": None, "house_name": None})
    return {"ok": True, "kind": "group", "group": group,
            "members": members, "stale": stale}


# ─── Loc (territory / coordinate) ────────────────────────────────────────

_terr1000_cache: list | None = None

def _terr1000() -> list:
    global _terr1000_cache
    if _terr1000_cache is None:
        if os.path.exists(TERR_1000_FILE):
            _terr1000_cache = json.load(open(TERR_1000_FILE))
        else:
            _terr1000_cache = []
    return _terr1000_cache


async def resolve_loc(query: str) -> dict:
    q = _norm(query)
    m = re.fullmatch(r"(\d+)\s*,\s*(\d+)(?:\s*,\s*(\d+))?", q)
    if m:
        x, y = int(m.group(1)), int(m.group(2))
        z = int(m.group(3)) if m.group(3) else 2  # z=2 current, z=1 bottom, z=3 top
        if z != 2:
            rows = [dict(r) for r in await Database.fetch(
                "SELECT name, x_coord, y_coord, z_coord, star_type, controlled_by, hazard_level "
                "FROM maya_rp.sectors WHERE z_coord=$1 "
                "ORDER BY (x_coord-$2)^2+(y_coord-$3)^2 LIMIT 5", z, x, y)]
            return {"ok": True, "kind": "coords", "query": (x, y, z), "grid": f"z{z}",
                    "sectors": rows, "note": f"nearest sectors on the z={z} plane"}
        if x > 30 or y > 30:
            # 1000-grid: system names encode "X-Y" coordinates
            systems = []
            for t in _terr1000():
                cm = re.fullmatch(r"(\d+)-(\d+)", t.get("system_name", ""))
                if cm:
                    systems.append((int(cm.group(1)), int(cm.group(2)), t))
            if systems:
                systems.sort(key=lambda s: (s[0] - x) ** 2 + (s[1] - y) ** 2)
                nearest = [{"x": sx, "y": sy, "system_name": t.get("system_name"),
                            "controlling_faction": t.get("controlling_faction") or "unclaimed"}
                           for sx, sy, t in systems[:5]]
                # cross-ref population from territory table where present
                names = [n["system_name"] for n in nearest]
                terr = {r["system_name"]: dict(r) for r in await Database.fetch(
                    "SELECT system_name, population, development_level, governor_name, status "
                    "FROM maya_rp.territory WHERE session_id=$1 AND system_name = ANY($2::text[])",
                    Config.SESSION_ID, names)}
                for n in nearest:
                    n.update(terr.get(n["system_name"], {}))
                return {"ok": True, "kind": "coords", "query": (x, y),
                        "grid": "1000", "systems": nearest,
                        "note": "nearest systems on the 1000-grid"}
        rows = [dict(r) for r in await Database.fetch(
            "SELECT name, x_coord, y_coord, star_type, controlled_by, hazard_level "
            "FROM maya_rp.sectors ORDER BY (x_coord-$1)^2+(y_coord-$2)^2 LIMIT 5", x, y)]
        return {"ok": True, "kind": "coords", "query": (x, y), "grid": "24",
                "sectors": rows, "note": "nearest sectors on the 0–24 sector grid"}
    terr = [dict(r) for r in await Database.fetch(
        "SELECT system_name, controlling_faction, population, development_level, "
        "governor_name, status, crisis_level FROM maya_rp.territory "
        "WHERE session_id=$1 AND LOWER(system_name) LIKE $2 "
        "ORDER BY population DESC LIMIT 10", Config.SESSION_ID, f"%{q}%")]
    sect = [dict(r) for r in await Database.fetch(
        "SELECT name, x_coord, y_coord, z_coord, controlled_by, star_type, hazard_level, hidden "
        "FROM maya_rp.sectors WHERE LOWER(name) LIKE $1 LIMIT 10", f"%{q}%")]
    if terr or sect:
        return {"ok": True, "kind": "name", "territories": terr, "sectors": sect}
    names = [r["system_name"] for r in await Database.fetch(
        "SELECT system_name FROM maya_rp.territory WHERE session_id=$1", Config.SESSION_ID)]
    close = difflib.get_close_matches(q, [_norm(n) for n in names], n=5, cutoff=0.6)
    if close:
        terr = [dict(r) for r in await Database.fetch(
            "SELECT system_name, controlling_faction, population, development_level, "
            "governor_name, status, crisis_level FROM maya_rp.territory "
            "WHERE session_id=$1 AND LOWER(system_name) = ANY($2::text[]) LIMIT 10",
            Config.SESSION_ID, close)]
        return {"ok": True, "kind": "fuzzy", "territories": terr,
                "note": f"typo? matched {close}"}
    return {"ok": False, "error": f"no territory/sector matches '{query}'"}


# ─── Ship ────────────────────────────────────────────────────────────────

async def resolve_ship(query: str) -> dict:
    q = _norm(query)
    rows = [dict(r) for r in await Database.fetch(
        "SELECT name, ship_type, sub_class, tier, hull, hull_current, power_rating, "
        "location, status, veteran_kills FROM maya_rp.ships "
        "WHERE session_id=$1 AND (LOWER(name) LIKE $2 "
        "OR LOWER(COALESCE(sub_class,'')) LIKE $2 OR LOWER(COALESCE(ship_type,'')) LIKE $2) "
        "ORDER BY power_rating DESC LIMIT 10", Config.SESSION_ID, f"%{q}%")]
    if rows:
        return {"ok": True, "kind": "exact-ish", "ships": rows}
    names = [r["name"] for r in await Database.fetch(
        "SELECT name FROM maya_rp.ships WHERE session_id=$1", Config.SESSION_ID)]
    close = difflib.get_close_matches(q, [_norm(n) for n in names], n=5, cutoff=0.6)
    if close:
        rows = [dict(r) for r in await Database.fetch(
            "SELECT name, ship_type, sub_class, tier, hull, hull_current, power_rating, "
            "location, status, veteran_kills FROM maya_rp.ships "
            "WHERE session_id=$1 AND LOWER(name) = ANY($2::text[]) "
            "ORDER BY power_rating DESC", Config.SESSION_ID, close)]
        return {"ok": True, "kind": "fuzzy", "ships": rows,
                "note": f"typo? matched {close}"}
    return {"ok": False, "error": f"no ship matches '{query}'"}


# ─── Output formatters ───────────────────────────────────────────────────

def _fmt_ship(s: dict) -> str:
    kills = f" · {s['veteran_kills']} kills" if s.get("veteran_kills") else ""
    hull = f" · hull {s['hull_current']}/{s['hull']}" if s.get("hull_current") is not None else ""
    return (f"{s['name']} — {s['sub_class'] or s['ship_type']} [T{s['tier']}] "
            f"· power {s['power_rating']:,}{hull}{kills}\n"
            f"   loc: {s['location'] or '—'} · {s['status']}")


async def main():
    args = sys.argv[1:]
    want_json = "--json" in args
    args = [a for a in args if a != "--json"]
    if len(args) < 1:
        print(__doc__)
        return
    cmd, rest = args[0], args[1:]
    await Database.init()
    roster = _load_roster()

    if cmd == "alias":
        if not rest or rest[0] == "list":
            out = {"ok": True, "aliases": roster["aliases"]}
            print(json.dumps(out, ensure_ascii=False, indent=2) if want_json
                  else "\n".join(f"  {a} → {t}" for a, t in sorted(roster["aliases"].items())))
            return
        if rest[0] == "add" and len(rest) >= 3:
            a, target = _norm(rest[1]), " ".join(rest[2:])
            chars = await _load_characters()
            hit = next((c for c in chars if _norm(c["name"]) == _norm(target)
                        or _base(c["name"]) == _base(target)), None)
            if not hit:
                print(json.dumps({"ok": False, "error": f"target '{target}' not found"})
                      if want_json else f"✗ target '{target}' not found in characters")
                return
            roster["aliases"][a] = hit["name"]
            _save_roster(roster)
            print(json.dumps({"ok": True, "alias": a, "target": hit["name"]},
                             ensure_ascii=False) if want_json
                  else f"✅ {a} → {hit['name']}")
            return
        if rest[0] == "rm" and len(rest) >= 2:
            a = _norm(rest[1])
            if a in roster["aliases"]:
                del roster["aliases"][a]
                _save_roster(roster)
            print(json.dumps({"ok": True, "removed": a}) if want_json else f"✅ removed {a}")
            return
        a = _norm(rest[0])
        target = roster["aliases"].get(a)
        print(json.dumps({"ok": bool(target), "alias": a, "target": target},
                         ensure_ascii=False) if want_json
              else (f"✅ {a} → {target}" if target else f"✗ no alias '{rest[0]}'"))
        return

    if cmd == "groups":
        out = {"ok": True, "groups": {g: len(m) for g, m in roster["groups"].items()}}
        print(json.dumps(out, ensure_ascii=False, indent=2) if want_json
              else "\n".join(f"  {g} ({len(m)})" for g, m in sorted(roster["groups"].items())))
        return

    if cmd == "char":
        q = _norm(" ".join(rest))
        chars = await _load_characters()
        if q in roster["groups"]:
            r = resolve_group(q, roster, chars)
            if want_json:
                print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
                return
            print(f"👥 group '{r['group']}' — {len(r['members'])} entries")
            for c in r["members"]:
                crown = " 👑" if c.get("is_spouse") else ""
                bond = f" [bond {c['bond']}]" if c.get("bond") is not None else ""
                print(f"  • {c['name']}{bond}{crown} — {c['role']}")
            if r["stale"]:
                print(f"  ⚠ stale: {', '.join(r['stale'])}")
            return
        r = resolve_char(q, chars, roster["aliases"])
        if want_json:
            print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
            return
        if not r.get("ok"):
            print(f"✗ {r['error']}")
            return
        if r["kind"] == "ambiguous":
            print(f"⚠ {r.get('note', 'ambiguous')}")
            for i, c in enumerate(r["candidates"], 1):
                print(f"  {i}) {c['name']}  [bond {c.get('bond') or 0}]"
                      f"{' 👑' if c.get('is_spouse') else ''} — {c['role'] or '—'}")
            return
        head = {"alias": "🎯", "exact": "✅", "exact-base": "✅", "first-name": "✅",
                "role": "✅", "fuzzy": "🔎"}.get(r["kind"], "✅")
        print(f"{head} {r['candidates'][0]['name']}")
        print(_fmt_char(r["candidates"][0], roster["aliases"]).split("\n", 1)[1])
        if r.get("note"):
            print(f"   {r['note']}")
        return

    if cmd == "loc":
        r = await resolve_loc(" ".join(rest))
        if want_json:
            print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
            return
        if not r.get("ok"):
            print(f"✗ {r['error']}")
            return
        if r["kind"] == "coords":
            if r["grid"] == "1000":
                print(f"📍 nearest systems on 1000-grid to {r['query']}:")
                for s in r["systems"]:
                    extra = ""
                    if s.get("population"):
                        extra = f" · pop {s['population']:,} · {s.get('status') or ''}"
                    print(f"  {s['system_name']} ({s['x']},{s['y']}) — "
                          f"{s.get('controlling_faction') or 'unclaimed'}{extra}")
            else:
                print(f"📍 nearest sectors to grid {r['query']}:")
                for s in r["sectors"]:
                    zc = s.get("z_coord", 2)
                    print(f"  z{zc} {s['name']} ({s['x_coord']},{s['y_coord']}) — "
                          f"{s['controlled_by'] or 'uncontrolled'} · {s['star_type'] or '?'} · "
                          f"hazard {s['hazard_level']}")
            if r.get("note"):
                print(f"   {r['note']}")
            return
        if r.get("territories"):
            print("🌍 territories:")
            for t in r["territories"]:
                gov = f" · gov {t['governor_name']}" if t.get("governor_name") else ""
                print(f"  {t['system_name']} — {t['controlling_faction']} · "
                      f"pop {t['population']:,} · dev {t['development_level']}"
                      f" · {t['status']}{gov}")
        if r.get("sectors"):
            print("📍 sectors:")
            for s in r["sectors"]:
                zc = s.get("z_coord", 2)
                tag = " 🕳 hidden" if s.get("hidden") else ""
                print(f"  z{zc} {s['name']} ({s['x_coord']},{s['y_coord']}) — "
                      f"{s['controlled_by'] or 'uncontrolled'}{tag}")
        if r.get("note"):
            print(f"   {r['note']}")
        return

    if cmd == "ship":
        r = await resolve_ship(" ".join(rest))
        if want_json:
            print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
            return
        if not r.get("ok"):
            print(f"✗ {r['error']}")
            return
        for s in r["ships"]:
            print(_fmt_ship(s))
        if r.get("note"):
            print(f"   {r['note']}")
        return

    print(__doc__)


if __name__ == "__main__":
    asyncio.run(main())
