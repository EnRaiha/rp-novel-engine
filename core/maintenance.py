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
import tempfile
import time

PHRASE = "GM MAYA"
SCOPE = ("ooc", "rp")
DEFAULT_TTL_SECONDS = 12 * 60 * 60

STATE_DIR = pathlib.Path(os.environ.get("RP_MAINT_DIR", pathlib.Path.home() / ".config" / "rp-engine"))
STATE_FILE = STATE_DIR / "maintenance.json"
PLAY_FLAG = STATE_DIR / "play.lock"
PLAY_FLAG_TTL_SECONDS = 6 * 60 * 60  # upper bound on a play flag's life; see play_is_live


def _read() -> dict:
    """Read the state file.

    Missing is empty: the engine has never been armed. Unreadable or corrupt is not the same thing,
    and returning `{}` for both made a broken override read as "not armed" — the register guard
    resumed billing deviation and a frozen campaign refused writes again, with nothing on screen to
    say why. The failure is carried out in the dict now instead of swallowed here.
    """
    try:
        data = json.loads(STATE_FILE.read_text())
    except FileNotFoundError:
        return {}
    except Exception as e:  # noqa: BLE001 - carried out to the caller, not swallowed
        return {"_unreadable": f"{type(e).__name__}: {e}"}
    if not isinstance(data, dict):
        # `[]` or `null` parsed cleanly and `.get` then raised AttributeError out of `active()`,
        # which the register guard and the session resolver call every turn.
        return {"_unreadable": f"state is {type(data).__name__}, expected an object"}
    return data


def _write(d: dict) -> None:
    """Replace the state file atomically through a uniquely named temp file.

    A fixed `maintenance.tmp` let two writers truncate each other's temp file before `replace`.

    @param d - full record to persist.
    @returns None
    """
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=STATE_FILE.parent, prefix=f".{STATE_FILE.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(json.dumps(d, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, STATE_FILE)
    except BaseException:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by another user
    except OSError:
        return False
    return True


def mark_play(live: bool, pid: int | None = None) -> None:
    """Raise or lower the play-session flag that `arm()` checks.

    The flag had a reader and no writer, so "never armed while a play session is live" never held:
    GM MAYA could be armed mid-play. The writer is `gm_maint.py play on|off`.

    @param live True writes the flag atomically (tmp file, then replace); False removes it and is
        idempotent, a missing file is fine.
    @param pid The play process's pid, recorded so `play_is_live` can tell a crashed player from a
        live one. The caller supplies it: the CLI that writes the flag exits at once, so its own pid
        says nothing about the session. None records no pid, and liveness is then age-only.
    @returns None
    """
    if not live:
        try:
            PLAY_FLAG.unlink()
        except FileNotFoundError:
            pass
        return
    PLAY_FLAG.parent.mkdir(parents=True, exist_ok=True)
    tmp = PLAY_FLAG.with_suffix(".tmp")
    tmp.write_text(json.dumps({"pid": pid, "since": time.time()}) + "\n")
    tmp.replace(PLAY_FLAG)


def play_is_live() -> bool:
    """Whether a play session holds the flag.

    Staleness rule: a crashed player must not block maintenance forever, so the flag counts only
    while it can still be true.
      - flag absent: not live
      - flag older than PLAY_FLAG_TTL_SECONDS (by mtime): stale, whatever the pid says
      - recorded pid: live only if that process exists (`os.kill(pid, 0)`; PermissionError = exists)
      - no readable pid (pid=None, empty or legacy content): live while younger than the TTL
    `arm(force=True)` stays the operator's override.

    @returns True when maintenance must refuse to arm.
    """
    try:
        age = time.time() - PLAY_FLAG.stat().st_mtime
        raw = PLAY_FLAG.read_text()
    except FileNotFoundError:
        return False
    except OSError:
        return True  # present but unreadable: fail toward refusing
    if age > PLAY_FLAG_TTL_SECONDS:
        return False
    try:
        pid = json.loads(raw).get("pid")
    except (ValueError, AttributeError):
        pid = None
    if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
        return _pid_alive(pid)
    return True


def status() -> dict:
    """Current maintenance state. Read-only: it never writes the file.

    Expiry is computed on read. The old write-back (`active=False` on expiry) ran between its
    own `_read` and `_write` with no lock, so an operator `arm()` landing in that gap was
    overwritten with `active: False`. `arm()` and `disarm()` own every write; an expired record
    stays on disk until the next `arm()` replaces it.

    @returns the record when armed; `{"active": False}` plus `expired` or `unreadable` details otherwise.
    """
    d = _read()
    if d.get("_unreadable"):
        # Not "not armed". The record could not be read at all, and the difference is the whole
        # point of an override the operator turned on by hand.
        return {"active": False, "unreadable": True, "error": d["_unreadable"]}
    if not d.get("active"):
        return {"active": False}
    try:
        expires_at = float(d.get("expires_at", 0))
    except (TypeError, ValueError):
        # `float("soon")` raised ValueError out of the register guard's call path. Answer instead,
        # and leave the record on disk for the operator to read.
        return {"active": False, "unreadable": True,
                "error": f"expires_at is not a number: {d.get('expires_at')!r}"}
    if expires_at < time.time():
        return {"active": False, "expired": True}
    return d


def active() -> bool:
    return bool(status().get("active"))


def arm(phrase: str, source: str = "operator", ttl: int = DEFAULT_TTL_SECONDS, force: bool = False) -> dict:
    if phrase != PHRASE:
        raise PermissionError("maintenance phrase rejected")
    if ttl <= 0:
        # `--ttl -5` armed a window that had already closed and still reported active: True.
        raise ValueError(f"maintenance ttl must be a positive number of seconds, got {ttl!r}")
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
    if d.get("_unreadable"):
        # Writing here would replace a record the operator may still recover by hand with this
        # dict, so the corrupt file would be gone and the reason with it.
        return {"active": False, "unreadable": True, "error": d["_unreadable"], "disarmed": False}
    if not d:
        # Nothing was armed. Writing a disarm record here manufactures one that never happened.
        return {"active": False, "disarmed": False, "reason": "nothing was armed"}
    d["active"] = False
    d["disarmed_at"] = time.time()
    d["disarm_reason"] = reason
    _write(d)
    return d
