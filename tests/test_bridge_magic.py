"""The bridge carries a magic declaration to the audit, and a preview writes nothing.

The harness reaches the engine through `scripts/ooc_bridge.py`, so the magic hook is only
end-to-end once the bridge forwards it. These tests drive the bridge the way the plugin does:
one JSON request on stdin, one JSON answer on stdout.

Every request here uses `preview`, because a real turn writes.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "scripts/ooc_bridge.py"


def _run(request: dict, timeout: int = 180) -> dict:
    env = {**os.environ, "DEEPSEEK_API_KEY": os.environ.get("DEEPSEEK_API_KEY", "test-key")}
    result = subprocess.run([sys.executable, str(BRIDGE)], input=json.dumps(request),
                            capture_output=True, text=True, cwd=str(ROOT), env=env, timeout=timeout)
    assert result.stdout.strip(), result.stderr[-500:]
    return json.loads(result.stdout.strip().splitlines()[-1])


def _state() -> tuple:
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
        pytest.skip("no OC_PG_* settings")
    conn = psycopg2.connect(host=os.environ["OC_PG_HOST"], port=int(os.environ.get("OC_PG_PORT", 5432)),
                            user=os.environ["OC_PG_USER"], password=os.environ.get("OC_PG_PASS"),
                            dbname=os.environ.get("OC_PG_DB", "maya_memory"))
    try:
        cur = conn.cursor()
        cur.execute("SELECT deviation, audits FROM maya_rp.ooc_system_state WHERE session_id=5")
        return cur.fetchone()
    finally:
        conn.close()


@pytest.fixture()
def state_guard():
    before = _state()
    yield before
    assert _state() == before, "a preview request changed session 5"


def test_an_undeclared_turn_prices_at_zero(state_guard):
    answer = _run({"call": "turn", "session_id": 5, "preview": True,
                   "text": "Dia meletakkan cawan itu di atas meja."})
    assert answer["ok"] is True
    assert answer["magic_delta"] == 0
    assert answer["magic"]["acts"] == []


def test_a_declared_act_is_priced_and_witnessed(state_guard):
    answer = _run({"call": "turn", "session_id": 5, "preview": True,
                   "text": "Dia menutup luka itu dengan air.",
                   "magic_acts": ["well:close_wound"], "magic_witnessed": True})
    assert answer["magic_delta"] == 6
    assert answer["magic"]["suspicion"] == 4
    assert answer["suspicion_reason"] == "magic"


def test_an_instrument_raises_a_record(state_guard):
    answer = _run({"call": "turn", "session_id": 5, "preview": True,
                   "text": "Dia menutup luka itu dengan air.",
                   "magic_acts": ["well:close_wound"], "magic_witnessed": True,
                   "magic_instrument": True})
    assert answer["magic"]["record"] is True


def test_an_unknown_act_is_reported_not_priced(state_guard):
    answer = _run({"call": "turn", "session_id": 5, "preview": True,
                   "text": "Dia melakukan sesuatu.",
                   "magic_acts": ["not:a_key"]})
    assert answer["magic"]["unknown"] == ["not:a_key"]
    assert answer["magic_delta"] == 0
