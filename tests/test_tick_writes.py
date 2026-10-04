#!/usr/bin/env python3
"""Tick writes — the count `modules_ok` cannot give.

`diff` is pure, so most of this needs no database. The database tests read a statistics view
and write nothing.
"""
from __future__ import annotations

from core.db import Database
from core.tick_writes import diff, never_written, report, snapshot


def test_tables_that_moved_are_reported_with_how_far():
    before = {"ships": {"ins": 10, "upd": 20, "del": 0}}
    after = {"ships": {"ins": 13, "upd": 22, "del": 1}}

    assert diff(before, after) == {"ships": {"ins": 3, "upd": 2, "del": 1}}


def test_a_table_that_did_not_move_is_absent():
    """Absence is the signal. A table listed with zeroes would read as checked-and-clean on every
    tick, which is 307 lines of nothing."""
    before = {"ships": {"ins": 10, "upd": 20, "del": 0}, "crew": {"ins": 1, "upd": 1, "del": 0}}
    after = {"ships": {"ins": 14, "upd": 20, "del": 0}, "crew": {"ins": 1, "upd": 1, "del": 0}}

    assert set(diff(before, after)) == {"ships"}


def test_nothing_moved_is_an_empty_report_not_a_failure():
    same = {"ships": {"ins": 6, "upd": 6, "del": 6}}

    assert diff(same, same) == {}


def test_a_table_only_in_the_second_snapshot_is_skipped():
    """A table created during the tick has no baseline, so its counts are not a delta."""
    assert diff({}, {"brand_new": {"ins": 1, "upd": 0, "del": 0}}) == {}


def test_a_missing_snapshot_is_skipped_rather_than_exploded():
    assert diff(None, {"ships": {"ins": 1, "upd": 0, "del": 0}}) == {}
    assert diff({"ships": {"ins": 1, "upd": 0, "del": 0}}, None) == {}


def test_a_counter_that_went_backwards_is_not_reported_as_a_write():
    """A stats reset between the two snapshots takes the counters to zero. A negative delta is a
    reset, not a write, and reporting it would invent activity."""
    before = {"ships": {"ins": 100, "upd": 50, "del": 0}}
    after = {"ships": {"ins": 0, "upd": 0, "del": 0}}

    assert diff(before, after) == {}


def test_a_real_write_survives_a_reset_in_another_counter():
    """The case that made the first version accidentally right. Summing the counters before
    flooring let five genuine inserts be cancelled by a reset `n_tup_upd` of a hundred, and the
    tick would have reported writing nothing while it wrote."""
    before = {"ships": {"ins": 0, "upd": 100, "del": 0}}
    after = {"ships": {"ins": 5, "upd": 0, "del": 0}}

    assert diff(before, after) == {"ships": {"ins": 5, "upd": 0, "del": 0}}


async def test_the_statistics_view_is_readable_by_the_engine_role():
    """It connects as `rp_engine`, not as the superuser. If this ever fails the report must say so
    rather than print zero writes, because the two look identical."""
    await Database.init()
    tables = await snapshot()

    assert tables, "pg_stat_user_tables returned nothing for this role"
    assert all({"ins", "upd", "del"} == set(v) for v in tables.values())


async def test_never_written_agrees_with_the_snapshot():
    await Database.init()
    tables = await snapshot()
    never = set(await never_written())

    assert never, "the engine has tables nothing has written; if this is empty the query is wrong"
    for table in list(never)[:20]:
        assert tables[table]["ins"] == 0 and tables[table]["upd"] == 0


async def test_an_unreadable_view_reports_that_it_could_not_look():
    """The distinction `modules_ok` never made: wrote nothing is not the same as could not look."""
    result = await report({"ships": {"ins": 1, "upd": 0, "del": 0}}, {})

    assert result["readable"] is False
    assert result["moved"] == {}
    assert "not readable" in result["note"]


async def test_a_readable_report_names_the_tables_that_moved():
    await Database.init()
    before = await snapshot()
    result = await report(before, await snapshot())

    assert result["readable"] is True
    assert result["tables_moved"] == 0, "a snapshot of a snapshot must show no movement"
    assert result["rows"] == 0
    assert result["never_written"]
