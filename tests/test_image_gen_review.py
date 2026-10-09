"""Module review tests for modules/image_gen.py.

Defects covered:

1. The ship read selected `hull` and never used it: a numeric hull value cannot
   go into a prompt, so the column was dead weight in the query. Dropped.
2. `prompt = f"Space scene: "` was an f-string with no placeholder.

Checked and found correct: every read is session-scoped and randomised; the
insert names the columns the table actually has (`image_prompts` keys on
(scene_type, prompt_full) and scene_type is enum-checked, which an earlier pass
had already fixed); the scene type follows what the prompt describes; the
subject falls back to None when no character exists; and the tick is a stub.

No database: every test drives a fake Database.
"""
from __future__ import annotations

import pytest

import modules.image_gen as ig


@pytest.fixture(autouse=True)
def _writable(monkeypatch):
    """The real frozen list must not decide these tests: they name session 3 or 5."""
    monkeypatch.setattr("core.session.is_frozen", lambda sid: False)


class FakeDB:
    def __init__(self, rows=None, execute_tag="INSERT 0 1"):
        self.row_map = rows or {}
        self.execute_tag = execute_tag
        self.calls = []

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", " ".join(sql.split()), args))
        for marker, value in self.row_map.items():
            if marker in sql:
                return value
        return None

    async def execute(self, sql, *args):
        self.calls.append(("execute", " ".join(sql.split()), args))
        return self.execute_tag

    def sql(self, kind=None):
        return [c[1] for c in self.calls if kind is None or c[0] == kind]

    def args_for(self, needle, kind=None):
        return [c[2] for c in self.calls
                if needle in c[1] and (kind is None or c[0] == kind)]


def _install(monkeypatch, fake):
    for name in ("fetchrow", "execute"):
        monkeypatch.setattr("modules.image_gen.Database." + name, getattr(fake, name))
    return fake


SHIP = {"name": "TKG Simpanan", "tier": 4}
CHAR = {"name": "Seraphina", "role": "admiral"}
SYSTEM = {"system_name": "Mastika"}


async def test_the_ship_read_no_longer_asks_for_an_unused_column(monkeypatch):
    fake = _install(monkeypatch, FakeDB(rows={"ships": SHIP, "characters": CHAR,
                                              "territory": SYSTEM}))

    await ig.generate_prompt(5)

    sql = [s for s in fake.sql("fetchrow") if "maya_rp.ships" in s][0]
    assert "hull" not in sql, sql
    assert "name, tier" in sql


async def test_the_prompt_names_the_character_and_the_system(monkeypatch):
    _install(monkeypatch, FakeDB(rows={"ships": SHIP, "characters": CHAR,
                                       "territory": SYSTEM}))

    out = await ig.generate_prompt(5)

    assert out["prompt"].startswith("Space scene: Seraphina (admiral)")
    assert "T4 vessel in the Mastika system" in out["prompt"]
    assert out["scene_type"] == "character-portrait"


async def test_a_scene_with_no_character_is_landscape(monkeypatch):
    _install(monkeypatch, FakeDB(rows={"ships": SHIP, "territory": SYSTEM}))

    out = await ig.generate_prompt(5)

    assert out["scene_type"] == "planet-landscape"
    assert "Seraphina" not in out["prompt"]


async def test_the_insert_names_the_real_columns(monkeypatch):
    fake = _install(monkeypatch, FakeDB(rows={"ships": SHIP, "characters": CHAR,
                                              "territory": SYSTEM}))

    out = await ig.generate_prompt(5)

    sql = fake.sql("execute")[0]
    assert "INSERT INTO maya_rp.image_prompts (session_id, scene_type, subject_name, prompt_full)" in sql
    args = fake.args_for("INSERT INTO maya_rp.image_prompts", "execute")[0]
    assert args[0] == 5 and args[1] == "character-portrait" and args[2] == "Seraphina"
    assert args[3] == out["prompt"]


async def test_every_read_is_session_scoped(monkeypatch):
    fake = _install(monkeypatch, FakeDB(rows={}))

    await ig.generate_prompt(5)

    for sql in fake.sql("fetchrow"):
        assert "session_id=$1" in sql, sql
    assert fake.args_for("maya_rp.ships", "fetchrow")[0] == (5,)


async def test_an_empty_campaign_still_produces_a_prompt(monkeypatch):
    _install(monkeypatch, FakeDB(rows={}))

    out = await ig.generate_prompt(5)

    assert "Sci-fi cinematic lighting" in out["prompt"]
    assert out["scene_type"] == "planet-landscape"


async def test_contract_run_tick_is_a_stub():
    assert await ig.run_tick(5) == {"status": "image_gen_ready"}
