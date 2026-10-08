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
import sys
import tempfile

STATE_DIR = pathlib.Path(os.environ.get("RP_MAINT_DIR", pathlib.Path.home() / ".config" / "rp-engine"))
ACTIVE_ARC = STATE_DIR / "active_arc"
FROZEN = STATE_DIR / "frozen_sessions"


def _warn(message: str) -> None:
    """Say something worth seeing, without closing an import cycle.

    `core.log` imports `core.config`, and `core.config` imports this module to
    resolve the process default. A module-level `from core.log import warn` here
    therefore closes the loop: `resolve_session` raises ImportError while
    `core.config` is still half-built, `_default_session` catches it, and every
    process silently starts on the frozen legacy session instead of the live arc.
    It arrives as the fallback warning with no obvious cause. Importing the logger
    at call time keeps the warning and the import order.
    """
    try:
        from core.log import warn
        warn("session", message)
    except Exception:
        # Deliberately wide, and the reason matters. Importing `core.log` runs its
        # module body, which makes the log directory and builds a file handler, so
        # the failure can be ImportError (the cycle above), OSError (an unwritable
        # log directory) or anything the logger raises. Every one of them must still
        # leave the warning on stderr: a warning about the session matters more than
        # the channel it goes out on. Nothing is swallowed, and the text is repeated
        # verbatim.
        print(f"warning: {message}", file=sys.stderr)


def unset(value) -> bool:
    """True for absent, blank, or zero: the sentinel every caller uses for 'no value'.

    The zero test is numeric, not textual. It compared the text to "0", so `"00"`,
    `"0.0"` and `False` were read as a real session id, and `--session=00` asked for
    a campaign that cannot exist rather than following the arc.
    """
    if value is None:
        return True
    if isinstance(value, bool):
        return not value
    text = str(value).strip()
    if text == "":
        return True
    try:
        return float(text) == 0
    except ValueError:
        return False


def _as_id(value, source: str) -> int:
    """A session id from a caller, or an error that names where the bad value came from."""
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"session id from {source} is not a number: {value!r}") from exc


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


def _atomic_write(target: pathlib.Path, text: str) -> None:
    """Write `text` to `target` through a uniquely named temp file in the same directory.

    A fixed `<name>.tmp` was shared by every writer: two concurrent switches truncated each
    other's temp file, and the loser's `replace` raised FileNotFoundError or published the
    other writer's half-written text. `mkstemp` gives each writer its own file; `os.replace`
    stays atomic because the temp file sits on the same filesystem.

    @param target - final path; its parent must exist.
    @param text - full new content.
    @returns None
    """
    fd, name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, target)
    except BaseException:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise


def set_active_arc(session_id: int) -> int:
    """Point the engine at one campaign. This is the only arc switch."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _atomic_write(ACTIVE_ARC, f"{int(session_id)}\n")
    return int(session_id)


class FrozenListUnreadable(PermissionError):
    """`frozen_sessions` exists and cannot be read, so no campaign can be called writable."""


def frozen() -> set[int]:
    """The reference-only campaigns. An entry that is not a number is named, not skipped.

    A typo used to disappear: the campaign it named stayed writable while the file
    read as if that campaign were protected.

    Only a missing file means nobody is frozen. Any other read failure (permissions, bad
    encoding, a directory in the file's place) used to return `set()`, so the guard failed
    open: every session read as writable and a write reached frozen session 3. It now warns
    and raises FrozenListUnreadable; `is_frozen` turns that into a refusal for writers.

    @returns the frozen session ids; empty when the file is absent.
    @raises FrozenListUnreadable when the file exists and cannot be read.
    """
    try:
        raw = FROZEN.read_text()
    except FileNotFoundError:
        return set()
    except Exception as exc:  # noqa: BLE001 - re-raised as the typed refusal
        _warn(f"frozen_sessions unreadable, refusing writes: {type(exc).__name__}: {exc}")
        raise FrozenListUnreadable(
            f"frozen list {FROZEN} is unreadable ({type(exc).__name__}: {exc}); "
            "writes are refused until it is repaired or GM MAYA maintenance is armed"
        ) from exc
    ids: set[int] = set()
    for part in raw.replace(",", " ").split():
        try:
            ids.add(int(part))
        except ValueError:
            _warn(f"frozen_sessions entry is not a session id: {part!r}")
            continue
    return ids


def is_frozen(session_id) -> bool:
    """Whether a write into `session_id` must be refused as reference-only.

    @param session_id - session id; a non-number is never frozen.
    @returns True when frozen.
    @raises FrozenListUnreadable when the list cannot be read and maintenance is not armed.
        Maintenance armed answers False: the operator is the one repairing the list.
    """
    try:
        sid = int(session_id)
    except (TypeError, ValueError):
        return False
    try:
        return sid in frozen()
    except FrozenListUnreadable:
        if _maintenance_active():
            return False
        raise


def set_frozen(session_ids) -> set[int]:
    """Replace the frozen list; a frozen campaign is reference, never a target."""
    ids = {int(item) for item in session_ids}
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _atomic_write(FROZEN, "".join(f"{item}\n" for item in sorted(ids)))
    return ids


def resolve_session(explicit=None) -> int | None:
    if not unset(explicit):
        return _as_id(explicit, "the caller")
    env = os.environ.get("RP_SESSION")
    if not unset(env):
        return _as_id(env, "RP_SESSION")
    arc = active_arc()
    if arc is not None:
        return _as_id(arc, str(ACTIVE_ARC))
    if _maintenance_active():
        return None
    raise RuntimeError(
        "no session resolved: pass --session=<id>, set RP_SESSION, or write "
        + str(ACTIVE_ARC)
        + ". Refusing to guess."
    )


def require_session(explicit=None) -> int:
    """Resolve the session for one call, refusing maintenance's "no session".

    `Config.SESSION_ID` is fixed at import, so a long-lived process (the kilo bridge serves the DSH
    plugin for hours, the map server, the tick) kept answering for the session that was current at
    start. Callers that fell back with `resolve_session(None) or Config.SESSION_ID` reintroduced the
    same stale id exactly when maintenance returns None. A reader that needs one session must fail
    loudly there instead.

    @param explicit - session id from the caller; wins over RP_SESSION and the active arc.
    @returns the resolved session id.
    @raises RuntimeError when nothing resolves, or when maintenance is armed and resolves no session.
    """
    sid = resolve_session(explicit)
    if sid is None:
        raise RuntimeError("maintenance mode resolves no session; pass session_id explicitly")
    return sid


def mode_label() -> str:
    try:
        from core import maintenance
        return "GM MAYA maintenance" if maintenance.active() else "play"
    except Exception as exc:
        # Reporting "play" is the safe answer, but an unreadable maintenance flag is
        # the difference between an operator writing canon and not, so it is said.
        _warn(f"maintenance state unreadable, reporting play: {exc}")
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
    try:
        frozen_note = " (and it is frozen)" if process_default in frozen() else ""
    except FrozenListUnreadable:
        frozen_note = " (frozen list unreadable)"
    return (f"warning: this process defaults to session {process_default}{frozen_note}, "
            f"but the engine now resolves to session {resolved}. Pass the session explicitly.")
