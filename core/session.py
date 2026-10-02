"""Single session resolver for the RP and OOC engines.

No hardcoded live-arc default. Precedence:
  1. explicit argument
  2. RP_SESSION environment variable
  3. active arc file  (~/.config/rp-engine/active_arc)
  4. maintenance mode -> None: cross-session edits are permitted, nothing guessed
Otherwise it refuses. Guessing the session is what merged two arcs.

`frozen_sessions` lists reference-only campaigns, one id per line. A frozen
campaign stays readable; a write into it is refused unless maintenance is armed.
"""
from __future__ import annotations

import os
import pathlib

STATE_DIR = pathlib.Path(os.environ.get("RP_MAINT_DIR", pathlib.Path.home() / ".config" / "rp-engine"))
ACTIVE_ARC = STATE_DIR / "active_arc"
FROZEN = STATE_DIR / "frozen_sessions"


def unset(value) -> bool:
    """True for absent, blank, or 0: the sentinel every caller uses for 'no value'."""
    if value is None:
        return True
    text = str(value).strip()
    return text == "" or text == "0"


def _maintenance_active() -> bool:
    try:
        from core import maintenance
        return maintenance.active()
    except Exception:
        return False


def active_arc() -> int | None:
    try:
        return int(ACTIVE_ARC.read_text().strip())
    except Exception:
        return None


def set_active_arc(session_id: int) -> int:
    """Point the engine at one campaign. This is the only arc switch."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = ACTIVE_ARC.with_suffix(".tmp")
    tmp.write_text(f"{int(session_id)}\n")
    tmp.replace(ACTIVE_ARC)
    return int(session_id)


def frozen() -> set[int]:
    try:
        raw = FROZEN.read_text()
    except Exception:
        return set()
    ids: set[int] = set()
    for part in raw.replace(",", " ").split():
        try:
            ids.add(int(part))
        except ValueError:
            continue
    return ids


def is_frozen(session_id) -> bool:
    try:
        return int(session_id) in frozen()
    except (TypeError, ValueError):
        return False


def set_frozen(session_ids) -> set[int]:
    """Replace the frozen list; a frozen campaign is reference, never a target."""
    ids = {int(item) for item in session_ids}
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = FROZEN.with_suffix(".tmp")
    tmp.write_text("".join(f"{item}\n" for item in sorted(ids)))
    tmp.replace(FROZEN)
    return ids


def resolve_session(explicit=None) -> int | None:
    if not unset(explicit):
        return int(explicit)
    env = os.environ.get("RP_SESSION")
    if not unset(env):
        return int(env)
    arc = active_arc()
    if arc is not None:
        return arc
    if _maintenance_active():
        return None
    raise RuntimeError(
        "no session resolved: pass --session=<id>, set RP_SESSION, or write "
        + str(ACTIVE_ARC)
        + ". Refusing to guess."
    )


def mode_label() -> str:
    try:
        from core import maintenance
        return "GM MAYA maintenance" if maintenance.active() else "play"
    except Exception:
        return "play"


def stale_process_default(current: int | None = None) -> str | None:
    """Report when this process's default session is no longer the engine's.

    `Config.SESSION_ID` is resolved once, at import. A process that started while the arc was session
    3 keeps writing to session 3 after the arc moves to 5, and session 3 is frozen. That is the
    mechanism by which a write can reach a session nobody chose, so it is worth a sentence at startup
    rather than a mystery later.

    @param current - the process default to check; defaults to `Config.SESSION_ID`.
    @returns one line naming the drift, or None when the two agree.
    """
    try:
        from core.config import Config

        process_default = int(Config.SESSION_ID if current is None else current)
        resolved = resolve_session()
    except Exception:
        return None
    if resolved is None or process_default == int(resolved):
        return None
    frozen_note = " (and it is frozen)" if process_default in frozen() else ""
    return (f"warning: this process defaults to session {process_default}{frozen_note}, "
            f"but the engine now resolves to session {resolved}. Pass the session explicitly.")
