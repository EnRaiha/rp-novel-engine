"""Module review: core/campaign.py.

FIVE DEFECTS, and the first two are one feature that could not work.

`restore_snapshot` applies four things by its docstring: state, milestone completions, exemptions
and suspicion. The body wrote two of them and counted the other two in its return value, so an act
resumed from a file lost every purchased exemption and every observer's suspicion while the result
said they had come back.

The same function could not read its own file. `save_snapshot` writes JSON, so every datetime comes
back as text, and asyncpg refuses text for a timestamptz parameter: `cli.py ooc snapshot save` then
`load` raised DataError on the first milestone that carried a completion. The in-process shape
(`snapshot()` straight into `restore_snapshot()`) hid it, which is the shape the one existing test
used.

`character_rules` read `ooc_rules` with no session filter, while `effective_rules` documents the
cascade as "campaign-scope rows (`session_id IS NULL`) plus this session's rows" and `lore_entries`
implements it. A rule authored for one campaign coloured another campaign's scenes.

`spend` priced three sinks and implemented two: any fourth entry added to `SPEND_PRICES` fell into
the `reveal_intel` branch, spending the points and recording a director note as if the caller had
asked for intel.

`triggered_endings` stamped an ending by `id` alone.

Not changed, reported: `condition_met` reads an unknown stat name as 0 and an unknown operator or
unparseable condition as "not met", so a typo in an ending's condition makes it quietly
unreachable. Measured first: all three rows in `ooc_endings` name a stat `stats()` produces and an
operator `OPS` carries, so nothing live depends on the fallback.

The scratch sessions are derived from the process id in a band no other test file uses (500, 600,
700, 800 and 900 are taken). Every row this file writes is removed in the fixture's finally.
"""
from __future__ import annotations

import inspect
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import campaign, ooc  # noqa: E402
from core.db import Database  # noqa: E402

SCRATCH_SESSION = 400 + (os.getpid() % 100)
OTHER_SESSION = SCRATCH_SESSION + 500
SUBJECT = "Campaign Review Subject"
#: No live persona carries this trait, so a rule scoped to it cannot reach a running campaign.
REVIEW_TRAIT = f"review-trait-{os.getpid()}"

CLEANUP = (
    "DELETE FROM maya_rp.ooc_directives WHERE session_id=$1",
    "DELETE FROM maya_rp.character_knowledge WHERE session_id=$1",
    "DELETE FROM maya_rp.character_assets WHERE session_id=$1",
    "DELETE FROM maya_rp.ooc_suspicion WHERE session_id=$1",
    "DELETE FROM maya_rp.ooc_exemptions WHERE session_id=$1",
    "DELETE FROM maya_rp.ooc_milestones WHERE session_id=$1",
    "DELETE FROM maya_rp.ooc_endings WHERE session_id=$1",
    "DELETE FROM maya_rp.ooc_system_state WHERE session_id=$1",
    "DELETE FROM maya_rp.characters WHERE session_id=$1",
)


async def _clear(session_id: int) -> None:
    for statement in CLEANUP:
        await Database.execute(statement, session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


async def _make_session(session_id: int, traits: str) -> int:
    """A session with one character; returns the character id.

    An `ooc_system_state` row comes too: `ooc_rules.session_id` carries a foreign key to it, so a
    session-scoped rule needs the session to have state.
    """
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1,'Campaign review session','active')"
        " ON CONFLICT (id) DO NOTHING",
        session_id,
    )
    await Database.execute(
        "INSERT INTO maya_rp.ooc_system_state (session_id) VALUES ($1)"
        " ON CONFLICT (session_id) DO NOTHING",
        session_id,
    )
    return await Database.fetchval(
        "INSERT INTO maya_rp.characters (session_id, name, status, bond, traits)"
        f" VALUES ($1,$2,'active',0,'{traits}'::jsonb) RETURNING id",
        session_id,
        SUBJECT,
    )


@pytest.fixture()
async def scratch_session():
    """Two sessions with the same character name, removed before and after the test."""
    await Database.init()
    await _clear(SCRATCH_SESSION)
    await _clear(OTHER_SESSION)
    subject = await _make_session(SCRATCH_SESSION, f'["{REVIEW_TRAIT}"]')
    other = await _make_session(OTHER_SESSION, f'["{REVIEW_TRAIT}"]')
    try:
        yield {"session": SCRATCH_SESSION, "other": OTHER_SESSION,
               "subject": subject, "other_subject": other}
    finally:
        await Database.execute("DELETE FROM maya_rp.ooc_rules WHERE session_id=$1", SCRATCH_SESSION)
        await _clear(SCRATCH_SESSION)
        await _clear(OTHER_SESSION)
        await Database.close()


