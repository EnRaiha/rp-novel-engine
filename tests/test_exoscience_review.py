"""Exoscience module review tests — one per defect found reading modules/exoscience.py.

Defects covered:

1. The mission loop read `progress` and `target_progress` straight off the row. Both columns are
   nullable, so a row written without either made `None + gain` raise inside the tick's single
   `try`: one malformed mission stopped every other mission in the session.
2. The anomaly loop read `data_collected` and `data_threshold` the same way, with the same result.
3. `start_mission` accepted a blank mission type, so a mission that cannot be described could be
   created and then progressed by the tick.
4. `generate_anomaly` accepted a blank location. The empty name built the LIKE pattern `%%`, which
   matches a session's first sector, so an unlocated anomaly was tied to an arbitrary site.
5. The tick's failure path logged at info level, the same level as a successful tick, so a broken
   tick was invisible in the log.

Every test drives a fake Database: nothing here writes to a campaign.
"""
from __future__ import annotations

import pytest

import modules.exoscience as exoscience  # noqa: E402


class FakeDB:
    """Answers by statement, and records what it was asked, so a defect can be driven cheaply."""

    def __init__(self, missions=None, anomalies=None, resources_credits=0, fail_fetch=False):
        self.missions = missions if missions is not None else []
        self.anomalies = anomalies if anomalies is not None else []
        self.resources_credits = resources_credits
        self.fail_fetch = fail_fetch
        self.calls = []

    async def fetch(self, sql, *args):
        if self.fail_fetch:
            raise RuntimeError("probe failure")
        self.calls.append(("fetch", " ".join(sql.split()), args))
        if "FROM maya_rp.science_missions" in sql:
            return self.missions
        if "FROM maya_rp.anomalies_catalog" in sql:
            return self.anomalies
        return []

    async def fetchrow(self, sql, *args):
        return None

    async def fetchval(self, sql, *args):
        flat = " ".join(sql.split())
        self.calls.append(("fetchval", flat, args))
        if "INSERT INTO maya_rp.science_missions" in flat:
            return 71
        if "INSERT INTO maya_rp.anomalies_catalog" in flat:
            return 72
        if "UPDATE maya_rp.resources" in flat:
            return self.resources_credits
        return None

    async def execute(self, sql, *args):
        self.calls.append(("execute", " ".join(sql.split()), args))
        return "UPDATE 1"

    def inserts(self):
        return [c for c in self.calls if c[0] == "fetchval" and "INSERT INTO" in c[1]]


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(exoscience, "Database", db)
    return db


class TestNullableRowsDoNotStopTheTick:
    async def test_a_mission_with_no_progress_is_read_as_zero(self, monkeypatch):
        """`progress IS NULL` used to raise inside the tick and take the whole session with it."""
        db = FakeDB(missions=[{"id": 41, "mission_type": "survey", "progress": None,
                               "target_progress": 50, "research_reward": 25}])
        monkeypatch.setattr(exoscience, "Database", db)

        result = await exoscience.run_tick(5)

        assert "error" not in result, result
        assert result["missions_completed"] == 0, result

    async def test_a_mission_with_no_target_is_read_as_hundred(self, monkeypatch):
        db = FakeDB(missions=[{"id": 42, "mission_type": "survey", "progress": 10,
                               "target_progress": None, "research_reward": 25}])
        monkeypatch.setattr(exoscience, "Database", db)

        result = await exoscience.run_tick(5)

        assert "error" not in result, result
        assert result["missions_completed"] == 0, result

    async def test_an_anomaly_with_no_columns_set_is_read_as_zero(self, monkeypatch):
        db = FakeDB(anomalies=[{"id": 43, "name": "Resonant Echo",
                                "data_collected": None, "data_threshold": None}])
        monkeypatch.setattr(exoscience, "Database", db)

        result = await exoscience.run_tick(5)

        assert "error" not in result, result
        assert result["anomalies_studied"] == 0, result


class TestTheBoardRefusesUnnamedWork:
    async def test_a_blank_mission_type_is_refused(self, fake_db):
        out = await exoscience.start_mission("   ", 5)

        assert "error" in out, out
        assert "mission_type" in out["error"], out
        assert fake_db.inserts() == [], f"a blank mission was written: {fake_db.calls}"

    async def test_a_blank_location_is_refused(self, fake_db):
        out = await exoscience.generate_anomaly("", 5)

        assert "error" in out, out
        assert "location" in out["error"], out
        assert fake_db.inserts() == [], f"an unplaced anomaly was written: {fake_db.calls}"

    async def test_a_real_location_still_reads_the_sector_and_places_the_anomaly(self, monkeypatch):
        db = FakeDB()
        monkeypatch.setattr(exoscience, "Database", db)

        out = await exoscience.generate_anomaly("  Bisik  ", 5)

        assert out.get("anomaly_id") == 72, out
        assert out.get("location") == "Bisik", "the stored location kept its padding"
        insert = db.inserts()[0][1]
        assert "anomalies_catalog" in insert


class TestTheRewardContract:
    async def test_a_paid_reward_is_not_reported_as_unpaid(self, monkeypatch):
        """The other half of the unpaid-reward contract: a session with a treasury stays quiet."""
        db = FakeDB(missions=[{"id": 44, "mission_type": "survey", "progress": 49,
                               "target_progress": 50, "research_reward": 25}],
                    resources_credits=500)
        monkeypatch.setattr(exoscience, "Database", db)

        result = await exoscience.run_tick(5)

        assert result["missions_completed"] == 1, result
        assert "rewards_unpaid" not in result, result

    async def test_a_missing_treasury_is_reported_rather_than_counted_as_paid(self, monkeypatch):
        db = FakeDB(missions=[{"id": 45, "mission_type": "survey", "progress": 49,
                               "target_progress": 50, "research_reward": 25}],
                    resources_credits=None)
        monkeypatch.setattr(exoscience, "Database", db)

        result = await exoscience.run_tick(5)

        assert result["missions_completed"] == 1, result
        assert result["rewards_unpaid"] == 1, result


class TestAFailedTickIsVisible:
    async def test_a_failed_tick_logs_at_error_level(self, monkeypatch):
        db = FakeDB(fail_fetch=True)
        monkeypatch.setattr(exoscience, "Database", db)
        seen = []
        monkeypatch.setattr(exoscience, "error", lambda module, msg: seen.append((module, msg)))

        result = await exoscience.run_tick(5)

        assert "error" in result, result
        assert seen, "the failure was not logged at error level"
        assert seen[0][0] == "exoscience", seen
        assert "probe failure" in seen[0][1], seen


class TestThePaceContract:
    async def test_the_same_mission_advances_by_the_same_amount_twice(self, monkeypatch):
        """The tick is reproducible: two runs over one unchanged state move the mission identically."""
        row = {"id": 46, "mission_type": "survey", "progress": 0,
               "target_progress": 999, "research_reward": 25}
        first = FakeDB(missions=[dict(row)])
        monkeypatch.setattr(exoscience, "Database", first)
        await exoscience.run_tick(5)
        second = FakeDB(missions=[dict(row)])
        monkeypatch.setattr(exoscience, "Database", second)
        await exoscience.run_tick(5)

        writes = lambda db: [(c[1], c[2]) for c in db.calls if c[0] == "execute"]
        assert writes(first) == writes(second), (writes(first), writes(second))
        assert writes(first), "the mission was never advanced"
