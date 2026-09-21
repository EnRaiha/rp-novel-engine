#!/usr/bin/env python3
"""Replay candidate texts against the current ruleset (M12, pure — no writes).

Before a rule change ships to canon, run the lines that matter through the
matcher and read the findings. Nothing is written to the ledger: this is the
same `audit_text` the engine uses, without the state updates.

Usage:
    python3 scripts/ruleset_regression.py --session 3 --text "That is okay." 
    python3 scripts/ruleset_regression.py --session 3 --file cases.txt [--stage selective]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402
from core import ooc  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(description="Replay texts against the ruleset (read-only)")
    parser.add_argument("--session", type=int, default=Config.SESSION_ID)
    parser.add_argument("--traits", default="aloof,general")
    parser.add_argument("--stage", default=None)
    parser.add_argument("--layer", default="dialogue")
    parser.add_argument("--text", action="append", default=[])
    parser.add_argument("--file", default=None)
    args = parser.parse_args()

    texts = list(args.text)
    if args.file:
        texts.extend(line.strip() for line in Path(args.file).read_text(encoding="utf-8").splitlines() if line.strip())
    if not texts:
        print("no texts given (--text or --file)", file=sys.stderr)
        return 2

    await Database.init()
    traits = tuple(part.strip() for part in args.traits.split(",") if part.strip())
    rules = [rule for rule in await ooc.effective_rules(args.session, traits, args.stage) if rule.kind != "scripted_beat"]
    await Database.close()

    print(f"ruleset: {len(rules)} penalty rules · stage {args.stage or '(current)'} · layer {args.layer}")
    total = 0
    for text in texts:
        findings = ooc.audit_text(text, rules, args.layer)
        total += len(findings)
        if findings:
            detail = ", ".join(f"{f.rule_id} +{f.delta} \"{f.match[:40]}\"" for f in findings)
            print(f"FLAG  {text[:70]!r} → {detail}")
        else:
            print(f"clean {text[:70]!r}")
    print(f"findings: {total} across {len(texts)} line(s)")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
