"""Helpers — dice, formatting, time calculations."""
import random
from datetime import datetime, timezone
from typing import Union

from core.config import Config


def roll(dice: str = "1d20") -> int:
    parts = dice.lower().split("d")
    count = int(parts[0]) if parts[0] else 1
    sides = int(parts[1]) if len(parts) > 1 else 20
    return sum(random.randint(1, sides) for _ in range(count))


def calc_game_days(last_tick, multiplier: int | None = None) -> float:
    """Game days elapsed since `last_tick`, at the configured tick rate.

    `multiplier` defaults to `Config.TIME_MULTIPLIER`, which used to be the only
    reader of that knob: the rule lived here as a literal 4, so setting the
    config changed the summary line and nothing the tick actually advanced by.
    """
    if multiplier is None:
        multiplier = Config.TIME_MULTIPLIER
    now = datetime.now(timezone.utc)
    # Handle both aware and naive datetimes
    if last_tick.tzinfo is None:
        last_tick = last_tick.replace(tzinfo=timezone.utc)
    real_hours = (now - last_tick).total_seconds() / 3600
    return real_hours * multiplier / 24


def clamp(val: Union[int, float], lo: Union[int, float], hi: Union[int, float]) -> Union[int, float]:
    return max(lo, min(hi, val))


def comma(num: Union[int, float, None]) -> str:
    """Thousands-separated number, or `n/a` when the ledger holds no figure.

    `int(None)` raised TypeError, so every snapshot that formatted a nullable
    column (credits, alloys, fuel, population) died on a NULL instead of naming
    the missing figure.
    """
    if num is None:
        return "n/a"
    return f"{int(num):,}"
