"""Module review tests for modules/locations.py.

Defects covered:

1. `set_character_presence` wrote only `character_presence_log`, a global audit
   trail. `characters.scene_location` is the column the engine reads back
   (char_query, char_locations, core/context), and nothing in the module ever
   wrote it, so the CLI could place a character for a year and no reader would
   see it move. `cli.py:404` calls it.
2. The new write is session-scoped, so a character id from the other campaign
   matches nothing; that miss used to be invisible in the same way.
3. `set_player_location` built a `val` dict with the location, ship and timestamp
   and never used it.

Reported rather than patched, because the fix changes what the GM sees and the
two vocabularies do not match:
`get_characters_at_location(session_id, location)` returns every active
character in the session and never uses `location`. Measured: characters hold
free-form scene names ("MASTIKA — Royal Palace (household)"), the player's
location is a slug ("bridge"), and session 5's 440 characters all have a NULL
scene_location. An equality filter would empty the scene for the live arc. A
test pins the current behaviour so it cannot drift while the decision is open.

Checked and correct: `character_presence_log` and `location_catalog` have no
`session_id` column, measured against information_schema, so their unscoped
statements are right; `get_characters_at_location` does scope by session.

No database: every test drives a fake connection.
"""
from __future__ import annotations

import pytest

from modules import locations


@pytest.fixture(autouse=True)
def _writable(monkeypatch):
    """The real frozen list must not decide these tests: they name session 3 or 5."""
    monkeypatch.setattr("core.session.is_frozen", lambda sid: False)


class FakeDB:
    def __init__(self, tags=("UPDATE 1",), value=1):
        self.tags = list(tags)
        self.value = value
        self.executes: list[tuple[str, tuple]] = []
        self.rows: list[dict] = []

    async def execute(self, sql, *args):
        self.executes.append((" ".join(sql.split()), args))
        return self.tags.pop(0) if self.tags else "UPDATE 1"

    async def fetch(self, sql, *args):
        return self.rows

    async def fetchrow(self, sql, *args):
        return self.rows[0] if self.rows else None

    async def fetchval(self, sql, *args):
        """The catalogue lookup in `set_player_location`. Without this the call reaches the real
        database, which makes a unit test depend on what is in `location_catalog` that day."""
        return self.value

    def transaction(self):
        """`set_character_presence` runs its UPDATE and INSERT on the yielded connection."""
        fake = self

        class _Tx:
            async def __aenter__(self):
                return fake

            async def __aexit__(self, *exc):
                return False

        return _Tx()


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    logs = {"info": [], "warn": []}
    monkeypatch.setattr(locations, "info", lambda m, msg: logs["info"].append(msg))
    monkeypatch.setattr(locations, "warn", lambda m, msg: logs["warn"].append(msg))
    monkeypatch.setattr(locations.Database, "execute", staticmethod(fake.execute))
    monkeypatch.setattr(locations.Database, "fetch", staticmethod(fake.fetch))
    monkeypatch.setattr(locations.Database, "fetchrow", staticmethod(fake.fetchrow))
    monkeypatch.setattr(locations.Database, "fetchval", staticmethod(fake.fetchval))
    monkeypatch.setattr(locations.Database, "transaction", staticmethod(fake.transaction))
    return fake, logs


async def test_placing_a_character_moves_it_where_readers_look(db):
    """(1) The log row alone left every reader showing the old location."""
    fake, _ = db
    await locations.set_character_presence(42, "medbay", session_id=5)
    moves = [e for e in fake.executes if e[0].startswith("UPDATE maya_rp.characters")]
    assert len(moves) == 1, fake.executes
    assert moves[0][1] == ("medbay", 42, 5), moves[0][1]
    assert any(e[0].startswith("INSERT INTO maya_rp.character_presence_log") for e in fake.executes)
    assert [e[0].split()[0] for e in fake.executes] == ["UPDATE", "INSERT"], fake.executes


async def test_placing_another_campaigns_character_says_so(db):
    """(2) The update is scoped, so the miss has to be reported."""
    fake, logs = db
    fake.tags = ["UPDATE 0"]
    await locations.set_character_presence(999, "medbay", session_id=5)
    assert logs["warn"], "a placement that moved nothing was silent"
    assert not any(e[0].startswith("INSERT INTO maya_rp.character_presence_log") for e in fake.executes), \
        fake.executes


