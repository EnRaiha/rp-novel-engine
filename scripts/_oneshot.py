"""Front end for one-shot scripts: a required --session, a dry run by default, a frozen guard."""
from __future__ import annotations

import argparse


def parse(description, argv=None, write_flag="--apply", extra=None):
    """Parse argv. `--session` has no default. `args.apply` is true only when `write_flag` is given."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--session", type=int, required=True, help="campaign id, no default")
    parser.add_argument(write_flag, dest="apply", action="store_true",
                        help="write. Without it the script only reports")
    if extra:
        extra(parser)
    return parser.parse_args(argv)


def guard(args):
    """Refuse a frozen session before the first write. A dry run passes."""
    if args.apply:
        from core.ooc import _refuse_frozen
        _refuse_frozen(args.session)
