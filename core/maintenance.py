"""Maintenance mode for the RP and OOC engines.

Armed by the operator phrase "GM MAYA". While armed:
  - the register guard stands down: edits are not billed to deviation, and the
    turn's decay does not settle either, so the number stands still
  - each audit row is still written, as skipped/maintenance, so the ledger shows
    why nothing moved instead of showing a gap
  - a frozen campaign accepts writes again, which is the only way to repair one
  - the session resolver answers None: the operator names the session explicitly

Never armed while a play session is live. The module refuses unless forced,
and the force path is meant for the operator at the console.
"""
from __future__ import annotations

import json
import os
import pathlib
import time

PHRASE = "GM MAYA"
SCOPE = ("ooc", "rp")
DEFAULT_TTL_SECONDS = 12 * 60 * 60

STATE_DIR = pathlib.Path(os.environ.get("RP_MAINT_DIR", pathlib.Path.home() / ".config" / "rp-engine"))
STATE_FILE = STATE_DIR / "maintenance.json"
PLAY_FLAG = STATE_DIR / "play.lock"


def _read() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def _write(d: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=2) + "\n")
    tmp.replace(STATE_FILE)


def play_is_live() -> bool:
    return PLAY_FLAG.exists()


def status() -> dict:
    d = _read()
    if not d.get("active"):
        return {"active": False}
    if float(d.get("expires_at", 0)) < time.time():
        d["active"] = False
        d["expired_at"] = time.time()
        _write(d)
        return {"active": False, "expired": True}
    return d


def active() -> bool:
    return bool(status().get("active"))


def arm(phrase: str, source: str = "operator", ttl: int = DEFAULT_TTL_SECONDS, force: bool = False) -> dict:
    if phrase != PHRASE:
        raise PermissionError("maintenance phrase rejected")
    if play_is_live() and not force:
        raise RuntimeError("a play session is live; maintenance refused")
    now = time.time()
    d = {
        "active": True,
        "phrase": PHRASE,
        "scope": list(SCOPE),
        "armed_at": now,
        "armed_by": source,
        "expires_at": now + ttl,
    }
    _write(d)
    return d


def disarm(reason: str = "operator") -> dict:
    d = _read()
    d["active"] = False
    d["disarmed_at"] = time.time()
    d["disarm_reason"] = reason
    _write(d)
    return d
