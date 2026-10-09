"""character_profile: concurrent grants keep every entry, and a name search matches literally.

Every test runs on a scratch session with its own `sessions` and `characters` rows.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import pathlib
import sys

import pytest
import pytest_asyncio

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.character_profile as cp  # noqa: E402
from core.db import Database  # noqa: E402


@pytest_asyncio.fixture
async def cast(scratch_session):
    """A scratch campaign with no characters."""
    await Database.init()
    await Database.execute("DELETE FROM maya_rp.characters WHERE session_id = $1", scratch_session)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1, 'profile fix2', 'active')",
        scratch_session)
    yield scratch_session
    await Database.execute("DELETE FROM maya_rp.characters WHERE session_id = $1", scratch_session)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", scratch_session)
    await Database.close()


async def _character(sid: int, name: str = "Fix Two", bond: int = 0, **columns) -> int:
    """One character row. `columns` maps a jsonb column to its raw JSON text."""
    cid = await Database.fetchval(
        "INSERT INTO maya_rp.characters (session_id, name, bond) VALUES ($1, $2, $3) RETURNING id",
        sid, name, bond)
    for column, raw in columns.items():
        await Database.execute(
            f"UPDATE maya_rp.characters SET {column} = $1::jsonb WHERE id = $2", raw, cid)
    return cid


async def _column(cid: int, column: str):
    raw = await Database.fetchval(f"SELECT {column} FROM maya_rp.characters WHERE id = $1", cid)
    return json.loads(raw) if isinstance(raw, str) else raw


class _ConnSpy:
    def __init__(self, conn, log):
        self._conn, self._log = conn, log

    def __getattr__(self, name):
        attr = getattr(self._conn, name)
        if name not in ("fetch", "fetchrow", "fetchval", "execute"):
            return attr

        async def recorded(query, *args):
            self._log.append(("conn", " ".join(query.split())))
            return await attr(query, *args)
        return recorded


class _DatabaseSpy:
    """`Database` that records which statements ran on the pool and which ran on a transaction's connection."""

    def __init__(self, log):
        self.log = log

    def __getattr__(self, name):
        attr = getattr(Database, name)
        if name not in ("fetch", "fetchrow", "fetchval", "execute"):
            return attr

        async def recorded(query, *args):
            self.log.append(("pool", " ".join(query.split())))
            return await attr(query, *args)
        return recorded

    @contextlib.asynccontextmanager
    async def transaction(self):
        async with Database.transaction() as conn:
            yield _ConnSpy(conn, self.log)


# ── L1a: the append keeps every entry ────────────────────────────────────


@pytest.mark.parametrize("call, column", [(cp.add_item, "inventory_jsonb"),
                                          (cp.add_to_wardrobe, "wardrobe_jsonb")])
async def test_a_grant_that_starts_while_another_holds_the_row_keeps_both(cast, call, column):
    cid = await _character(cast)
    release = asyncio.Event()

    async def holder():
        async with Database.transaction() as conn:
            await conn.fetchrow("SELECT 1 FROM maya_rp.characters WHERE id = $1 FOR UPDATE", cid)
            await release.wait()
            await conn.execute(
                f"UPDATE maya_rp.characters SET {column} = $1 WHERE id = $2",
                json.dumps([{"id": "first", "name": "first"}]), cid)

    held = asyncio.create_task(holder())
    await asyncio.sleep(0.3)
    second = asyncio.create_task(call(cid, {"id": "second", "name": "second"}, cast))
    await asyncio.sleep(0.5)
    release.set()
    await asyncio.gather(held, second)

    assert [e["id"] for e in await _column(cid, column)] == ["first", "second"]


@pytest.mark.parametrize("call, column", [(cp.add_item, "inventory_jsonb"),
                                          (cp.add_to_wardrobe, "wardrobe_jsonb")])
async def test_concurrent_grants_all_land(cast, call, column):
    cid = await _character(cast)

    await asyncio.gather(*(call(cid, {"id": f"e{i}", "name": f"e{i}"}, cast) for i in range(8)))

    assert sorted(e["id"] for e in await _column(cid, column)) == sorted(f"e{i}" for i in range(8))