async def test_set_player_location_writes_the_column_readers_use(db):
    """The write that used to be prose, and the prose it still keeps beside it.

    This test was `..._writes_the_line_its_reader_parses`, and it held the round trip: the writer
    produced `Location: observation_deck on Flagship` and the reader split that string back apart.
    Both halves guessed. `player_context` held no rows for any session, so the hardcoded `bridge`
    was the only answer either of them ever gave.
    """
    fake, _ = db
    await locations.set_player_location(5, "observation_deck", "Flagship")
    writes = [e for e in fake.executes if e[0].startswith("INSERT INTO maya_rp.player_context")]
    assert len(writes) == 1, fake.executes
    _, args = writes[0]
    assert args == (5, "observation_deck", "Location: observation_deck on Flagship"), args


async def test_set_player_location_says_when_the_place_is_not_in_the_catalogue(db):
    """A slug outside the catalogue matches no character, so the empty scene needs a reason."""
    fake, logs = db
    fake.value = None  # `SELECT 1 FROM location_catalog` finds nothing
    await locations.set_player_location(5, "somewhere_invented", "Flagship")
    assert logs["warn"], "a location no reader can match was written without a word"


async def test_get_characters_at_location_uses_its_location(db, monkeypatch):
    """The pin was lifted, and this is what replaced it.

    This test used to assert the opposite, under the name
    `..._ignores_the_location_PINNED`, because an equality filter could not match
    anything: every character location in session 5 was NULL, session 3's were
    free-form scene names like `MASTIKA — Royal Palace (household)`, and the
    player's side was a slug parsed out of `current_focus`. Migration
    `131_scene_location_catalog.sql` gave both sides one vocabulary — a
    `maya_rp.location_catalog.name` — so the filter is now the behaviour to hold.
    """
    fake, _ = db
    seen: list[tuple] = []

    async def capture(sql, *args):
        seen.append((sql, args))
        return []

    monkeypatch.setattr(locations.Database, "fetch", staticmethod(capture))
    await locations.get_characters_at_location(5, "medbay")
    assert seen == [(
        "SELECT c.name, c.bond, c.role FROM maya_rp.characters c "
        "WHERE c.session_id=$1 AND c.status='active' AND c.scene_location=$2 "
        "ORDER BY c.bond DESC", (5, "medbay"))], seen


async def test_get_characters_at_location_asks_nothing_when_the_scene_is_unset(db, monkeypatch):
    """An unset scene is empty, and it does not become the roster as a consolation."""
    fake, _ = db
    seen: list[tuple] = []

    async def capture(sql, *args):
        seen.append((sql, args))
        return []

    monkeypatch.setattr(locations.Database, "fetch", staticmethod(capture))
    assert await locations.get_characters_at_location(5, None) == []
    assert seen == [], "no query is issued for a scene that has no location"


async def test_get_player_location_reads_the_column_before_parsing_prose(db, monkeypatch):
    """The column is the answer. `current_focus` is only a fallback, and a loud one."""
    fake, _ = db

    async def with_column(sql, *args):
        return {"location": "heaven_reach", "current_focus": "Location: bridge on Flagship", "mood": None}

    monkeypatch.setattr(locations.Database, "fetchrow", staticmethod(with_column))
    got = await locations.get_player_location(5)
    assert got == {"location": "heaven_reach", "ship": None, "source": "column"}, got


async def test_get_player_location_parses_only_when_the_column_is_empty(db, monkeypatch):
    fake, _ = db

    async def prose_only(sql, *args):
        return {"location": None, "current_focus": "Location: observation_deck on Flagship", "mood": None}

    monkeypatch.setattr(locations.Database, "fetchrow", staticmethod(prose_only))
    got = await locations.get_player_location(5)
    assert got["location"] == "observation_deck"
    assert got["source"] == "parsed", "a parsed location must say that it was parsed"


async def test_get_player_location_invents_nothing_when_both_are_empty(db, monkeypatch):
    """It used to answer `bridge` here, for every session that never set a focus."""
    fake, _ = db

    async def nothing(sql, *args):
        return None

    monkeypatch.setattr(locations.Database, "fetchrow", staticmethod(nothing))
    got = await locations.get_player_location(5)
    assert got == {"location": None, "ship": None, "source": "unset"}, got
