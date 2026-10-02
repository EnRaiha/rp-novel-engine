#!/usr/bin/env python3
"""The grand plan's own definition of done, as a check that prints PASS or FAIL per line.

`wiki/rp-dev/GRAND-PLAN-2026-10-02.md` section 8 names five criteria for v1.0. Writing them as prose
lets anyone claim them; writing them as a script makes the claim cost one command. Nothing here
writes: it reads the engine, the vault and the unit tests' own gates.

    python3 scripts/plan_status.py
    python3 scripts/plan_status.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

VAULT = pathlib.Path(__file__).resolve().parents[2]
ENGINE = VAULT / "rp-engine-py"

#: Migrations this work applied and recorded. A rebuild replays `_migrations`, so a missing row
#: means the DDL is live and unreproducible.
EXPECTED_MIGRATIONS = (
    "115_faction_axes.sql", "116_world_models.sql", "117_trust_numeric.sql",
    "118_migration_bookkeeping.sql", "119_science_assassination.sql",
    "123_migration_bookkeeping.sql", "124_affection.sql",
)

#: Scripts that write to the database. Each must appear in the dry-run gate, or the gate is a
#: promise the tests do not keep.
MUTATORS = (
    "faction_stance.py", "faction_scale.py", "ship_tiers.py", "ship_fleet.py",
    "restore_mythic_tiers.py",
)

GATE_FILE = "rp-engine-py/tests/test_dry_run_safety.py"
ARC1_RANGE = (2931, 2993)


def connect():
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
        raise SystemExit("no OC_PG_* settings; the status check reads the engine")
    return psycopg2.connect(host=os.environ["OC_PG_HOST"],
                            port=int(os.environ.get("OC_PG_PORT", 5432)),
                            user=os.environ["OC_PG_USER"],
                            password=os.environ.get("OC_PG_PASS"),
                            dbname=os.environ.get("OC_PG_DB", "maya_memory"))


def check_migrations(cur) -> tuple[bool, str]:
    cur.execute("SELECT name FROM maya_rp._migrations")
    recorded = {row[0] for row in cur.fetchall()}
    missing = [name for name in EXPECTED_MIGRATIONS if name not in recorded]
    return not missing, f"recorded {len(EXPECTED_MIGRATIONS) - len(missing)}/{len(EXPECTED_MIGRATIONS)}" + (
        f"; missing {missing}" if missing else "")


def check_frozen_session(cur) -> tuple[bool, str]:
    cur.execute("SELECT session_id, deviation, audits FROM maya_rp.ooc_system_state ORDER BY session_id")
    rows = {r[0]: (r[1], r[2]) for r in cur.fetchall()}
    frozen = pathlib.Path.home() / ".config/rp-engine/frozen_sessions"
    arc = pathlib.Path.home() / ".config/rp-engine/active_arc"
    frozen_text = frozen.read_text().strip() if frozen.is_file() else ""
    arc_text = arc.read_text().strip() if arc.is_file() else ""
    live = rows.get(5, (None, None))
    ok = "3" in frozen_text.split() and arc_text == "5" and live[0] is not None
    return ok, (f"active_arc={arc_text or '?'} · frozen=[{frozen_text}] · "
                f"session 5 deviation={live[0]} audits={live[1]}")


def check_every_confirmed_wife_has_a_face(cur) -> tuple[bool, str]:
    """The 35 confirmed wives, each with her face. Amended from the Arc I cast.

    The plan first asked for the 63 Arc I characters. The King ruled on 2026-10-02: faces only, and
    only the 35 confirmed wives, no to other. So the criterion follows the ruling, and the Arc I
    count is reported beside it as a fact rather than a target.
    """
    cur.execute("""SELECT count(*) FROM maya_rp.characters
                   WHERE session_id = 5 AND traits::text ILIKE '%confirmed-wife%'""")
    wives = cur.fetchone()[0]
    # The portrait assets hang off the session-3 rows, not the session-5 twins, so the face of a
    # wife is found through a name join into the frozen session. Same shape as the manifest's tier
    # resolution, and the same fragility: it is the only link between the face and the live row.
    cur.execute("""SELECT count(DISTINCT w.id) FROM maya_rp.characters w
                   JOIN maya_rp.characters t ON t.session_id = 3 AND t.name = w.name
                   JOIN maya_rp.character_assets a ON a.character_id = t.id
                   WHERE w.session_id = 5 AND w.traits::text ILIKE '%confirmed-wife%'
                     AND a.kind = 'portrait' AND a.status = 'ready'""")
    faced = cur.fetchone()[0]
    cur.execute("""SELECT count(*) FROM maya_rp.characters c
                   JOIN maya_rp.character_assets a ON a.character_id = c.id
                   WHERE c.session_id = 5 AND c.id BETWEEN %s AND %s
                     AND a.kind = 'portrait' AND a.status = 'ready'""", ARC1_RANGE)
    arc = cur.fetchone()[0]
    return faced >= wives, (f"{faced}/{wives} confirmed wives have a face"
                            f"; Arc I cast {arc} (declined by ruling)")


def check_illustrated_novel() -> tuple[bool, str]:
    """The compiler path exists and the illustrated edition carries faces."""
    script = ENGINE / "scripts/novel_faces.py"
    if not script.is_file():
        return False, "novel_faces.py is missing"
    edition = VAULT / "adventures/tkg-arc1-restart/novel/the-sunrise-illustrated.md"
    if not edition.is_file():
        return False, "the illustrated edition has not been built (no face exists in the manuscript)"
    images = edition.read_text(encoding="utf-8").count("![id ")
    return images > 0, f"the illustrated edition carries {images} image(s)"


def check_mutators_are_gated() -> tuple[bool, str]:
    gate = (VAULT / GATE_FILE).read_text(encoding="utf-8")
    ungated = [name for name in MUTATORS if name not in gate]
    return not ungated, ("every mutating script is in the dry-run gate" if not ungated
                         else f"not in the gate: {ungated}")


def check_images_reach_the_chat(proxy_path: pathlib.Path | None = None,
                                decorator_path: pathlib.Path | None = None) -> tuple[bool, str]:
    """Criterion 5: images appear in the chat without a terminal.

    The plan named the host plugin row as the way. Route B reaches the same outcome through the auth
    proxy, which already injects files into every HTML document, so this checks the outcome and names
    which path is carrying it. Measuring the mechanism rather than the result would report a failure
    for a working feature.
    """
    proxy = proxy_path or pathlib.Path.home() / "scripts" / "dsh-auth-proxy"
    decorator = decorator_path or pathlib.Path.home() / ".config/dsh-auth/portrait-chat.js"
    if not proxy.is_file():
        return False, "the proxy script is missing"
    text = proxy.read_text(encoding="utf-8")
    wired = ('"/__dsh-portrait-chat.js"' in text
             and 'src="/__dsh-portrait-chat.js"' in text)
    if not wired:
        return False, "the portrait decorator is not wired into the proxy"
    if not decorator.is_file():
        return False, "the proxy is wired but the decorator has not been generated"
    import subprocess
    import sys as _sys

    check = subprocess.run([_sys.executable, str(ENGINE / "scripts" / "portrait_chat_js.py"), "--check"],
                           capture_output=True, text=True, timeout=120)
    current = check.returncode == 0
    size = decorator.stat().st_size
    return current, (f"route B carries it: proxy wired, decorator {size} bytes"
                     + ("" if current else " and STALE, regenerate it"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    conn = connect()
    cur = conn.cursor()
    checks = [
        ("1. migrations are recorded", check_migrations(cur)),
        ("2. session 3 frozen, session 5 live", check_frozen_session(cur)),
        ("3. every confirmed wife has a face", check_every_confirmed_wife_has_a_face(cur)),
        ("4. the illustrated novel carries faces", check_illustrated_novel()),  # void by ruling
        ("5. every mutating script is dry-run gated", check_mutators_are_gated()),
        ("6. images reach the chat", check_images_reach_the_chat()),
    ]
    conn.close()

    if args.json:
        print(json.dumps([{"check": name, "pass": ok, "evidence": detail}
                          for name, (ok, detail) in checks], indent=1))
        return 0

    passed = sum(1 for _, (ok, _) in checks if ok)
    for name, (ok, detail) in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        print(f"        {detail}")
    print(f"v1.0 criteria: {passed}/{len(checks)} met")
    return 0


if __name__ == "__main__":
    sys.exit(main())
