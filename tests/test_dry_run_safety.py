"""A dry run must not write. The mutating scripts run against the live database.

Four scripts can redistribute the world: `faction_scale.py` releases territory,
`ship_fleet.py` deals hulls to factions, `ship_tiers.py` re-tiers hulls, and
`faction_stance.py` rewrites every faction's stance. Each one offers a dry run, and the
only thing that makes that offer trustworthy is a test that proves it.

The fingerprint is a row count plus an md5 over the ordered values, so a single changed
cell fails the test rather than sliding under a count. Timestamp columns are included
where they exist, and they are the reason this gate works at all: a model that recomputes
the same values writes the same numbers, so a fingerprint over values alone is blind to
it. That was measured, not assumed: the first version of this test passed against a
mutation that wrote stances it had just recalculated.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

TABLES = {
    "research_queue": "SELECT count(*), md5(string_agg(id::text || coalesce(programme_days::text,'') || coalesce(status,''), '|' ORDER BY id)) FROM maya_rp.research_queue",
    "factions": "SELECT count(*), md5(string_agg(id::text || coalesce(stance,'') || coalesce(stance_score::text,'') || coalesce(stance_at::text,'') || coalesce(systems_held::text,'') || coalesce(scale_class,'') || coalesce(doctrine,'') || coalesce(origin,'') || coalesce(trust::text,''), '|' ORDER BY id)) FROM maya_rp.factions",
    "ships": "SELECT count(*), md5(string_agg(id::text || coalesce(tier::text,'') || coalesce(faction_id::text,'') || coalesce(class_id::text,''), '|' ORDER BY id)) FROM maya_rp.ships",
    "territory": "SELECT count(*), md5(string_agg(id::text || coalesce(controlling_faction,'') || coalesce(contested_by::text,'') || coalesce(updated_at::text,''), '|' ORDER BY id)) FROM maya_rp.territory",
}

DRY_RUNS = (
    ("faction_stance.py", ["--dry-run"]),
    ("faction_scale.py", ["--dry-run"]),
    ("ship_tiers.py", ["--dry-run"]),
    ("ship_fleet.py", ["--dry-run"]),
)


def _connect():
    import psycopg2

    env = pathlib.Path.home() / ".env"
    if env.is_file() and not os.environ.get("OC_PG_HOST"):
        for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, _, value = line.partition("=")
                key = key.removeprefix("export ").strip()
                if key.startswith(("OC_PG_", "POSTGRES_")) and key not in os.environ:
                    os.environ[key] = value.strip().strip("'\"")
    if not os.environ.get("OC_PG_HOST"):
        pytest.skip("no OC_PG_* connection settings; the dry-run gate needs the database")
    return psycopg2.connect(
        host=os.environ["OC_PG_HOST"], port=int(os.environ.get("OC_PG_PORT", 5432)),
        user=os.environ["OC_PG_USER"], password=os.environ.get("OC_PG_PASS"),
        dbname=os.environ.get("OC_PG_DB", "maya_memory"))


def _fingerprint() -> dict[str, tuple[int, str]]:
    conn = _connect()
    try:
        cur = conn.cursor()
        out = {}
        for name, sql in TABLES.items():
            cur.execute(sql)
            count, digest = cur.fetchone()
            out[name] = (int(count), str(digest))
        return out
    finally:
        conn.close()


@pytest.fixture()
def fingerprints():
    before = _fingerprint()
    yield before
    after = _fingerprint()
    assert before == after, "a dry run changed the database"


@pytest.mark.parametrize("script,args", DRY_RUNS)
def test_dry_run_exits_clean_and_writes_nothing(script, args, fingerprints):
    env = {**os.environ, "DEEPSEEK_API_KEY": os.environ.get("DEEPSEEK_API_KEY", "test-key")}
    result = subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                            capture_output=True, text=True, cwd=str(ROOT), env=env, timeout=600)
    assert result.returncode == 0, f"{script} failed: {result.stderr[-600:]}"
    assert "dry run" in result.stdout.lower() or "nothing written" in result.stdout.lower(), (
        f"{script} did not say it wrote nothing: {result.stdout[-300:]}"
    )


PROGRAMME_DRY = (
    ("list", ["programme", "list"]),
    ("quote", ["programme", "quote", "--tier=5"]),
    ("tick", ["programme", "tick", "--session=3"]),
    ("kill", ["programme", "kill", "--target=1", "--spend=3"]),
)


@pytest.mark.parametrize("label,args", PROGRAMME_DRY)
def test_programme_commands_are_dry_by_default(label, args, fingerprints):
    """The programme surface must not write unless it is told to.

    The magic CLI wrote to the campaign during a manual check, so this gate now covers the
    programme commands too: `list` and `quote` read, and `tick` and `kill` print a plan and
    stop unless `--apply` is present.
    """
    env = {**os.environ, "DEEPSEEK_API_KEY": os.environ.get("DEEPSEEK_API_KEY", "test-key")}
    result = subprocess.run([sys.executable, str(SCRIPTS / "cli.py"), *args],
                            capture_output=True, text=True, cwd=str(ROOT), env=env, timeout=300)
    assert result.returncode == 0, f"{label} failed: {result.stderr[-400:]}"
    if label in ("tick", "kill"):
        assert "dry run" in result.stdout or "nothing written" in result.stdout, result.stdout[-300:]
