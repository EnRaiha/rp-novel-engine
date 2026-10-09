"""Module review tests for modules/character_profile.py (2026-10-03).

Every database-backed test runs on a scratch session with its own character row, so nothing
touches the campaigns.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest
import pytest_asyncio

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.character_profile as cp  # noqa: E402
from core.db import Database  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


@pytest_asyncio.fixture
async def subject(scratch_session):
    """A scratch campaign with one character: (session_id, character_id)."""
    await Database.init()
    await Database.execute("DELETE FROM maya_rp.characters WHERE session_id = $1", scratch_session)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1, 'profile review', 'active')",
        scratch_session)
    cid = await Database.fetchval(
        "INSERT INTO maya_rp.characters (session_id, name, role) VALUES ($1, 'Review Subject', 'tester')"
        " RETURNING id", scratch_session)
    yield scratch_session, int(cid)
    await Database.execute("DELETE FROM maya_rp.characters WHERE session_id = $1", scratch_session)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", scratch_session)
    await Database.close()


async def _set_inventory(cid: int, raw: str) -> None:
    await Database.execute(
        "UPDATE maya_rp.characters SET inventory_jsonb = $1::jsonb WHERE id = $2", raw, cid)


# ── A write that matched no row used to report success ──────────────────


async def test_every_write_refuses_a_character_that_does_not_exist(subject):
    sid, _ = subject
    missing = 10_000_000
    for call, payload in ((cp.add_item, {"name": "knife"}),
                          (cp.add_to_wardrobe, {"id": "coat"}),
                          (cp.update_profile, {"face": {"eyes": "grey"}})):
        with pytest.raises(ValueError, match=f"not found in session {sid}"):
            await call(missing, payload, sid)
    with pytest.raises(ValueError, match=f"not found in session {sid}"):
        await cp.set_outfit(missing, "coat", sid)


async def test_grant_refuses_an_outfit_that_is_not_in_the_wardrobe(subject):
    sid, cid = subject
    await cp.add_to_wardrobe(cid, {"id": "coat", "name": "Coat"}, sid)
    before = await Database.fetchval(
        "SELECT current_outfit FROM maya_rp.characters WHERE id=$1", cid)
    with pytest.raises(ValueError, match="not in character"):
        await cp.grant(cid, wear="review-no-such-outfit", session_id=sid)
    after = await Database.fetchval(
        "SELECT current_outfit FROM maya_rp.characters WHERE id=$1", cid)
    assert after == before


async def test_grant_refuses_a_payload_that_is_not_a_mapping(subject):
    sid, cid = subject
    with pytest.raises(ValueError, match="item must be a mapping"):
        await cp.grant(cid, item="knife", session_id=sid)
    with pytest.raises(ValueError, match="outfit must be a mapping"):
        await cp.grant(cid, outfit=["coat"], session_id=sid)
    with pytest.raises(ValueError, match="profile_data must be a mapping"):
        await cp.grant(cid, profile="tall", session_id=sid)


# ── The card, on the column shape `_as_list` exists for ─────────────────


async def test_the_card_treats_a_dict_shaped_inventory_as_empty(subject):
    """Nine characters carried `{}` in inventory_jsonb; the reading path covers it."""
    sid, cid = subject
    await _set_inventory(cid, "{}")

    card = await cp.get_character_card(cid, sid)

    assert "──" in card and "not found" not in card
    assert "Visible Items" not in card


async def test_the_card_refuses_an_inventory_that_holds_contents_but_is_not_a_list(subject):
    sid, cid = subject
    await _set_inventory(cid, '{"items": [{"name": "x"}]}')

    with pytest.raises(ValueError, match="not a list"):
        await cp.get_character_card(cid, sid)


async def test_the_card_survives_plain_string_entries_in_the_inventory(subject):
    """A live row held `["knife", "knife"]`; `.get` on a string raised AttributeError."""
    sid, cid = subject
    await _set_inventory(cid, '["knife", "knife"]')

    card = await cp.get_character_card(cid, sid)

    assert "not found" not in card
    assert "Visible Items" not in card


async def test_the_card_reports_what_grant_handed_over(subject):
    sid, cid = subject
    await cp.grant(cid, outfit={"id": "review-coat", "name": "Review Coat",
                                "tags": ["formal"]}, session_id=sid)
    await cp.grant(cid, item={"name": "Review Knife", "slot": "held"}, session_id=sid)
    await cp.grant(cid, wear="review-coat", session_id=sid)

    card = await cp.get_character_card(cid, sid)

    assert "Review Coat" in card, card
    assert "Visible Items: Review Knife" in card, card


async def test_auto_dress_matches_the_tag_and_settles_when_already_worn(subject):
    sid, cid = subject
    await cp.grant(cid, outfit={"id": "review-armour", "name": "Review Armour",
                                "tags": ["combat"]}, session_id=sid)

    first = await cp.auto_dress_for_mode(cid, "combat", sid)
    second = await cp.auto_dress_for_mode(cid, "combat", sid)

    assert first is True, "the dresser did not put the combat outfit on"
    assert second is False, "the dresser changed the outfit twice"


def test_auto_dress_returns_false_for_a_character_with_no_row(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(cp, "Database", stub)
    assert _run(cp.auto_dress_for_mode(10_000_000, "combat", 900)) is False


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


async def test_the_card_names_the_character_and_the_role(subject):
    sid, cid = subject
    await cp.update_profile(cid, {"face": {"eyes": "amber"},
                                  "body": {"build": "lean"},
                                  "voice": "dry"}, session_id=sid)

    card = await cp.get_character_card(cid, sid)

    assert "Eyes: amber" in card, card
    assert "Build: lean" in card, card
    assert "Voice: dry" in card, card
