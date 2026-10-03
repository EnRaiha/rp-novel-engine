"""Module review tests for modules/unity.py (2026-10-03).

unity.py is pure arithmetic, so most of these tests are pure too. The one that
reads the database reads only; it writes nothing anywhere.
"""
from __future__ import annotations

import asyncio
import math
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.unity as unity  # noqa: E402
from modules import calendar_tkg  # noqa: E402
from core.db import Database  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def _doc_unity(hull_count, systems_held, stance_score, origin, doctrine, pressure, lag):
    """The unity formula, transcribed from the module docstring, not from the code."""
    clamped = max(-1.0, min(1.0, stance_score))
    p = max(0.0, min(1.0, (1.0 - clamped) / 2.0)) if pressure is None else max(0.0, min(1.0, pressure))
    grip = 0.0 if systems_held < 1 else min(1.0, (hull_count / (1.0 + systems_held)) / 500.0)
    reach = math.log10(1.0 + systems_held) / 2.0
    span = 0.60 * reach + 0.40 * min(1.0, lag)
    base = {"natural": 0.20, "imposed": 0.50, "sponsored": 0.45}[origin]
    gain = {"natural": 0.55, "imposed": 0.05, "sponsored": -0.10}[origin]
    doc = {"science_tech": 0.05, "magic": -0.05, "balance": 0.02, "unaligned": -0.10}[doctrine]
    value = base + gain * p + doc + 0.10 * abs(clamped) + 0.15 * grip - span
    return round(max(0.0, min(1.0, value)), 4)


# ── The documented formula, checked against an independent transcription ─


def test_the_documented_unity_formula_is_what_the_code_computes():
    for hulls in (0, 250, 2080, 10000):
        for held in (0, 1, 3, 79):
            for stance in (-1.0, -0.0753, 0.0, 0.2633, 1.0):
                for origin, doctrine in (("natural", "science_tech"),
                                         ("imposed", "unaligned"),
                                         ("sponsored", "magic")):
                    for pressure, lag in ((None, 0.0), (0.9, 0.5), (0.1, 1.0)):
                        shown = unity.unity(hulls, held, stance, origin, doctrine, pressure, lag)
                        want = _doc_unity(hulls, held, stance, origin, doctrine, pressure, lag)
                        assert shown == want, (hulls, held, stance, origin, doctrine,
                                               pressure, lag, shown, want)


def test_the_documented_latency_formulas_hold_at_their_edges():
    assert unity.path_latency_days([]) == 0.0
    assert unity.mean_latency_days([1.0]) == 1.0
    assert unity.latency_days_ceil(0.0) == 0
    assert unity.arrival_game_day(0, 0.0) == 0
    assert unity.lag_fraction(0.0) == 0.0
    assert unity.pressure_default(1.0) == 0.0
    assert unity.grip(500.0, 0) == 0.0
    assert unity.reach(0) == 0.0
    assert unity.drift(0.0, 1.0) == 0.0


def test_the_month_constant_has_one_source():
    """LATENCY_REFERENCE_DAYS restates calendar_tkg.DAYS_PER_MONTH.

    The module keeps a local copy for its own pure-import build, the same way
    LANE_TYPES keeps a local copy of economy_physics' lane list. Both copies are
    pinned by a test so neither can drift in silence.
    """
    assert unity.LATENCY_REFERENCE_DAYS == float(calendar_tkg.DAYS_PER_MONTH)
    assert unity.lag_fraction(calendar_tkg.DAYS_PER_MONTH) == 1.0


def test_the_module_never_mutates_what_the_caller_supplied():
    lanes = [{"lane_type": "standard", "distance": 2.0}]
    row = dict(hull_count=10, systems_held=2, stance_score=0.1)
    unity.path_latency_days(lanes)
    unity.unity(**row)
    assert lanes == [{"lane_type": "standard", "distance": 2.0}]
    assert row == dict(hull_count=10, systems_held=2, stance_score=0.1)


def test_the_public_api_surface_is_intact():
    for name in ("lane_latency_days", "latency_from_hours", "path_latency_days",
                 "mean_latency_days", "latency_days_ceil", "arrival_game_day",
                 "lag_fraction", "pressure_default", "grip", "reach", "span",
                 "unity", "unity_band", "drift"):
        assert callable(getattr(unity, name)), name
    for name in ("SIGNAL_COURIER", "SIGNAL_ANSIBLE", "LATENCY_REFERENCE_DAYS",
                 "LANE_TYPES", "UNITY_EDGES", "DRIFT_PER_FULL_LAG", "ORIGIN_BASE",
                 "ORIGIN_PRESSURE_GAIN", "DOCTRINE_UNITY"):
        assert hasattr(unity, name), name


# ── The live rows the module documents ─────────────────────────────────


def _faction_rows():
    async def load():
        await Database.init()
        try:
            return await Database.fetch("""
                SELECT f.id, f.origin, f.doctrine, f.systems_held, f.stance_score,
                       (SELECT count(*) FROM maya_rp.ships s WHERE s.faction_id = f.id) AS hulls
                FROM maya_rp.factions f ORDER BY f.id""")
        finally:
            await Database.close()

    return _run(load())


def test_every_live_faction_row_bands_its_own_unity():
    rows = _faction_rows()
    assert rows, "no faction rows to read"
    for r in rows:
        value = unity.unity(r["hulls"], r["systems_held"] or 0, r["stance_score"],
                            r["origin"] or unity.DEFAULT_ORIGIN,
                            r["doctrine"] or unity.DEFAULT_DOCTRINE)
        assert 0.0 <= value <= 1.0
        assert unity.unity_band(value) in ("unanimous", "united", "strained",
                                           "divided", "fractured")


def test_the_documented_measured_snapshot_reproduces():
    """The module header states band counts, mean, min and max for 2026-10-02."""
    rows = _faction_rows()
    if len(rows) != 76:
        pytest.skip(f"the faction table holds {len(rows)} rows, not the documented 76")
    values = [unity.unity(r["hulls"], r["systems_held"] or 0, r["stance_score"],
                          r["origin"] or unity.DEFAULT_ORIGIN,
                          r["doctrine"] or unity.DEFAULT_DOCTRINE) for r in rows]
    bands: dict[str, int] = {}
    for value in values:
        band = unity.unity_band(value)
        bands[band] = bands.get(band, 0) + 1
    assert bands == {"fractured": 25, "divided": 4, "strained": 8,
                     "united": 38, "unanimous": 1}
    assert round(sum(values) / len(values), 4) == 0.4023
    assert min(values) == 0.0221
    assert max(values) == 0.8412