class TestASnapshotAppliesWhatItSaves:
    """The docstring names four things; the body wrote two and counted four."""

    def _snapshot(self, fixture: dict, rule_id: str, when: str) -> dict:
        return {
            "version": 1,
            "session_id": fixture["session"],
            "state": {"arc_stage": "selective", "deviation": 12, "roleplay_points": 40,
                      "audits": 3, "findings": 1, "debuff": "Neural Tremor"},
            "milestones": [{"name": "review-beat", "completed_at": when}],
            "exemptions": [{"rule_id": rule_id, "action_key": "review_action", "condition": None,
                            "cost_rpp": 20, "permanent": True, "expires_at": None}],
            "suspicion": [{"observer_id": fixture["subject"], "suspicion": 33,
                           "last_reason": "review"}],
        }

    async def test_exemptions_and_suspicion_are_written(self, scratch_session):
        rule_id = await Database.fetchval(
            "SELECT id FROM maya_rp.ooc_rules WHERE enabled ORDER BY id LIMIT 1")
        applied = await campaign.restore_snapshot(
            self._snapshot(scratch_session, rule_id, "2026-01-02T03:04:05+00:00"))
        assert applied["exemptions"] == 1 and applied["suspicion"] == 1
        exemption = await Database.fetchrow(
            "SELECT rule_id, action_key, cost_rpp FROM maya_rp.ooc_exemptions WHERE session_id=$1",
            SCRATCH_SESSION)
        assert (exemption["rule_id"], exemption["action_key"], exemption["cost_rpp"]) == (
            rule_id, "review_action", 20)
        assert await Database.fetchval(
            "SELECT suspicion FROM maya_rp.ooc_suspicion WHERE session_id=$1", SCRATCH_SESSION) == 33

    async def test_a_milestone_the_target_does_not_have_is_not_counted(self, scratch_session):
        rule_id = await Database.fetchval(
            "SELECT id FROM maya_rp.ooc_rules WHERE enabled ORDER BY id LIMIT 1")
        applied = await campaign.restore_snapshot(
            self._snapshot(scratch_session, rule_id, "2026-01-02T03:04:05+00:00"))
        assert applied["milestones"] == 0, "no row carried that beat, so none was restored"

    async def test_the_counts_are_what_was_applied(self, scratch_session):
        rule_id = await Database.fetchval(
            "SELECT id FROM maya_rp.ooc_rules WHERE enabled ORDER BY id LIMIT 1")
        fixture = scratch_session
        await Database.execute(
            "INSERT INTO maya_rp.ooc_milestones (session_id, name, stage) VALUES ($1,'review-beat','selective')",
            SCRATCH_SESSION)
        applied = await campaign.restore_snapshot(
            self._snapshot(fixture, rule_id, "2026-01-02T03:04:05+00:00"))
        assert applied["milestones"] == 1
        assert await Database.fetchval(
            "SELECT completed_at FROM maya_rp.ooc_milestones WHERE session_id=$1 AND name='review-beat'",
            SCRATCH_SESSION) == datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


class TestASnapshotSurvivesItsOwnFile:
    """`save_snapshot` writes JSON, so the timestamps come back as text."""

    async def test_a_saved_snapshot_restores_with_its_completion(self, scratch_session, tmp_path):
        """`cli.py ooc snapshot save` then `load` raised DataError on the first completed beat."""
        await Database.execute(
            "INSERT INTO maya_rp.ooc_milestones (session_id, name, stage, completed_at)"
            " VALUES ($1,'review-beat','selective','2026-01-02T03:04:05+00:00')",
            SCRATCH_SESSION,
        )
        data = await campaign.snapshot(SCRATCH_SESSION)
        path = campaign.save_snapshot(data, tmp_path / "act.json")
        loaded = campaign.load_snapshot(path)
        assert isinstance(loaded["milestones"][0]["completed_at"], str), "JSON turned it into text"

        await Database.execute(
            "UPDATE maya_rp.ooc_milestones SET completed_at=NULL WHERE session_id=$1 AND name='review-beat'",
            SCRATCH_SESSION)
        applied = await campaign.restore_snapshot(loaded)
        assert applied["milestones"] == 1
        assert await Database.fetchval(
            "SELECT completed_at FROM maya_rp.ooc_milestones WHERE session_id=$1 AND name='review-beat'",
            SCRATCH_SESSION) == datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    async def test_an_unreadable_timestamp_is_refused_by_name(self, scratch_session):
        with pytest.raises(ValueError, match="unreadable timestamp 'not a date'"):
            await campaign.restore_snapshot({
                "session_id": SCRATCH_SESSION,
                "milestones": [{"name": "review-beat", "completed_at": "not a date"}],
            })


