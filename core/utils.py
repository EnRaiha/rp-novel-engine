"""Helpers — dice, formatting, time calculations."""
import random
from datetime import datetime, timezone
from typing import Union, List

def roll(dice: str = "1d20") -> int:
    parts = dice.lower().split("d")
    count = int(parts[0]) if parts[0] else 1
    sides = int(parts[1]) if len(parts) > 1 else 20
    return sum(random.randint(1, sides) for _ in range(count))

def calc_game_days(last_tick, multiplier: int = 4) -> float:
    now = datetime.now(timezone.utc)
    # Handle both aware and naive datetimes
    if last_tick.tzinfo is None:
        last_tick = last_tick.replace(tzinfo=timezone.utc)
    real_hours = (now - last_tick).total_seconds() / 3600
    return real_hours * multiplier / 24

def clamp(val: Union[int, float], lo: Union[int, float], hi: Union[int, float]) -> Union[int, float]:
    return max(lo, min(hi, val))

def comma(num: Union[int, float]) -> str:
    return f"{int(num):,}"
