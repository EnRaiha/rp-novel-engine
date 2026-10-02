#!/usr/bin/env python3
"""Face manifest: the portrait contract the attachment plugin reads.

One generated row per character and portrait key. Sources: the character rows of
the live session 5, the asset rows of frozen session 3 (every render row is
stamped session 3), and the character tree on disk. It is a derived cache:
rebuild and diff, never edit.

Wives first (D1). Session 5 records no spouse, so the wife tier comes from an
exact name join into session 3, and each row keeps the session-3 id it matched on
in `twin`. A merge that gives session 5 a real wife flag is the eventual fix.

    cd rp-engine-py && python3 scripts/face_manifest.py --stats

`--format json` writes `faces/manifest.json` instead, the same rows in the shape the
attachment plugin loads (`file` is a boolean there); markdown stays the default.

Deterministic: the same tree plus the same database row set gives the same rows
in the same order; only the generated-at header line carries a clock. Read-only:
this script issues SELECT statements and nothing else.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from core.portraits import EMOTIONS, OCCASIONS, character_dir, parse_traits  # noqa: E402

VAULT_ROOT = pathlib.Path.home() / "Bumi-Hijau"
FACES_DIR = VAULT_ROOT / "adventures" / "tkg-arc1-restart" / "prototype" / "faces"
DEFAULT_OUT = pathlib.Path(
    os.environ.get("TKG_FACE_MANIFEST_OUT") or str(FACES_DIR / "MANIFEST.md")
)
DEFAULT_JSON_OUT = pathlib.Path(
    os.environ.get("TKG_FACE_MANIFEST_JSON_OUT") or str(FACES_DIR / "manifest.json")
)
ACTIVE_SESSION = 5
TWIN_SESSION = 3
VILLAINESS_IDS = (2159, 2208, 2211)
ARC1_PREFIX = "Arc I: The Descent (The Sunrise)"
TIERS = ("wife", "villainess", "arc1-cast", "import", "prisoner", "other")
HAIR_KEYS = ("bun", "unbun", "braid", "ponytail", "halfup", "tudung")
KEYS = tuple(EMOTIONS)
STATUS_ORDER = ("ready", "gap", "pending", "failed")
QUEUE_RANK = {"ready": 0, "failed": 1, "pending": 2}
EMPTY = "-"

CHARACTER_SQL = """
    SELECT id, session_id, name, background, traits, is_spouse, romance_stage
      FROM maya_rp.characters WHERE session_id IN (%s, %s) ORDER BY session_id, id
"""
ASSET_SQL = """
    SELECT session_id, character_id, occasion, status FROM maya_rp.character_assets
      WHERE kind = 'portrait' ORDER BY session_id, character_id, occasion