class TestTheRulesASessionLivesUnder:
    """`effective_rules` documents the cascade; `character_rules` read the table whole."""

    @staticmethod
    async def _insert(rule_id: str, session_id: int | None) -> None:
        """A rule carrying the review trait, scoped to one session or to the campaign."""
        await Database.execute(
            "INSERT INTO maya_rp.ooc_rules (id, scope, session_id, trait, kind, pattern, delta)"
            " VALUES ($1,$2,$3,$4,'modern_phrasing','review-never-matches',1)",
            rule_id, "session" if session_id is not None else "campaign", session_id, REVIEW_TRAIT,
        )

    async def test_a_rule_of_another_campaign_stays_out(self, scratch_session):
        mine_id = f"review-mine-{os.getpid()}"
        theirs_id = f"review-theirs-{os.getpid()}"
        shared_id = f"review-campaign-{os.getpid()}"
        await self._insert(mine_id, SCRATCH_SESSION)
        await self._insert(theirs_id, scratch_session["other"])
        await self._insert(shared_id, None)
        try:
            mine = {rule["id"] for rule in
                    (await campaign.character_rules(SCRATCH_SESSION, SUBJECT))["rules"]}
            assert mine_id in mine, "a session's own rule must reach it"
            assert shared_id in mine, "the campaign-scope rows are shared and must not be filtered out"
            assert theirs_id not in mine, (
                "another campaign's session-scoped rule coloured this scene")
        finally:
            await Database.execute(
                "DELETE FROM maya_rp.ooc_rules WHERE id = ANY($1::text[])",
                [mine_id, theirs_id, shared_id],
            )


class TestTheSinksAndTheLadder:
    """Two tables that have to agree with two branch lists."""

    async def test_a_priced_sink_with_no_branch_is_refused(self, scratch_session, monkeypatch):
        await Database.execute(
            "INSERT INTO maya_rp.ooc_system_state (session_id, roleplay_points) VALUES ($1,100)"
            " ON CONFLICT (session_id) DO UPDATE SET roleplay_points=100",
            SCRATCH_SESSION,
        )
        monkeypatch.setitem(campaign.SPEND_PRICES, "review_sink", 5)
        with pytest.raises(ValueError, match="has a price but no branch"):
            await campaign.spend(SCRATCH_SESSION, "review_sink")

    async def test_the_three_priced_sinks_are_the_three_branches(self):
        assert set(campaign.SPEND_PRICES) == {"skip_beat", "calm_observer", "reveal_intel"}

    def test_every_debuff_the_ladder_can_raise_has_effects(self):
        """The ladder lives in core/ooc.py and the mapping here: a rename in one breaks the other."""
        assert set(campaign.DEBUFF_EFFECTS) == {name for _key, name, _effect in ooc.DEBUFF_LADDER}

    def test_an_ending_that_fires_is_stamped_in_its_own_session(self):
        """The statement carries the session; the id it is given comes from a scoped read."""
        source = inspect.getsource(campaign.triggered_endings)
        assert "session_id=$2" in source and "WHERE id=$1" in source


