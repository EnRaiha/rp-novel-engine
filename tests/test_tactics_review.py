"""Module review tests for modules/tactics.py.

Defect covered by this pass:

1. `get_tactical_position` validated zone, terrain and formation case-insensitively
   and then computed the multipliers case-SENSITIVELY: "WEDGE" produced no warning
   and took the 0.9 fallback instead of the wedge's 1.0. The multipliers read the
   lower-cased values now.
2. `run_tick` logged its crash at info level.

Checked and found correct, and the docstrings record the earlier pass: an unknown
weapon raises instead of fighting at kinetic odds; `targeting_system` is validated
against the module's own list; `calculate_fleet_power` reads the fleet through
`fleets` and `fleet_members` and refuses an unknown name; a zero `hull_current` is
a wreck, not a full-strength hull; and `formation_bonus` documents its 1.0
fallback. `ship_tech_bonuses` has no session_id, so research's insert into it is
correctly unscoped.

No database for most of it: the pure helpers are tested directly, the fleet read
through a fake.
"""
from __future__ import annotations

import os

import pytest

import modules.tactics as tactics

# Scratch session: sessions 3 and 5 are frozen reference data and the writers refuse them.
SID = 900 + os.getpid() % 100


class FakeDB:
    def __init__(self, fetch=None, fetchrow=None):
        self.fetch_rows = fetch if fetch is not None else []
        self.fetchrow_value = fetchrow
        self.calls = []

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        return self.fetch_rows

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", " ".join(sql.split()), args))
        return self.fetchrow_value

    def sql(self, kind=None):
        return [c[1] for c in self.calls if kind is None or c[0] == kind]


def _install(monkeypatch, fake):
    for name in ("fetch", "fetchrow"):
        monkeypatch.setattr("modules.tactics.Database." + name, getattr(fake, name))
    return fake


SHIPS = [{"tier": 3, "hull": 100, "hull_current": 50, "speed": 10},
         {"tier": None, "hull": 40, "hull_current": None, "speed": 5}]


# ── 1. The multipliers read the validated case ──────────────────────────

@pytest.mark.parametrize("formation,expected", [("spearhead", 1.2), ("SPEARHEAD", 1.2),
                                               ("wedge", 1.0), ("Wedge", 1.0)])
async def test_a_formation_multiplier_ignores_case(formation, expected):
    out = await tactics.get_tactical_position(5, formation=formation)

    assert "warnings" not in out, out
    assert out["effective_power"] == pytest.approx(round(0.8 * 0.8 * expected, 2)), out


@pytest.mark.parametrize("terrain,expected", [("asteroid_field", 1.0), ("ASTEROID_FIELD", 1.0),
                                              ("nebula", 0.9), ("NEBULA", 0.9)])
async def test_a_terrain_multiplier_ignores_case(terrain, expected):
    out = await tactics.get_tactical_position(5, terrain=terrain)

    assert "warnings" not in out, out
    # zone defaults to forward (0.8), formation to spearhead (1.2)
    assert out["effective_power"] == pytest.approx(round(0.8 * expected * 1.2, 2)), out


@pytest.mark.parametrize("zone,expected", [("aft", 1.0), ("AFT", 1.0), ("ventral", 1.0),
                                           ("forward", 0.8)])
async def test_a_zone_multiplier_ignores_case(zone, expected):
    out = await tactics.get_tactical_position(5, zone=zone)

    # terrain defaults to open_space (0.8), formation to spearhead (1.2)
    assert out["effective_power"] == pytest.approx(round(expected * 0.8 * 1.2, 2)), out


async def test_an_unknown_value_is_named_and_still_answered(monkeypatch):
    out = await tactics.get_tactical_position(5, zone="flank", terrain="mud", formation="turtle")

    assert len(out["warnings"]) == 3
    assert any("flank" in w for w in out["warnings"])
    assert out["effective_power"] == pytest.approx(round(0.8 * 0.8 * 0.9, 2))


async def test_the_defaults_are_the_documented_ones():
    out = await tactics.get_tactical_position(5)

    assert out["zone"] == "forward" and out["terrain"] == "open_space"
    assert out["formation"] == "spearhead"
    assert out["effective_power"] == pytest.approx(round(0.8 * 0.8 * 1.2, 2))


# ── Contract the module claims ──────────────────────────────────────────

def test_contract_every_pure_table_is_unique():
    for table in (tactics.SYSTEM_TARGETS, tactics.ZONES, tactics.TERRAINS,
                  tactics.FORMATIONS, tactics.MILITARY_OPS):
        values = list(table)
        assert len(set(values)) == len(values)


def test_contract_the_damage_table_names_its_multipliers():
    for name, spec in tactics.DAMAGE_TYPES.items():
        assert set(spec) == {"strong_vs", "weak_vs", "mult"}, name
        assert spec["mult"] > 0


async def test_contract_calculate_fleet_power_reads_the_campaign(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=SHIPS))

    out = await tactics.calculate_fleet_power(5)

    assert out["ship_count"] == 2
    # (3*10 + 50//10) + (1*10 + 40//10): NULL tier reads as 1, NULL hull_current
    # falls back to the hull value
    assert out["fleet_power"] == 35 + 14
    assert "session_id=$1" in fake.sql("fetch")[0]


async def test_contract_an_unknown_fleet_raises_rather_than_answering(monkeypatch):
    _install(monkeypatch, FakeDB(fetchrow=None))

    with pytest.raises(ValueError, match="Unknown fleet"):
        await tactics.calculate_fleet_power(5, "No Such Fleet")


async def test_contract_formation_bonus_documents_its_fallback():
    assert tactics.formation_bonus("wedge") == 1.15
    assert tactics.formation_bonus("WEDGE") == 1.15
    assert tactics.formation_bonus("turtle") == 1.0


def test_contract_roll_terrain_returns_a_named_table_row():
    seen = {tactics.roll_terrain()["name"] for _ in range(40)}

    assert seen <= {t["name"] for t in tactics._TERRAINS}


async def test_contract_run_tick_reports_the_campaign_power(monkeypatch):
    _install(monkeypatch, FakeDB(fetch=SHIPS))

    out = await tactics.run_tick(SID)

    assert out["ship_count"] == 2 and out["fleet_power"] == 49


async def test_contract_run_tick_reports_a_crash_as_an_error(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.tactics.error", lambda mod, msg: seen.append(msg))
    monkeypatch.setattr("modules.tactics.info", lambda mod, msg: None)

    async def boom(*_a, **_k):
        raise RuntimeError("no hulls")

    _install(monkeypatch, FakeDB())
    monkeypatch.setattr("modules.tactics.Database.fetch", boom)

    out = await tactics.run_tick(SID)

    assert "no hulls" in out["error"]
    assert any("no hulls" in m for m in seen), seen
