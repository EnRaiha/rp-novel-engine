"""Operator CLI for GM MAYA maintenance mode and the session source of truth.

  python3 scripts/gm_maint.py arm [--ttl SECONDS] [--force]
  python3 scripts/gm_maint.py disarm
  python3 scripts/gm_maint.py status
  python3 scripts/gm_maint.py mode
  python3 scripts/gm_maint.py session [--session N]
  python3 scripts/gm_maint.py arc [N]            # show or set the active arc
  python3 scripts/gm_maint.py freeze [N ...]     # show or replace the frozen list
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import maintenance as m
from core import session as s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("verb", choices=["arm", "disarm", "status", "session", "mode", "arc", "freeze"])
    ap.add_argument("values", nargs="*", type=int)
    ap.add_argument("--session", type=int, default=None)
    ap.add_argument("--ttl", type=int, default=m.DEFAULT_TTL_SECONDS)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    if a.verb == "arm":
        print(m.arm(m.PHRASE, source="operator", ttl=a.ttl, force=a.force))
    elif a.verb == "disarm":
        print(m.disarm("operator"))
    elif a.verb == "status":
        print("mode:", s.mode_label())
        print("arc:", s.active_arc())
        print("frozen:", sorted(s.frozen()) or "—")
        print(m.status())
    elif a.verb == "mode":
        print(s.mode_label())
    elif a.verb == "arc":
        if a.values:
            s.set_active_arc(a.values[0])
        print("arc:", s.active_arc())
    elif a.verb == "freeze":
        if a.values:
            s.set_frozen(a.values)
        print("frozen:", sorted(s.frozen()) or "—")
    else:
        try:
            print("session:", s.resolve_session(a.session))
        except RuntimeError as exc:
            print("refused:", exc)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
