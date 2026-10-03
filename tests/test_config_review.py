"""Module review: core/config.py.

TWO REGISTRIES, AND THE FILE IS THE SECOND ONE.

The tick names its modules in `scripts/orchestrator.py::MODULE_MAP` and this file decides whether a
name runs, through `is_module_active` → `MODULES.get(name, False)`. Measured against the tick list:

    81 tick keys, 82 rows
    in the tick, no row here:  duel, wreck_assembly
    a row here the tick never reads:  agnes, dramatic_structure, meanwhile

`duel` and `wreck_assembly` are wired into the tick and have no row, so every run logs
"SKIPPED (disabled)" and they never execute. `agnes` is the one row deliberately set False, so an
absent row is not how this file says no. The pair is recorded rather than switched on: enabling them
starts writing to the live campaigns on every tick, which is a decision and not a review fix. The
test asserts the set, so the day someone adds the rows it fails and the note is updated with them.

`dramatic_structure` and `meanwhile` are called directly from `core/pacing.py` and
`core/master_briefing.py`, so the modules are alive and only their rows are dead.

The database address was the primary address in the engine's config, while the addressing convention
makes a Tailscale name the address and an `IP:port` the fallback. Measured before the change: the
name resolves through MagicDNS, port 5432 answers on it, and the engine connects and queries through
it (`current_schema() = maya_rp`). The summary line no longer carries a second copy of the host.

Reported, not changed: `TIME_MULTIPLIER` is read only by `summary()`, so the "4 game days per tick"
knob controls nothing; `SESSION_FALLBACK_USED` is read only by a test, while the real announcement is
the stderr line; and `_default_session` resolves once at import, so a long-lived process keeps the
session it started with, which is the documented behaviour and the Lead's open item.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import Config  # noqa: E402


def _dsn_host() -> str:
    return Config.DSN.split("@", 1)[-1].split("/", 1)[0].split(":", 1)[0]


def _tick_keys() -> set[str]:
    """The module names `scripts/orchestrator.py` ticks, read from its MODULE_MAP."""
    source = (ROOT / "scripts" / "orchestrator.py").read_text(encoding="utf-8")
    block = source[source.index("MODULE_MAP = {"):]
    block = block[:block.index("\n}")]
    return set(re.findall(r'"([a-z_0-9]+)":', block))


class TestTheTwoRegistriesAgree:
    """`.get(name, False)` reads an absent row as disabled, so the two lists must agree."""

    def test_a_module_in_the_tick_list_has_a_row_here(self):
        missing = _tick_keys() - set(Config.MODULES)
        assert missing == {"duel", "wreck_assembly"}, (
            "the tick list and this registry changed together: update the note at the top of this "
            "file, because a name in the tick with no row is skipped on every run")

    def test_the_deliberately_disabled_module_says_so_with_a_row(self):
        """`agnes` is off through `False`, which is how this file says no. Absence is not."""
        assert Config.MODULES["agnes"] is False
        assert [name for name, active in Config.MODULES.items() if not active] == ["agnes"]

    def test_a_row_the_tick_never_reads_is_recorded(self):
        unused = set(Config.MODULES) - _tick_keys()
        assert unused == {"agnes", "dramatic_structure", "meanwhile"}, (
            "these modules are called directly, so only their rows are dead; a new one means a row "
            "nobody reads")


class TestIsModuleActive:
    def test_an_unknown_name_is_inactive(self):
        """The safe default for enabling work, and the reason a missing row is silent."""
        assert Config.is_module_active("review_no_such_module") is False

    def test_an_enabled_row_is_active(self):
        assert Config.is_module_active("economy") is True


class TestTheDatabaseAddress:
    """The addressing convention: a Tailscale name is the address, `IP:port` is the fallback."""

    def test_the_dsn_names_the_host_by_its_tailscale_name(self):
        assert _dsn_host().endswith(".tail73711d.ts.net"), _dsn_host()

    def test_the_legacy_ip_is_not_what_the_engine_connects_to(self):
        assert "100.65.243.60" not in Config.DSN

    def test_the_summary_reports_the_host_the_dsn_connects_to(self):
        assert _dsn_host() in Config.summary()

    def test_the_dsn_still_carries_its_user_schema_and_database(self):
        assert "rp_engine" in Config.DSN and "maya_memory" in Config.DSN
        assert "search_path=maya_rp" in Config.DSN
