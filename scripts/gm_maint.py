"""Operator CLI for GM MAYA maintenance mode and the session source of truth.

  python3 scripts/gm_maint.py arm [--ttl SECONDS] [--force]
  python3 scripts/gm_maint.py disarm
  python3 scripts/gm_maint.py status
  python3 scripts/gm_maint.py mode
  python3 scripts/gm_maint.py session [--session N]
  python3 scripts/gm_maint.py arc [N]            # show or set the active arc, and name its novel
  python3 scripts/gm_maint.py freeze [N ...]     # show or replace the frozen list
  python3 scripts/gm_maint.py play on [--pid N]  # raise the play flag; arm refuses while it is live
  python3 scripts/gm_maint.py play off           # lower it
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import maintenance as m
from core import session as s
from core.db import Database

#: Bound on the novel read: the operator asked for a report, not for a wait on a database that is down.
NOVEL_TIMEOUT_SECONDS = 5


async def _read_novel(arc: int) -> str:
    """Read one arc's novel, closing the pool this call opened."""
    created = Database.pool is None
    await Database.init()
    try:
        return await asyncio.wait_for(s.novel_of(arc), NOVEL_TIMEOUT_SECONDS)
    finally:
        if created:
            await Database.close()


def novel_label(arc) -> str:
    """The novel of the arc, for the operator report.

    The report must print: an arc with no row, an unreachable database and a slow one are all named
    rather than raised, because a status verb that dies tells the operator nothing.

    @param arc - the active arc, or None when none is set.
    @returns the `novel_id` slug, `none` for no arc, or an UNRESOLVED line naming what went wrong.
    """
    if arc is None:
        return "none"
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        # The CLI runs as a process, so an in-process caller is the only way here. A worker thread
        # answers too, and the report does not need one.
        return "UNRESOLVED (RuntimeError: an event loop is already running)"
    try:
        return asyncio.run(_read_novel(arc))
    except Exception as exc:
        return f"UNRESOLVED ({type(exc).__name__}: {exc})"


def _int_or_switch(v):
    """`play on|off` shares the positional with the integer verbs; argparse still rejects other words."""
    return v if v in ("on", "off") else int(v)


def _frozen_label():
    """The frozen list for display; an unreadable list is named, never a traceback."""
    try:
        return sorted(s.frozen()) or "—"
    except PermissionError as exc:
        return f"UNREADABLE ({exc}); every write is refused until it is repaired"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("verb", choices=["arm", "disarm", "status", "session", "mode", "arc", "freeze", "play"])
    ap.add_argument("values", nargs="*", type=_int_or_switch)
    ap.add_argument("--pid", type=int, default=None)
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--ttl", type=int, default=m.DEFAULT_TTL_SECONDS)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)

    if a.verb == "play":
        if a.values not in (["on"], ["off"]):
            ap.error("play takes exactly one of: on, off")
        if a.values == ["on"]:
            m.mark_play(True, pid=a.pid)
            print(f"play: on (pid {a.pid if a.pid is not None else 'none'}; stale after {m.PLAY_FLAG_TTL_SECONDS}s)")
        else:
            m.mark_play(False)
            print("play: off")
        return 0
    if a.verb == "arm":
        print(m.arm(m.PHRASE, source="operator", ttl=a.ttl, force=a.force))
    elif a.verb == "disarm":
        print(m.disarm("operator"))
    elif a.verb == "status":
        arc = s.active_arc()
        print("mode:", s.mode_label())
        print("arc:", arc)
        print("novel:", novel_label(arc))
        print("frozen:", _frozen_label())
        print(m.status())
    elif a.verb == "mode":
        print(s.mode_label())
    elif a.verb == "arc":
        if a.values:
            s.set_active_arc(a.values[0])
        arc = s.active_arc()
        print("arc:", arc)
        print("novel:", novel_label(arc))
    elif a.verb == "freeze":
        if a.values:
            s.set_frozen(a.values)
        print("frozen:", _frozen_label())
    else:
        try:
            print("session:", s.resolve_session(a.session))
        except RuntimeError as exc:
            print("refused:", exc)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
