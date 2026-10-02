"""A handler that swallows an error without a word is a scene that continues on nothing.

Seventeen handlers caught `Exception` and passed. The failure they hide is not the exception itself
but the silence: a scene keeps running with missing data and no record, and the same defect that
produced today's `affection` column (written by nobody, read by nobody) also produced this.

The rule this test enforces: a handler that does nothing must either write a log line or say, in the
code, why doing nothing is correct. Silence stops being an option.
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
FOLDERS = ("core", "modules", "scripts")
DELIBERATE = "deliberate:"


def silent_handlers() -> list[tuple[str, int, str]]:
    """Every `except Exception:` whose body is only `pass` or `continue`, plus its next line."""
    found = []
    for folder in FOLDERS:
        for path in sorted((ROOT / folder).rglob("*.py")):
            rows = path.read_text(encoding="utf-8", errors="replace").split("\n")
            for index, row in enumerate(rows):
                if not re.match(r"\s*except Exception\b", row):
                    continue
                body = rows[index + 1] if index + 1 < len(rows) else ""
                if re.match(r"\s*(pass|continue)\s*$", body):
                    found.append((str(path.relative_to(ROOT)), index + 1, row))
    return found


class TestNoSilentHandlers:
    def test_every_silent_handler_is_declared_deliberate(self):
        undeclared = [(path, line) for path, line, row in silent_handlers() if DELIBERATE not in row]
        assert not undeclared, (
            "these handlers swallow an error with no log line and no reason: "
            + ", ".join(f"{path}:{line}" for path, line in undeclared)
        )

    def test_the_deliberate_marker_is_rare_enough_to_mean_something(self):
        """A marker on everything is a marker on nothing."""
        declared = [row for _, _, row in silent_handlers() if DELIBERATE in row]
        assert len(declared) <= 4, f"too many declared-silent handlers: {len(declared)}"

    def test_the_reported_handlers_actually_report(self):
        """The patched sites must name the step that failed, not just the fact that one did."""
        generic = []
        for folder in FOLDERS:
            for path in sorted((ROOT / folder).rglob("*.py")):
                text = path.read_text(encoding="utf-8", errors="replace")
                if "optional step failed" in text:
                    generic.append(str(path.relative_to(ROOT)))
        assert not generic, f"a log line must name the failing step: {generic}"