"""


def load_env() -> None:
    """Postgres settings from `~/.env`, the same rule the other scripts use."""
    env = pathlib.Path.home() / ".env"
    if not env.is_file() or os.environ.get("OC_PG_HOST"):
        return
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        key, _, value = line.partition("=")
        key = key.removeprefix("export ").strip()
        if key.startswith(("OC_PG_", "POSTGRES_")) and key not in os.environ:
            os.environ[key] = value.strip().strip("'\"")


def connect():
    import psycopg2

    load_env()
    return psycopg2.connect(
        host=os.environ["OC_PG_HOST"],
        port=int(os.environ.get("OC_PG_PORT", 5432)),
        user=os.environ["OC_PG_USER"],
        password=os.environ["OC_PG_PASS"],
        dbname=os.environ.get("OC_PG_DB", "maya_memory"),
    )


#: The durable marker for a confirmed wife. The King confirmed 35 on 2026-10-02.
WIFE_TRAIT = "confirmed-wife"


def tier_of(row: dict, wife_names: set[str]) -> str:
    """Tier for one character row, first match wins, in TIERS order.

    A wife is recognised by her trait first, because a trait travels with the row. The name join
    into session 3 stays as the fallback for any spouse the trait has not reached yet, since
    session 5 records no `is_spouse` of its own.
    """
    if WIFE_TRAIT in parse_traits(row["traits"]) or row["name"] in wife_names:
        return "wife"
    if row["id"] in VILLAINESS_IDS:
        return "villainess"
    if str(row["background"] or "").startswith(ARC1_PREFIX):
        return "arc1-cast"
    traits = parse_traits(row["traits"])
    if "imported" in traits:
        return "import"
    if "prisoner" in traits:
        return "prisoner"
    return "other"


def as_key(occasion: str) -> str:
    """Asset rows are keyed by occasion; the manifest is keyed by emotion key."""
    return OCCASIONS.get(occasion, (occasion, ()))[0]


def queue_status(cid: int, key: str, assets: dict) -> str:
    """`pending`, `failed`, or `gap`; a `ready` row with no file reads `failed`."""
    state = assets.get((TWIN_SESSION, cid, key))
    if state is None:
        return "gap"
    return state if state in ("pending", "failed") else "failed"


def build(characters: list[dict], assets: dict) -> list[dict]:
    """One row per character and key, sorted by tier order, name, then key."""
    wife_names = {
        r["name"]
        for r in characters
        if r["session_id"] == TWIN_SESSION and (r["is_spouse"] or r["romance_stage"] == "married")
    }
    by_name = {r["name"]: r["id"] for r in characters if r["session_id"] == TWIN_SESSION}
    live = [r for r in characters if r["session_id"] == ACTIVE_SESSION]
    out: list[dict] = []
    for row in live:
        twin = by_name.get(row["name"])
        tier = tier_of(row, wife_names)
        folder = character_dir(row["name"], twin or row["id"])
        code = twin if twin is not None else row["id"]
        for key in KEYS:
            path = folder / "emotions" / f"{key}.png"
            exists = path.is_file()
            rel = None
            if exists:
                try:
                    rel = path.relative_to(VAULT_ROOT).as_posix()
                except ValueError:
                    rel = path.as_posix()
            status = "ready" if exists else queue_status(code, key, assets)
            out.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "twin": twin,
                    "tier": tier,
                    "key": key,
                    "kind": "hair" if key in HAIR_KEYS else "emotion",
                    "path": rel,
                    "exists": "yes" if exists else "no",
                    "status": status,
                }
            )
    out.sort(key=lambda r: (TIERS.index(r["tier"]), r["name"], KEYS.index(r["key"])))
    return out


def tally(rows: list[dict]) -> tuple[dict, dict, dict]:
    tiers = {t: 0 for t in TIERS}
    keys = {k: {s: 0 for s in STATUS_ORDER} for k in KEYS}
    status = {s: 0 for s in STATUS_ORDER}
    for r in rows:
        tiers[r["tier"]] += 1
        keys[r["key"]][r["status"]] += 1
        status[r["status"]] += 1
    return tiers, keys, status


def render(rows: list[dict], chars: int, generated_at: str, out: pathlib.Path) -> str:
    tiers, keys, status = tally(rows)
    files = sum(1 for r in rows if r["exists"] == "yes")
    emotion_keys = [k for k in KEYS if k not in HAIR_KEYS]
    lines = [
        "# Face manifest",
        "",
        f"Generated {generated_at} by `rp-engine-py/scripts/face_manifest.py`. This file is derived;",
        "rebuild it rather than editing it: `cd rp-engine-py && python3 scripts/face_manifest.py --stats`.",
        "",
        f"Rows: {len(rows)} = {chars} characters x {len(KEYS)} keys"
        f" ({len(emotion_keys)} emotion, {len(HAIR_KEYS)} hair). Files on disk: {files}.",
        "Tiers: " + ", ".join(f"{t} {tiers[t]}" for t in TIERS) + ".",
        "Status: " + ", ".join(f"{s} {status[s]}" for s in STATUS_ORDER) + ".",
        "",
        f"`id` is the session-{ACTIVE_SESSION} id. `twin` is the session-{TWIN_SESSION} id matched on exact name,"
        f" or {EMPTY}.",
        "`path` is relative to the vault root, "
        f"{EMPTY} when no file exists. A missing image keeps its row so the plugin reports it.",
        f"The emotion set is present exactly as the tree has it: `{'`, `'.join(emotion_keys)}`.",
        "`angry` has no file anywhere; it appears per character as `gap`, or as `pending` where it is queued.",
        "",
        "| id | name | twin | tier | emotion | kind | path | file | status |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['id']} | {r['name']} | {r['twin'] if r['twin'] is not None else EMPTY} | {r['tier']} "
            f"| {r['key']} | {r['kind']} | {r['path'] or EMPTY} | {r['exists']} | {r['status']} |"
        )
    lines.append("")
    text = "\n".join(lines)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return text


def match_keys(name: str) -> list[str]:
    """The strings prose may use for this character, derived from the stored name.

    Deterministic, and deliberately conservative:

    - the stored name itself, so `Queen Onyx Sable` matches as written;
    - the part before any parenthetical epithet, so `Maya al-Dabaran (Anchor)` matches
      as `Maya al-Dabaran`, which is how the novel usually names her;
    - the epithet alone only when it is a single or two-word proper form, because the
      novel writes `Rook Crow (Den)` and later `Den` for the same person.

    A one-word key is NOT derived from a longer name. `Zara` inside `Zara-beth` is the
    resolver's whole-word rule to catch, and a generator that emits partial first names
    would make collisions out of every shared given name.
    """
    keys: list[str] = []
    stored = " ".join(name.split())
    if stored:
        keys.append(stored)
    stem = stored.split("(", 1)[0].strip()
    if stem and stem not in keys:
        keys.append(stem)
    if "(" in stored and stored.endswith(")"):
        epithet = stored[stored.index("(") + 1 : -1].strip()
        if epithet and len(epithet.split()) <= 2 and epithet not in keys:
            keys.append(epithet)
    return keys


def prune_shared_keys(names: list[str]) -> dict[str, list[str]]:
    """Keys for every character, with the cross-collisions removed.

    A single-word epithet is a useful key until it is also part of somebody else's name. `Queen`
    is a key for `Rook Thorn (Queen)` and it sits inside `Queen Onyx Sable`, so prose about Onyx
    would attach Thorn as well. The measured cases were `Queen`, and any title word shared by two
    characters.

    Multi-word keys are kept: `Pirate Queen` is shared by 21 characters, and the resolver refuses a
    key that maps to more than one of them, which is the correct answer rather than a wrong face.

    @param names - every character name in the manifest.
    @returns {name: keys} where no key is both one word and a substring of another name.
    """
    lowered = [name.lower() for name in names]
    out: dict[str, list[str]] = {}
    for index, name in enumerate(names):
        keys = []
        for key in match_keys(name):
            if len(key.split()) == 1:
                others = [other for position, other in enumerate(lowered) if position != index]
                if any(key.lower() in other for other in others):
                    continue
            keys.append(key)
        out[name] = keys
    return out


def json_row(r: dict, keys: list[str] | None = None) -> dict:
    """The same row as `render` prints, with `exists` named for what it means.

    @param keys - the pruned key list for this character, from `prune_shared_keys`.
    """
    return {
        "id": r["id"],
        "name": r["name"],
        "keys": keys if keys is not None else match_keys(r["name"]),
        "twin": r["twin"],
        "tier": r["tier"],
        "key": r["key"],
        "kind": r["kind"],
        "path": r["path"],
        "file": r["exists"] == "yes",
        "status": r["status"],
    }


def render_json(rows: list[dict], chars: int, generated_at: str, out: pathlib.Path) -> str:
    """The same rows as `render`, as JSON for the attachment plugin."""
    # One word keys that also sit inside another character's name are dropped here, in a batch,
    # because the check needs every name at once.
    pruned = prune_shared_keys(sorted({str(r["name"]) for r in rows}))
    payload = {
        "generated_at": generated_at,
        "session": ACTIVE_SESSION,
        "characters": chars,
        "keys": len(KEYS),
        "rows": [json_row(r, pruned.get(r["name"])) for r in rows],
    }
    text = json.dumps(payload, indent=1) + "\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the TKG face manifest (read-only).")
    parser.add_argument(
        "--format",
        choices=("md", "json"),
        default="md",
        help="md (default) renders MANIFEST.md; json writes the plugin's manifest.json",
    )
    parser.add_argument("--out", type=pathlib.Path, default=None)
    parser.add_argument("--stats", action="store_true", help="print counts per tier and per key")
    args = parser.parse_args()
    out = args.out or (DEFAULT_JSON_OUT if args.format == "json" else DEFAULT_OUT)

    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(CHARACTER_SQL, (TWIN_SESSION, ACTIVE_SESSION))
        columns = ("id", "session_id", "name", "background", "traits", "is_spouse", "romance_stage")
        characters = [dict(zip(columns, row)) for row in cur.fetchall()]
        cur.execute(ASSET_SQL)
        assets: dict = {}
        for sid, cid, occasion, state in cur.fetchall():
            key = as_key(occasion)
            if key not in KEYS:
                continue
            slot = (sid, cid, key)
            if QUEUE_RANK.get(state, 0) > QUEUE_RANK.get(assets.get(slot, ""), -1):
                assets[slot] = state
    finally:
        conn.close()

    rows = build(characters, assets)
    chars = sum(1 for r in characters if r["session_id"] == ACTIVE_SESSION)
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    if args.format == "json":
        render_json(rows, chars, generated_at, out)
    else:
        render(rows, chars, generated_at, out)

    if args.stats:
        tiers, keys, _ = tally(rows)
        print("tiers: " + ", ".join(f"{t}={tiers[t]}" for t in TIERS))
        for key in KEYS:
            kind = "hair" if key in HAIR_KEYS else "emotion"
            counts = keys[key]
            body = ", ".join(f"{s}={counts[s]}" for s in STATUS_ORDER if counts[s])
            print(f"key {key} kind={kind} rows={sum(counts.values())} {body}".rstrip())
    files = sum(1 for r in rows if r["exists"] == "yes")
    print(f"manifest: {chars} characters, {len(rows)} rows, {files} files on disk -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
