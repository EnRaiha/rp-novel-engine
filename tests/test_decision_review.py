"""Module review tests for core/decision.py.

Defects covered:

1. `decisions(session_id, ...)` accepted a session and never used it: the
   `decision_stream` view select-lists neither branch's `session_id`, and the
   query carried `WHERE 1=1`. `cli.py decisions list` therefore showed both
   campaigns' decrees and grand-plan items.
2. `add_cli` imported `parse_kv_flags` from `core.utils`, which has no such name,
   so `cli.py decisions add ...` died with ImportError before it parsed anything.
   The local `_parse_flags` is the parser and was already there.
3. `by_fact` typed every `fact_value` as a JSON string (`f'"{value}"'`), so a
   numeric lookup never equalled the number in the column. Reachable from
   `cli.py lineage <fact> <value>`.
4. `record(decree_id=...)` returned the id whether or not the UPDATE matched a
   row, so a decree in another session (or none) was reported as written.
5. `record` read `session_id or Config.SESSION_ID`, the `or`-default class: a
   session of 0 became the frozen default.
6. `link_event` completes in silence when the decision is not in this session.

Checked and found correct, so the row is not silent about what it looked at:
`chain` scopes every hop by session and caps the walk at `depth`; `by_fact`'s
key-only branch scopes by session; the INSERT path returns the id it got back
from RETURNING; `link_event` carries `AND session_id=$3` already; the
`decision_stream` view itself is a database object, so the filter had to be
expressed against its base tables from inside the module.

No database: every test drives a fake connection.
"""
from __future__ import annotations

import json

import pytest

from core import decision


class FakeDB:
    def __init__(self):
        self.calls: list[tuple[str, str, tuple]] = []
        self.fetch_rows: list = []
        self.fetchrow_result = {"id": 42}
        self.execute_tag = "UPDATE 1"
        self.warnings: list[str] = []

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        return self.fetch_rows

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", " ".join(sql.split()), args))
        return self.fetchrow_result

    async def execute(self, sql, *args):
        self.calls.append(("execute", " ".join(sql.split()), args))
        return self.execute_tag

    def last(self, kind: str):
        return [c for c in self.calls if c[0] == kind][-1]


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(decision, "warn", lambda m, msg: fake.warnings.append(msg))
    monkeypatch.setattr(decision.Database, "fetch", staticmethod(fake.fetch))
    monkeypatch.setattr(decision.Database, "fetchrow", staticmethod(fake.fetchrow))
    monkeypatch.setattr(decision.Database, "execute", staticmethod(fake.execute))
    return fake


async def test_decisions_asks_only_this_session(db):
    """(1) The session was accepted and never reached the query."""
    await decision.decisions(5)
    _, sql, args = db.last("fetch")
    assert "session_id = $1" in sql, sql
    assert args[0] == 5, args


async def test_decisions_keeps_its_optional_filters(db):
    """(1) The filter numbering still lines up after the session predicate."""
    await decision.decisions(5, day=7, kind="decree", status="executing", limit=3)
    _, sql, args = db.last("fetch")
    assert args == (5, 7, "decree", "executing", 3), args
    assert "AND game_day = $2" in sql and "AND kind = $3" in sql
    assert "AND status = $4" in sql and "LIMIT $5" in sql


async def test_record_writes_the_session_it_was_given(db):
    await decision.record("Izzat", "directive", "Test", session_id=9)
    _, _, args = db.last("fetchrow")
    assert args[0] == 9, args


async def test_record_reads_a_zero_session_as_given(db):
    """(5) `session_id or default` turned a real 0 into the frozen campaign."""
    await decision.record("Izzat", "directive", "Test", session_id=0)
    _, _, args = db.last("fetchrow")
    assert args[0] == 0, args


async def test_record_reports_a_decree_that_is_not_there(db):
    """(4) A miss was reported as a written provenance chain."""
    db.execute_tag = "UPDATE 0"
    out = await decision.record("Izzat", "directive", "Test", decree_id=7, session_id=5)
    assert out is None
    assert db.warnings, "a missed decree update said nothing"


async def test_record_returns_the_decree_id_when_the_row_matches(db):
    db.execute_tag = "UPDATE 1"
    out = await decision.record("Izzat", "directive", "Test", decree_id=7, session_id=5)
    assert out == 7
    assert not db.warnings


async def test_by_fact_asks_for_a_number_as_a_number(db):
    """(3) 1200 was typed as the JSON string "1200" and matched no number."""
    await decision.by_fact(5, "treasury", 1200)
    _, _, args = db.last("fetch")
    assert args[2] == "1200", args


async def test_by_fact_asks_for_a_string_as_a_string(db):
    await decision.by_fact(5, "treasury", "1200")
    _, _, args = db.last("fetch")
    assert args[2] == '"1200"', args


async def test_add_cli_records_a_decision(db):
    """(2) The dead import made `cli.py decisions add` an ImportError."""
    out = await decision.add_cli(["--title", "Ammunition", "--day", "7",
                                  "--delta", '{"credits": -5}'])
    assert out == {"decision_id": 42, "title": "Ammunition"}
    _, _, args = db.last("fetchrow")
    assert args[3] == "Ammunition" and args[8] == 7, args
    assert json.loads(args[11]) == {"credits": -5}, "jsonb parameters are bound as JSON text"


async def test_link_event_logs_a_miss(db):
    """(6) The contract is `-> None`; a miss still has to be visible somewhere."""
    db.execute_tag = "UPDATE 0"
    out = await decision.link_event(5, 999_999, 999_999)
    assert out is None
    assert db.warnings, "an event that linked nothing said nothing"