@pytest.mark.parametrize("call, column", [(cp.add_item, "inventory_jsonb"),
                                          (cp.add_to_wardrobe, "wardrobe_jsonb")])
async def test_the_read_locks_the_row_and_both_statements_share_one_connection(
        cast, monkeypatch, call, column):
    cid = await _character(cast)
    log: list[tuple[str, str]] = []
    monkeypatch.setattr(cp, "Database", _DatabaseSpy(log))

    await call(cid, {"id": "coat"}, cast)

    reads = [(where, q) for where, q in log if q.startswith("SELECT") and column in q]
    writes = [(where, q) for where, q in log if q.startswith("UPDATE") and column in q]
    assert len(reads) == 1 and len(writes) == 1, log
    assert "FOR UPDATE" in reads[0][1], reads
    assert reads[0][0] == writes[0][0] == "conn", log


@pytest.mark.parametrize("call, column", [(cp.add_item, "inventory_jsonb"),
                                          (cp.add_to_wardrobe, "wardrobe_jsonb")])
async def test_an_append_keeps_what_the_list_held(cast, call, column):
    cid = await _character(cast, **{column: '[{"id": "old"}]'})

    await call(cid, {"id": "new"}, cast)

    assert await _column(cid, column) == [{"id": "old"}, {"id": "new"}]


@pytest.mark.parametrize("call, column", [(cp.add_item, "inventory_jsonb"),
                                          (cp.add_to_wardrobe, "wardrobe_jsonb")])
async def test_an_empty_object_column_is_treated_as_an_empty_list(cast, call, column):
    cid = await _character(cast, **{column: "{}"})

    await call(cid, {"id": "new"}, cast)

    assert await _column(cid, column) == [{"id": "new"}]


@pytest.mark.parametrize("call, column", [(cp.add_item, "inventory_jsonb"),
                                          (cp.add_to_wardrobe, "wardrobe_jsonb")])
async def test_an_object_with_contents_is_refused_and_left_alone(cast, call, column):
    cid = await _character(cast, **{column: '{"items": [1]}'})

    with pytest.raises(ValueError, match="not a list"):
        await call(cid, {"id": "new"}, cast)

    assert await _column(cid, column) == {"items": [1]}


@pytest.mark.parametrize("call", [cp.add_item, cp.add_to_wardrobe])
async def test_a_missing_character_is_refused_by_id_and_session(cast, call):
    with pytest.raises(ValueError, match=f"character 999999999 not found in session {cast}"):
        await call(999_999_999, {"id": "new"}, cast)


# ── L1b: the name search matches literally ───────────────────────────────


async def test_a_percent_in_a_name_is_matched_literally(cast):
    await _character(cast, "Aria", bond=10)
    await _character(cast, "Zed", bond=0)

    assert "ZED" in await cp.get_character_card_by_name("zed", cast)
    assert await cp.get_character_card_by_name("z%", cast) == "Character not found."


async def test_an_underscore_in_a_name_is_matched_literally(cast):
    await _character(cast, "Aria", bond=10)

    assert "ARIA" in await cp.get_character_card_by_name("ari", cast)
    assert await cp.get_character_card_by_name("Ari_", cast) == "Character not found."


async def test_a_name_that_contains_the_wildcard_characters_is_found_by_them(cast):
    await _character(cast, "Kazel", bond=10)
    await _character(cast, "Ka_el 100%", bond=0)

    assert "KA_EL 100%" in await cp.get_character_card_by_name("a_el", cast)
    assert "KA_EL 100%" in await cp.get_character_card_by_name("0%", cast)


async def test_a_backslash_in_a_name_is_matched_literally(cast):
    await _character(cast, "Back\\slash", bond=0)

    assert "BACK\\SLASH" in await cp.get_character_card_by_name("k\\sl", cast)
    assert await cp.get_character_card_by_name("ksl", cast) == "Character not found."


async def test_the_exact_name_still_wins_over_a_longer_match(cast):
    await _character(cast, "Mira Long", bond=50)
    await _character(cast, "Mira", bond=0)

    assert "── MIRA ──" in await cp.get_character_card_by_name("mira", cast)


def test_contains_escapes_the_three_special_characters():
    assert cp._contains("a%b_c\\d") == "%a\\%b\\_c\\\\d%"