class TestEveryCampaignWriterRefusesAFrozenCampaign:
    """`ooc.py` writers refused a frozen campaign; the campaign layer did not.

    Before the fix `add_directive`, `spend`, `learn`, `restore_snapshot`, `portraits.queue`
    and the CLI's raw `milestone add` SQL each wrote into a reference-only campaign, so the
    guard that `audit` and `set_stage` honour was open on six other doors. Each test asserts
    the refusal AND that no row moved, because a guard placed after the write would raise
    and still have written.

    The freeze is simulated by patching `core.session.is_frozen`; the real
    `~/.config/rp-engine/frozen_sessions` is never touched.
    """

    @pytest.fixture()
    def frozen(self, monkeypatch):
        import core.session as session_mod

        monkeypatch.setattr(session_mod, "is_frozen", lambda sid: True)
        monkeypatch.setattr(ooc, "_maintenance_active", lambda: False)
        return True

    async def _count(self, table: str) -> int:
        return int(await Database.fetchval(
            f"SELECT count(*) FROM maya_rp.{table} WHERE session_id=$1", SCRATCH_SESSION))

    async def test_add_directive_is_refused_and_writes_nothing(self, scratch_session, frozen):
        """Pre-fix: the note was inserted into the frozen campaign."""
        with pytest.raises(ooc.FrozenSession):
            await campaign.add_directive(SCRATCH_SESSION, "a note")
        assert await self._count("ooc_directives") == 0, "a refused note must not be stored"

    async def test_spend_is_refused_and_keeps_the_balance(self, scratch_session, frozen):
        """Pre-fix: reveal_intel recorded a note and debited the points."""
        await Database.execute(
            "UPDATE maya_rp.ooc_system_state SET roleplay_points=100 WHERE session_id=$1", SCRATCH_SESSION)
        with pytest.raises(ooc.FrozenSession):
            await campaign.spend(SCRATCH_SESSION, "reveal_intel", "who holds the key")
        balance = await Database.fetchval(
            "SELECT roleplay_points FROM maya_rp.ooc_system_state WHERE session_id=$1", SCRATCH_SESSION)
        assert balance == 100, "a refused spend must not debit the crown"
        assert await self._count("ooc_directives") == 0, "a refused spend must not record intel"

    async def test_learn_is_refused_and_writes_nothing(self, scratch_session, frozen):
        """Pre-fix: the fact was upserted into the frozen campaign's ledger."""
        with pytest.raises(ooc.FrozenSession):
            await campaign.learn(SCRATCH_SESSION, scratch_session["subject"], "a-fact")
        assert await self._count("character_knowledge") == 0, "a refused fact must not be stored"

    async def test_restore_snapshot_is_refused_by_the_session_the_file_names(self, scratch_session, frozen):
        """Pre-fix: the file's state overwrote the frozen session's numbers."""
        data = {"session_id": SCRATCH_SESSION,
                "state": {"arc_stage": "selective", "roleplay_points": 77},
                "milestones": [], "exemptions": [], "suspicion": []}
        with pytest.raises(ooc.FrozenSession):
            await campaign.restore_snapshot(data)
        row = await Database.fetchrow(
            "SELECT arc_stage, roleplay_points FROM maya_rp.ooc_system_state WHERE session_id=$1",
            SCRATCH_SESSION)
        assert (row["arc_stage"], row["roleplay_points"]) == ("lockdown", 0), "state must be untouched"

    async def test_portrait_queue_is_refused_and_writes_nothing(self, scratch_session, frozen):
        """Pre-fix: a pending render row was inserted for the frozen campaign."""
        from core import portraits

        with pytest.raises(ooc.FrozenSession):
            await portraits.queue(SCRATCH_SESSION, SUBJECT, "portrait")
        assert await self._count("character_assets") == 0, "a refused queue must not leave a row"

    async def test_add_milestone_is_refused_and_writes_no_beat_or_rule(self, scratch_session, frozen):
        """Pre-fix: the CLI ran the upserts itself, bypassing core and the guard."""
        with pytest.raises(ooc.FrozenSession):
            await ooc.add_milestone(SCRATCH_SESSION, "frozen-beat", pattern="re:x")
        assert await self._count("ooc_milestones") == 0, "a refused beat must not be stored"
        assert await self._count("ooc_rules") == 0, "a refused beat must not author its rule"

    async def test_arming_maintenance_lets_a_write_through(self, scratch_session, monkeypatch):
        """The refusal must not close the documented way in."""
        import core.session as session_mod

        monkeypatch.setattr(session_mod, "is_frozen", lambda sid: True)
        monkeypatch.setattr(ooc, "_maintenance_active", lambda: True)
        row = await campaign.add_directive(SCRATCH_SESSION, "maintenance note")
        assert row["note"] == "maintenance note"
        assert await self._count("ooc_directives") == 1
        await ooc.add_milestone(SCRATCH_SESSION, "maint-beat", pattern="re:x")
        assert await self._count("ooc_milestones") == 1
