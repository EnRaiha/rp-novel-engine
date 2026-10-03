"""Module review: core/utils.py.

TWO DEFECTS FIXED, both about a rule that lives in two places.

`calc_game_days` carried the tick rate as a literal default, `multiplier: int = 4`.
Six modules call it with no multiplier (`narrative`, `diplomacy`, `economy`,
`research`, `market`, `pirates`), so the number the engine actually advanced game
time by was this literal, while `Config.TIME_MULTIPLIER = 4` — the knob whose own
comment reads "4 = 4 game days per tick" — was read only by `config.summary()`.
Setting the knob changed the banner and nothing else. The default is
`Config.TIME_MULTIPLIER` now, so the knob controls the arithmetic it advertises.
The value is 4 today, so no live tick changes until someone sets it, which is the
whole point of a knob.

`comma` raised TypeError on None (`int(None)`), and the three columns it is for
are all nullable — `maya_rp.resources.credits`, `alloys` and `fuel`. The snapshots
that format them (`core/state.py`, `core/session_rituals.py`) each died on a NULL
credit rather than naming the missing figure. A missing figure is `n/a` now, which
is the shape `core/briefing.py` already uses for the same columns. `comma` had no
caller anywhere before this, so the contract is set here rather than inherited.

REPORTED, not changed: `roll` has no caller in the engine or its tests, and its
parser reads anything it is handed. `"2d6"` and `"d20"` are the intended forms;
`"20"` is parsed as 20d20 rather than d20, and `"1d"` raises `int('')`. A caller
was never in a position to notice. Making the accepted form explicit and refusing
the rest is a contract change for a function nothing calls, so it is a decision
for the lead rather than a fix here.

CHECKED AND CORRECT: `clamp` clamps at both ends and returns the bound when they
cross; `calc_game_days` normalises a naive `last_tick` to UTC before subtracting
and an explicit multiplier still wins over the config; `roll` stays `random`, which
is what the name says, and nothing in the engine rolls a persisted outcome through
it (no caller at all).
"""
from __future__ import annotations

import pathlib
import sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core import utils  # noqa: E402
from core.config import Config  # noqa: E402


class TestTheTickRate:
    """The config knob is what the arithmetic reads."""

    def test_the_default_is_the_configured_multiplier(self, monkeypatch):
        monkeypatch.setattr(Config, "TIME_MULTIPLIER", 8)
        tick = datetime.now(timezone.utc) - timedelta(hours=12)

        assert utils.calc_game_days(tick) == pytest.approx(4.0), "12 real hours at 8 days per day"

    def test_the_stock_multiplier_gives_the_documented_rate(self):
        tick = datetime.now(timezone.utc) - timedelta(hours=24)

        assert utils.calc_game_days(tick) == pytest.approx(Config.TIME_MULTIPLIER)

    def test_an_explicit_multiplier_still_wins(self, monkeypatch):
        monkeypatch.setattr(Config, "TIME_MULTIPLIER", 99)
        tick = datetime.now(timezone.utc) - timedelta(hours=24)

        assert utils.calc_game_days(tick, 1) == pytest.approx(1.0)

    def test_a_naive_timestamp_is_read_as_utc(self):
        naive = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24, seconds=5)

        assert utils.calc_game_days(naive, 1) == pytest.approx(1.0, abs=0.01)

    def test_the_module_does_not_keep_a_second_copy_of_the_literal(self):
        source = (ROOT / "core/utils.py").read_text(encoding="utf-8")

        assert "multiplier: int = 4" not in source
        assert "Config.TIME_MULTIPLIER" in source


class TestTheNumber:
    """A missing figure is named, a real one keeps its separators."""

    def test_a_missing_figure_is_not_available(self):
        assert utils.comma(None) == "n/a"

    def test_a_real_figure_is_grouped(self):
        assert utils.comma(729591047927) == "729,591,047,927"
        assert utils.comma(0) == "0"
        assert utils.comma(-1500) == "-1,500"

    def test_a_float_is_truncated_as_before(self):
        assert utils.comma(1234.9) == "1,234"

    def test_the_modules_that_format_the_ledger_use_it(self):
        for module in ("core/state.py", "core/session_rituals.py"):
            source = (ROOT / module).read_text(encoding="utf-8")
            assert "comma(" in source, f"{module} formats a nullable column without the shared helper"


class TestTheOtherHelpers:
    def test_clamp_holds_both_ends(self):
        assert utils.clamp(5, 0, 10) == 5
        assert utils.clamp(-1, 0, 10) == 0
        assert utils.clamp(11, 0, 10) == 10

    def test_roll_stays_inside_its_dice(self):
        for dice in ("1d1", "d1", "3d1"):
            assert utils.roll(dice) == utils.roll(dice)
