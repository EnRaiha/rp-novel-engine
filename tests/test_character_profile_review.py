"""Module review tests for modules/character_profile.py (2026-10-03).

The database-backed tests borrow a session-5 character, snapshot the four jsonb
columns they touch, and put the row back in a finally. Nothing is left behind.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.character_profile as cp  # noqa: E402
from core.db import Database  # noqa: E402

COLUMNS = ("inventory_jsonb", "wardrobe_jsonb", "profile_jsonb", "current_outfit")


def _run(coro):
    return asyncio.run(coro)


def _text(value):
    """asyncpg hands jsonb back as text; a decoded value has to go back that way."""
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value)


async def _borrow(require_wardrobe: bool = False, session_id: int = 5):
    where = "AND jsonb_array_length(wardrobe_jsonb) > 0" if require_wardrobe else ""
    return await Database.fetchrow(
        f"SELECT id, {', '.join(COLUMNS)} FROM maya_rp.characters "
        f"WHERE session_id = $1 {where} ORDER BY id LIMIT 1",
        session_id,
    )


async def _restore(before):
    await Database.execute(
        "UPDATE maya_rp.characters SET inventory_jsonb=$1::jsonb, wardrobe_jsonb=$2::jsonb, "
        "profile_jsonb=$3::jsonb, current_outfit=$4::jsonb WHERE id=$5",
        *[_text(before[c]) for c in COLUMNS], before["id"],
    )


# ── A write that matched no row used to report success ──────────────────


def test_every_write_refuses_a_character_that_does_not_exist():
    missing = 10_000_000
    for call, payload in ((cp.add_item, {"name": "knife"}),
                          (cp.add_to_wardrobe, {"id": "coat"}),
                          (cp.update_profile, {"face": {"eyes": "grey"}})):
        with pytest.raises(ValueError, match="not found in session 5"):
            _run(call(missing, payload, 5))
    with pytest.raises(ValueError, match="not found in session 5"):
        _run(cp.set_outfit(missing, "coat", 5))


def test_grant_refuses_an_outfit_that_is_not_in_the_wardrobe():
    async def scenario():
        await Database.init()
        row = await _borrow(require_wardrobe=True)
        try:
            assert row, "no session-5 character with a wardrobe"
            before = await Database.fetchval(
                "SELECT current_outfit FROM maya_rp.characters WHERE id=$1", row["id"])
            with pytest.raises(ValueError, match="not in character"):
                await cp.grant(int(row["id"]), wear="review-no-such-outfit", session_id=5)
            after = await Database.fetchval(
                "SELECT current_outfit FROM maya_rp.characters WHERE id=$1", row["id"])
            assert _text(after) == _text(before)
        finally:
            if row:
                await _restore(row)
            await Database.close()

    _run(scenario())


def test_grant_refuses_a_payload_that_is_not_a_mapping():
    assert not _run(_refusals())


async def _refusals():
    with pytest.raises(ValueError, match="item must be a mapping"):
        await cp.grant(2071, item="knife", session_id=5)
    with pytest.raises(ValueError, match="outfit must be a mapping"):
        await cp.grant(2071, outfit=["coat"], session_id=5)
    with pytest.raises(ValueError, match="profile_data must be a mapping"):
        await cp.grant(2071, profile="tall", session_id=5)


# ── The card, on the column shape `_as_list` exists for ─────────────────


def test_the_card_treats_a_dict_shaped_inventory_as_empty():
    """Nine characters carried `{}` in inventory_jsonb; the reading path covers it."""

    async def scenario():
        await Database.init()
        row = await _borrow()
        try:
            assert row, "no session-5 character to borrow"
            await Database.execute(
                "UPDATE maya_rp.characters SET inventory_jsonb='{}'::jsonb WHERE id=$1", row["id"])
            return await cp.get_character_card(int(row["id"]), 5)
        finally:
            if row:
                await _restore(row)
            await Database.close()

    card = _run(scenario())
    assert "──" in card and "not found" not in card
    assert "Visible Items" not in card


def test_the_card_refuses_an_inventory_that_holds_contents_but_is_not_a_list():
    async def scenario():
        await Database.init()
        row = await _borrow()
        try:
            assert row, "no session-5 character to borrow"
            await Database.execute(
                "UPDATE maya_rp.characters SET inventory_jsonb='{\"items\": [{\"name\": \"x\"}]}'::jsonb"
                " WHERE id=$1", row["id"])
            with pytest.raises(ValueError, match="not a list"):
                await cp.get_character_card(int(row["id"]), 5)
        finally:
            if row:
                await _restore(row)
            await Database.close()

    _run(scenario())


def test_the_card_survives_plain_string_entries_in_the_inventory():
    """A live row holds `["knife", "knife"]`; `.get` on a string raised AttributeError.

    Read-only: the row this reads belongs to the campaign, so the test borrows it
    and changes nothing.
    """

    async def scenario():
        await Database.init()
        try:
            row = await Database.fetchrow(
                "SELECT id FROM maya_rp.characters WHERE session_id = 5 AND EXISTS "
                "(SELECT 1 FROM jsonb_array_elements(inventory_jsonb) e "
                " WHERE jsonb_typeof(e) <> 'object') ORDER BY id LIMIT 1")
            if not row:
                pytest.skip("no session-5 character carries a non-object inventory entry")
            return await cp.get_character_card(int(row["id"]), 5)
        finally:
            await Database.close()

    card = _run(scenario())
    assert "not found" not in card
    assert "Visible Items" not in card


def test_the_card_reports_what_grant_handed_over():
    async def scenario():
        await Database.init()
        row = await _borrow()
        try:
            assert row, "no session-5 character to borrow"
            cid = int(row["id"])
            await cp.grant(cid, outfit={"id": "review-coat", "name": "Review Coat",
                                        "tags": ["formal"]}, session_id=5)
            await cp.grant(cid, item={"name": "Review Knife", "slot": "held"}, session_id=5)
            await cp.grant(cid, wear="review-coat", session_id=5)
            return await cp.get_character_card(cid, 5)
        finally:
            if row:
                await _restore(row)
            await Database.close()

    card = _run(scenario())
    assert "Review Coat" in card, card
    assert "Visible Items: Review Knife" in card, card


def test_auto_dress_matches_the_tag_and_settles_when_already_worn():
    async def scenario():
        await Database.init()
        row = await _borrow()
        try:
            assert row, "no session-5 character to borrow"
            cid = int(row["id"])
            await cp.grant(cid, outfit={"id": "review-armour", "name": "Review Armour",
                                        "tags": ["combat"]}, session_id=5)
            first = await cp.auto_dress_for_mode(cid, "combat", 5)
            second = await cp.auto_dress_for_mode(cid, "combat", 5)
            return first, second
        finally:
            if row:
                await _restore(row)
            await Database.close()

    first, second = _run(scenario())
    assert first is True, "the dresser did not put the combat outfit on"
    assert second is False, "the dresser changed the outfit twice"


def test_auto_dress_returns_false_for_a_character_with_no_row(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(cp, "Database", stub)
    assert _run(cp.auto_dress_for_mode(10_000_000, "combat", 5)) is False


class _StubDB:
    """`auto_dress_for_mode` alone: one empty column read, no connection."""

    async def fetchval(self, sql, *args):
        return None


# ── The module's own coercion contract ──────────────────────────────────


def test_the_two_coercions_agree_on_empty_and_refuse_contents():
    assert cp._as_list("{}", "inventory_jsonb") == []
    assert cp._as_dict("[]", "profile_jsonb") == {}
    assert cp._as_list(None, "inventory_jsonb") == []
    assert cp._as_dict(None, "current_outfit") == {}
    assert cp._as_list('[{"id": "coat"}]', "wardrobe_jsonb") == [{"id": "coat"}]
    assert cp._as_dict('{"face": {}}', "profile_jsonb") == {"face": {}}
    with pytest.raises(ValueError, match="not a list"):
        cp._as_list('{"items": [1]}', "inventory_jsonb")
    with pytest.raises(ValueError, match="not an object"):
        cp._as_dict('["coat"]', "current_outfit")


def test_the_card_names_the_character_and_the_role():
    async def scenario():
        await Database.init()
        row = await _borrow()
        try:
            assert row, "no session-5 character to borrow"
            cid = int(row["id"])
            await cp.update_profile(cid, {"face": {"eyes": "amber"},
                                          "body": {"build": "lean"},
                                          "voice": "dry"}, session_id=5)
            return await cp.get_character_card(cid, 5)
        finally:
            if row:
                await _restore(row)
            await Database.close()

    card = _run(scenario())
    assert "Eyes: amber" in card, card
    assert "Build: lean" in card, card
    assert "Voice: dry" in card, card
