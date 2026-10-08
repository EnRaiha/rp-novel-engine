"""Module review: core/ooc.py, part one. The state reader, the gate, and a rule that cannot run.

`state()` was a read that wrote. Create-on-first-touch used
`ON CONFLICT (session_id) DO UPDATE SET updated_at=now()`, which fires on every call
once the row exists, so `updated_at` recorded the last time somebody looked rather
than the last thing that happened. That is the field the harness mirror publishes as
`updatedAt`, so it always read as fresh, and it is the one state reader in the module
with no frozen guard, which it only needed because it wrote.

The confrontation gate counted every exemption ever bought, expired ones included,
while `live_exemptions` filters by `permanent OR expires_at > now()`. The gate and the
ruleset disagreed about what the session holds.

`buy_exemption(permanent=False)` with no `ttl_hours` rendered the missing lifetime as
the string "0", so `expires_at` was `now()`: a purchase that cost roleplay points and
expired in the same instant, with nothing saying so.

`audit_text` swallowed a rule whose pattern would not compile. A clean turn is
supposed to mean the prose was clean, and an inert rule makes it mean nothing ran.

Every test runs in a scratch campaign derived from the process id, the pattern
tests/test_ooc.py uses, and every row it writes is removed in the fixture's finally.
The live arc and the frozen reference are never written.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

import asyncpg
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import ooc  # noqa: E402
from core.db import Database  # noqa: E402

SCRATCH_SESSION = 700 + (os.getpid() % 100)

CLEANUP = (
    "DELETE FROM maya_rp.ooc_suspicion WHERE session_id=$1",
    "DELETE FROM maya_rp.ooc_audit_events WHERE session_id=$1",
    "DELETE FROM maya_rp.ooc_exemptions WHERE session_id=$1",
    "DELETE FROM maya_rp.ooc_milestones WHERE session_id=$1",
    "DELETE FROM maya_rp.ooc_system_state WHERE session_id=$1",
)


async def _clear(session_id: int) -> None:
    for statement in CLEANUP:
        await Database.execute(statement, session_id)


@pytest.fixture()
async def scratch_session():
    """A disposable campaign row, removed afterwards."""
    await Database.init()
    await _clear(SCRATCH_SESSION)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day)"
        " VALUES ($1,'OOC module review','active',1)"
        " ON CONFLICT (id) DO UPDATE SET game_day=1",
        SCRATCH_SESSION,
    )
    try:
        yield SCRATCH_SESSION
    finally:
        await _clear(SCRATCH_SESSION)
        await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", SCRATCH_SESSION)
        await Database.close()


class TestTheStateReaderAndItsTimestamp:
    """Contract, not a fix: these three pass on the code before today's commit too.

    `state()` never wrote on a read of an existing session, and a mutation that
    restores the conflict branch leaves all three green. The claim that it did was
    withdrawn during the red proof, which is what the red proof is for.
    """

    async def test_reading_state_does_not_move_the_timestamp(self, scratch_session):
        first = await ooc.state(scratch_session)
        second = await ooc.state(scratch_session)
        assert first["updated_at"] == second["updated_at"], \
            "a read moved updated_at, so the mirror's updatedAt is the time of the last look"

    async def test_the_first_touch_still_creates_the_row(self, scratch_session):
        before = await Database.fetchval(
            "SELECT count(*) FROM maya_rp.ooc_system_state WHERE session_id=$1", scratch_session)
        assert before == 0, "the fixture should leave no state row"
        row = await ooc.state(scratch_session)
        assert row["session_id"] == scratch_session
        after = await Database.fetchval(
            "SELECT count(*) FROM maya_rp.ooc_system_state WHERE session_id=$1", scratch_session)
        assert after == 1

    async def test_a_real_write_does_move_the_timestamp(self, scratch_session):
        first = await ooc.state(scratch_session)
        await ooc.set_stage(scratch_session, "selective")
        second = await ooc.state(scratch_session)
        assert second["updated_at"] > first["updated_at"], "a write must move it"
        assert second["arc_stage"] == "selective"


class TestTheGateCountsWhatIsLive:
    """A gate satisfied by a purchase that ran out is not satisfied."""

    async def test_an_expired_exemption_does_not_open_the_gate(self, scratch_session):
        await ooc.state(scratch_session)
        await ooc.set_stage(scratch_session, "selective")
        await Database.execute(
            "UPDATE maya_rp.ooc_system_state SET roleplay_points=99 WHERE session_id=$1",
            scratch_session)
        # rule_id carries a foreign key to ooc_rules, so the purchases name real rules.
        rules = await Database.fetch(
            "SELECT id FROM maya_rp.ooc_rules ORDER BY id LIMIT 3")
        if len(rules) < 1:
            pytest.skip("no ooc_rules rows to exempt")
        # Two expired purchases and one live one. The gate is `exemptions >= 1`.
        for index, expires in enumerate(("now() - interval '2 hours'",
                                         "now() - interval '1 hour'",
                                         "now() + interval '1 hour'")):
            rule = rules[index % len(rules)]
            await Database.execute(
                "INSERT INTO maya_rp.ooc_exemptions"
                " (session_id, rule_id, action_key, cost_rpp, permanent, expires_at)"
                f" VALUES ($1,$2,$3,1,false,{expires})",
                scratch_session, rule["id"], f"review_action_{index}")

        total = await Database.fetchval(
            "SELECT count(*) FROM maya_rp.ooc_exemptions WHERE session_id=$1", scratch_session)
        assert total == 3, "the test wants three purchases on the table"

        readiness = await ooc.stage_readiness(scratch_session)
        assert readiness["next"] == "confrontation", readiness
        assert readiness["gates"]["exemptions"]["have"] == 1, \
            "the gate counted expired purchases, so a dead exemption opens it"


class TestAnExemptionNeedsALifetime:
    """`permanent=False` with no ttl wrote a row that was already expired."""

    async def test_a_temporary_exemption_without_a_ttl_is_refused(self):
        with pytest.raises(ValueError, match="ttl_hours"):
            await ooc.buy_exemption(SCRATCH_SESSION, "any-rule", "any_action", permanent=False)

    async def test_a_zero_ttl_is_refused_too(self):
        with pytest.raises(ValueError, match="ttl_hours"):
            await ooc.buy_exemption(SCRATCH_SESSION, "any-rule", "any_action",
                                    permanent=False, ttl_hours=0)

    async def test_a_temporary_exemption_with_a_ttl_is_still_allowed(self, scratch_session):
        """The refusal must not close the feature."""
        await ooc.state(scratch_session)
        await Database.execute(
            "UPDATE maya_rp.ooc_system_state SET roleplay_points=99 WHERE session_id=$1",
            scratch_session)
        rule = await Database.fetchrow(
            "SELECT id FROM maya_rp.ooc_rules WHERE enabled ORDER BY id LIMIT 1")
        if rule is None:
            pytest.skip("no enabled rule to exempt")
        out = await ooc.buy_exemption(scratch_session, rule["id"], "gentle_touch",
                                      permanent=False, ttl_hours=4)
        assert out["ok"] is True, out
        live = await ooc.live_exemptions(scratch_session)
        assert rule["id"] in live, "a four hour exemption must be live"


class TestARuleThatCannotRunIsReported:
    """A clean turn means the prose was clean, not that the rule never ran."""

    def _broken_rule(self):
        return ooc.OocRule(id="review-broken", kind="forbidden_lexicon",
                           pattern="re:(unclosed", delta=5, layer=ooc.LAYER_DIALOGUE,
                           is_regex=True)

    def test_an_uncompilable_rule_is_named_once(self, monkeypatch):
        said = []
        monkeypatch.setattr(ooc, "_BROKEN_RULES", set())
        monkeypatch.setattr(ooc, "error", lambda module, msg: said.append(msg))

        rule = self._broken_rule()
        # A dialogue rule is only compiled when there is dialogue to test, so the
        # text has to carry a quoted line or the rule is never reached.
        text = 'She looked away. "anything at all," she said.'
        assert ooc.audit_text(text, [rule]) == []
        assert ooc.audit_text(text, [rule]) == []
        assert len(said) == 1, f"expected one report, got {said}"
        assert "review-broken" in said[0], said[0]

    def test_a_working_rule_still_reports_normally(self, monkeypatch):
        monkeypatch.setattr(ooc, "_BROKEN_RULES", set())
        rule = ooc.OocRule(id="review-ok", kind="forbidden_lexicon", pattern="okay", delta=4)
        findings = ooc.audit_text('He said "okay" to that.', [rule])
        assert [f.rule_id for f in findings] == ["review-ok"]


class TestTheMirrorDoesNotTakeTheLedgerDown:
    """The mirror is a cache in front of the truth, and it runs after the commit.

    `entries.sort(key=lambda entry: int(entry.get("sessionId") or 0))` raised
    ValueError on any non-numeric key, in a file the engine does not own, while
    writing the mirror. `audit()` calls this after its transaction has committed, so
    the audit row was in the ledger and the caller was told the turn failed: the two
    planes disagree from then on, permanently.
    """

    @pytest.fixture()
    def mirror(self, tmp_path, monkeypatch):
        path = tmp_path / "ooc" / "tkg-state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("OOC_STATE_FILE", str(path))
        return path

    async def test_a_non_numeric_session_key_does_not_break_the_write(self, scratch_session, mirror):
        mirror.write_text(json.dumps([
            {"sessionId": "tkg-play", "deviation": 1},
            {"sessionId": 5, "deviation": 2},
        ]))
        written = await ooc.mirror_state_file(scratch_session)
        assert written is not None, "a stray key must not take the mirror down"
        entries = json.loads(mirror.read_text())
        keys = [entry["sessionId"] for entry in entries]
        assert scratch_session in keys, keys
        assert keys == sorted(keys, key=lambda k: (1, str(k)) if isinstance(k, str) else (0, k)), keys

    async def test_a_corrupt_mirror_is_rebuilt_and_reported(self, scratch_session, mirror, monkeypatch):
        said = []
        monkeypatch.setattr(ooc, "error", lambda module, msg: said.append(msg))
        mirror.write_text("{not json at all")
        written = await ooc.mirror_state_file(scratch_session)
        assert written is not None
        assert any("unusable" in message for message in said), said
        assert mirror.with_name(mirror.name + ".corrupt").exists(), "the corrupt file is kept once for repair"
        assert [entry["sessionId"] for entry in json.loads(mirror.read_text())] == [scratch_session]

    async def test_an_unwritable_mirror_is_reported_not_raised(self, scratch_session, tmp_path, monkeypatch):
        """The engine's own rows are committed by now, so this must not raise."""
        said = []
        monkeypatch.setattr(ooc, "error", lambda module, msg: said.append(msg))
        # A directory where the file should be: every write path fails.
        blocked = tmp_path / "blocked"
        blocked.mkdir()
        monkeypatch.setenv("OOC_STATE_FILE", str(blocked))
        assert await ooc.mirror_state_file(scratch_session) is None
        assert said, "a failed mirror must say so"

    async def test_a_successful_mirror_still_writes_the_entry(self, scratch_session, mirror):
        written = await ooc.mirror_state_file(scratch_session)
        assert written == str(mirror)
        entries = json.loads(mirror.read_text())
        assert entries[0]["sessionId"] == scratch_session
        assert entries[0]["stage"] == "lockdown"


class TestEveryWriterRefusesAFrozenCampaign:
    """`audit` refused writes into a frozen campaign. Four other writers did not.

    A frozen campaign is reference: readable at will, writable only with GM MAYA
    maintenance armed. `_refuse_frozen` was called on one path, so a stage change, a
    completed beat, a bought exemption and a suspicion bump could each edit the
    campaign that is supposed to be read-only.

    The freeze is simulated by patching `core.session.is_frozen`, so the real
    `~/.config/rp-engine/frozen_sessions` is never touched: three reviewers run this
    suite at once and none of them should see another's edit to that file.
    """

    @pytest.fixture()
    def frozen(self, monkeypatch):
        import core.session as session_mod

        monkeypatch.setattr(session_mod, "is_frozen", lambda sid: True)
        monkeypatch.setattr(ooc, "_maintenance_active", lambda: False)
        return True

    async def test_set_stage_is_refused(self, scratch_session, frozen):
        await ooc.state(scratch_session)  # the row must exist for the write to matter
        with pytest.raises(ooc.FrozenSession):
            await ooc.set_stage(scratch_session, "selective")

    async def test_complete_milestone_is_refused(self, scratch_session, frozen):
        with pytest.raises(ooc.FrozenSession):
            await ooc.complete_milestone(scratch_session, "any-beat")

    async def test_buy_exemption_is_refused(self, scratch_session, frozen):
        with pytest.raises(ooc.FrozenSession):
            await ooc.buy_exemption(scratch_session, "any-rule", "any_action")

    async def test_bump_suspicion_is_refused(self, scratch_session, frozen):
        with pytest.raises(ooc.FrozenSession):
            await ooc.bump_suspicion(scratch_session, observer=1, delta=5)

    async def test_reading_a_frozen_campaign_is_still_allowed(self, scratch_session, frozen):
        """The guard refuses writes, not reads."""
        row = await ooc.state(scratch_session)
        assert row["session_id"] == scratch_session
        assert await ooc.milestones(scratch_session) == []

    async def test_arming_maintenance_lets_the_write_through(self, scratch_session, monkeypatch):
        """The refusal must not close the documented way in."""
        import core.session as session_mod

        monkeypatch.setattr(session_mod, "is_frozen", lambda sid: True)
        monkeypatch.setattr(ooc, "_maintenance_active", lambda: True)
        await ooc.state(scratch_session)
        row = await ooc.set_stage(scratch_session, "selective")
        assert row["arc_stage"] == "selective"


class TestOneUnknownStageIsOneAnswer:
    """Four reads of a stage, three answers to an unknown name.

    `debuff_for` and the decay lookup in `audit` used the lockdown ladder, `stage_allows` allowed
    every rule, and `stage_readiness` raised a bare `list.index` ValueError that named nothing. A
    typo in a rule's `min_stage` changed which rules ran, and no line said so.
    """

    @staticmethod
    def _rule(**window) -> ooc.OocRule:
        return ooc.OocRule(id="review-window", kind="prose", pattern="x", delta=1, **window)

    def test_the_debuff_ladder_refuses_an_unknown_stage(self):
        with pytest.raises(ValueError, match="unknown arc stage 'lockdwon' in the stage debuff_for"):
            ooc.debuff_for(80, "lockdwon")

    def test_the_rule_window_refuses_an_unknown_stage(self):
        with pytest.raises(ValueError, match="unknown arc stage 'lockdwon' in the current stage"):
            ooc.stage_allows(self._rule(), "lockdwon")

    def test_a_rule_window_that_is_wrong_names_the_rule_and_the_field(self):
        with pytest.raises(ValueError, match="rule 'review-window' min_stage"):
            ooc.stage_allows(self._rule(min_stage="selectiv"), "lockdown")

    def test_a_known_window_still_opens_and_closes(self):
        opens = self._rule(min_stage="selective")
        assert ooc.stage_allows(opens, "lockdown") is False
        assert ooc.stage_allows(opens, "selective") is True
        assert ooc.stage_allows(opens, "confrontation") is True
        closes = self._rule(max_stage="lockdown")
        assert ooc.stage_allows(closes, "lockdown") is True
        assert ooc.stage_allows(closes, "selective") is False

    def test_the_ladder_still_reads_each_stage_differently(self):
        assert ooc.debuff_for(30, "lockdown")[0] == "Neural Tremor"
        assert ooc.debuff_for(30, "selective") is None
        assert ooc.debuff_for(80, "confrontation")[0] == "Meridian Lock"
        assert ooc.debuff_for(100, "confrontation")[0] == "System Reclamation"

    def test_the_stage_tables_name_the_same_three_stages(self):
        """One source of truth for the names; the refusal reads STAGE_ORDER."""
        assert set(ooc.STAGE_ORDER) == set(ooc.STAGE_THRESHOLDS) == set(ooc.STAGE_RANK)
        assert set(ooc.STAGE_GATES) <= set(ooc.STAGE_ORDER)

    async def test_the_readiness_reader_refuses_a_bad_stage_by_name(self, scratch_session, monkeypatch):
        async def bad_state(_sid):
            return {"arc_stage": "lockdwon", "deviation": 0}

        monkeypatch.setattr(ooc, "state", bad_state)
        with pytest.raises(ValueError, match="unknown arc stage 'lockdwon' in the session's arc_stage"):
            await ooc.stage_readiness(scratch_session)

    async def test_the_audit_refuses_a_bad_stage_before_it_writes(self, scratch_session, monkeypatch):
        """With no rules to window, the decay lookup is the stage read under test here."""
        async def bad_state(_sid):
            return {"arc_stage": "lockdwon", "deviation": 0, "roleplay_points": 0}

        async def no_rules(*_args, **_kwargs):
            return []

        monkeypatch.setattr(ooc, "state", bad_state)
        monkeypatch.setattr(ooc, "effective_rules", no_rules)
        with pytest.raises(ValueError, match="unknown arc stage 'lockdwon'.*use one of lockdown, selective, confrontation"):
            await ooc.audit("prose to audit", scratch_session, turn_ref="review")
        assert await Database.fetchval(
            "SELECT count(*) FROM maya_rp.ooc_audit_events WHERE session_id=$1", scratch_session) == 0


class TestTheLedgerNamesEveryRuleThatFired:
    """One row per turn is the design. Naming one of that turn's three rules is not.

    `ooc_audit_events.rule_id` carries a foreign key into `ooc_rules`, so the column can hold one
    rule id or NULL. The row therefore names a rule only when the turn fired exactly one, and the
    count of what fired stays where it already was: the deviation delta and `state.findings`.
    """

    @staticmethod
    def _finding(rule_id: str) -> ooc.OocFinding:
        return ooc.OocFinding(rule_id=rule_id, kind="prose", layer=ooc.LAYER_DIALOGUE,
                              match="matched prose", delta=1)

    @staticmethod
    async def _real_rules(limit: int) -> list[str]:
        """Ids that exist in `ooc_rules`: `rule_id` is a foreign key, so a made-up id cannot be stored."""
        rows = await Database.fetch(
            "SELECT id FROM maya_rp.ooc_rules WHERE enabled ORDER BY id LIMIT $1", limit)
        ids = [row["id"] for row in rows]
        assert len(ids) == limit, f"this test needs {limit} enabled rules, found {ids}"
        return ids

    @staticmethod
    def _last_row(session_id: int):
        return Database.fetchval(
            "SELECT rule_id FROM maya_rp.ooc_audit_events WHERE session_id=$1 ORDER BY id DESC LIMIT 1",
            session_id)

    async def test_a_turn_with_three_findings_counts_three_and_names_none(self, scratch_session, monkeypatch):
        fired = [self._finding(f"review-rule-{n}") for n in (1, 2, 3)]
        monkeypatch.setattr(ooc, "audit_text", lambda text, rules, layer: fired)
        result = await ooc.audit("prose to audit", scratch_session, turn_ref="review")
        assert [f["rule_id"] for f in result["findings"]] == [
            "review-rule-1", "review-rule-2", "review-rule-3"]
        assert result["deviation"] == 3, "all three findings were billed"
        assert result["state"]["findings"] == 3, "all three were counted"
        assert await self._last_row(scratch_session) is None, (
            "the row cannot name one of three rules as if it were the only one")

    async def test_a_single_finding_still_names_one_rule(self, scratch_session, monkeypatch):
        one = (await self._real_rules(1))[0]
        monkeypatch.setattr(ooc, "audit_text", lambda text, rules, layer: [self._finding(one)])
        await ooc.audit("prose to audit", scratch_session, turn_ref="review")
        assert await self._last_row(scratch_session) == one

    async def test_a_clean_turn_names_no_rule(self, scratch_session, monkeypatch):
        monkeypatch.setattr(ooc, "audit_text", lambda text, rules, layer: [])
        await ooc.audit("prose to audit", scratch_session, turn_ref="review")
        assert await self._last_row(scratch_session) is None

    async def test_one_rule_corrected_on_the_next_turn_still_reads_as_a_correction(
        self, scratch_session, monkeypatch
    ):
        first, second = await self._real_rules(2)
        monkeypatch.setattr(ooc, "audit_text", lambda text, rules, layer: [self._finding(first)])
        await ooc.audit("prose to audit", scratch_session, turn_ref="review")
        monkeypatch.setattr(ooc, "audit_text", lambda text, rules, layer: [self._finding(second)])
        returned = await ooc.audit("prose to audit", scratch_session, turn_ref="review")
        assert returned["suspicion_delta"] == ooc.SUSPICION_MU
        assert returned["suspicion_reason"] == f"micro_consistency:{first}"

    async def test_a_correction_counts_for_the_very_next_turn_only(self, scratch_session, monkeypatch):
        """Later clean turns find a newer event than the flagged one, so they relax instead."""
        (rule,) = await self._real_rules(1)
        observer = await Database.fetchval(
            "INSERT INTO maya_rp.characters (session_id, name, status)"
            " VALUES ($1, 'Review Observer', 'active') RETURNING id", scratch_session)

        async def stored() -> int:
            return await Database.fetchval(
                "SELECT suspicion FROM maya_rp.ooc_suspicion WHERE session_id=$1 AND observer_id=$2",
                scratch_session, observer)

        async def no_knowledge(*args):
            return []

        try:
            # A second finding from the knowledge rules would leave the ledger row with no rule id.
            monkeypatch.setattr(ooc, "knowledge_findings", no_knowledge)
            monkeypatch.setattr(ooc, "audit_text", lambda text, rules, layer: [self._finding(rule)])
            await ooc.audit("prose to audit", scratch_session, turn_ref="review")
            monkeypatch.setattr(ooc, "audit_text", lambda text, rules, layer: [])
            corrected = await ooc.audit("prose to audit", scratch_session, turn_ref="review")
            assert corrected["suspicion_delta"] == ooc.SUSPICION_MU
            assert corrected["suspicion_reason"] == f"micro_consistency:{rule}"
            assert await stored() == ooc.SUSPICION_MU
            for turn, expected in ((3, ooc.SUSPICION_MU - ooc.SUSPICION_MU_DECAY),
                                   (4, ooc.SUSPICION_MU - 2 * ooc.SUSPICION_MU_DECAY)):
                clean = await ooc.audit("prose to audit", scratch_session, turn_ref="review")
                assert clean["suspicion_delta"] == -ooc.SUSPICION_MU_DECAY, f"turn {turn} relaxes"
                assert clean["suspicion_reason"] is None, f"turn {turn} is not a correction"
                assert await stored() == expected, f"turn {turn} leaves the stored suspicion relaxed"
        finally:
            # Deleting the character cascades to its `ooc_suspicion` row.
            await Database.execute("DELETE FROM maya_rp.characters WHERE id=$1", observer)

    async def test_a_turn_with_several_rules_cannot_claim_a_correction(self, scratch_session, monkeypatch):
        """Before, the row named the first rule, so the second one re-firing still read as a fix."""
        first, second, third = await self._real_rules(3)
        monkeypatch.setattr(ooc, "audit_text",
                            lambda text, rules, layer: [self._finding(first), self._finding(second)])
        await ooc.audit("prose to audit", scratch_session, turn_ref="review")
        monkeypatch.setattr(ooc, "audit_text", lambda text, rules, layer: [self._finding(third)])
        returned = await ooc.audit("prose to audit", scratch_session, turn_ref="review")
        assert returned["suspicion_delta"] == 0, "the row named no rule, so nothing was shown corrected"


class TestAWriterThatFailsPartwayLeavesNothingBehind:
    """`audit`, `complete_milestone` and `buy_exemption` each write more than one row.

    The rows belong to one transaction only when every statement runs on the connection that
    transaction holds. A statement issued through the pool takes another connection and commits on
    its own, so a failure in a later statement cannot undo the earlier ones. Each test makes the
    later statement fail on a real constraint, so no schema change is needed, and then reads the
    rows the earlier statement touched.
    """

    @staticmethod
    async def _row(session_id: int):
        return await Database.fetchrow(
            "SELECT deviation, roleplay_points, audits, findings"
            " FROM maya_rp.ooc_system_state WHERE session_id=$1", session_id)

    async def test_an_audit_whose_ledger_row_is_refused_leaves_the_state_alone(
        self, scratch_session, monkeypatch
    ):
        """The ledger row names a rule that is not in `ooc_rules`, so its foreign key refuses it."""
        await ooc.state(scratch_session)
        before = dict(await self._row(scratch_session))
        unknown = ooc.OocFinding(rule_id="review-no-such-rule", kind="prose",
                                 layer=ooc.LAYER_DIALOGUE, match="matched prose", delta=1)
        monkeypatch.setattr(ooc, "audit_text", lambda text, rules, layer: [unknown])
        with pytest.raises(asyncpg.exceptions.ForeignKeyViolationError):
            await ooc.audit("prose to audit", scratch_session, turn_ref="review")
        assert dict(await self._row(scratch_session)) == before, \
            "the state update outlived the audit row that was refused"

    async def test_a_beat_whose_payment_overflows_is_not_marked_complete(self, scratch_session):
        """The reward added to the balance leaves the integer range, so the state update raises."""
        await ooc.state(scratch_session)
        await Database.execute(
            "UPDATE maya_rp.ooc_system_state SET roleplay_points=1 WHERE session_id=$1",
            scratch_session)
        await Database.execute(
            "INSERT INTO maya_rp.ooc_milestones (session_id, name, stage, rpp_reward)"
            " VALUES ($1,'review-atomic-beat','lockdown',2147483647)", scratch_session)
        with pytest.raises(asyncpg.exceptions.NumericValueOutOfRangeError):
            await ooc.complete_milestone(scratch_session, "review-atomic-beat", evidence=True)
        completed_at = await Database.fetchval(
            "SELECT completed_at FROM maya_rp.ooc_milestones WHERE session_id=$1 AND name=$2",
            scratch_session, "review-atomic-beat")
        assert completed_at is None, "the beat stayed marked complete although its payment failed"
        assert (await self._row(scratch_session))["roleplay_points"] == 1

    async def test_an_exemption_that_cannot_be_stored_does_not_move_the_balance(self, scratch_session):
        """A lifetime the interval cannot hold fails the insert after the debit, and the debit rolls back.

        The price is legal, so the balance check passes and `roleplay_points` is debited; only
        then does `now() + ('999999999999' || ' hours')::interval` overflow (SQLSTATE 22015) at
        the exemption INSERT. Before the transaction wrapped both writes, the points were gone
        with no exemption to show for them. (A negative price used to be the injection here,
        but it is now refused up front, see the next test.)
        """
        await ooc.state(scratch_session)
        await Database.execute(
            "UPDATE maya_rp.ooc_system_state SET roleplay_points=99 WHERE session_id=$1",
            scratch_session)
        rule = await Database.fetchrow("SELECT id FROM maya_rp.ooc_rules ORDER BY id LIMIT 1")
        assert rule is not None, "migration 114 seeds a rule, so there is always one to name"
        with pytest.raises(asyncpg.exceptions.IntervalFieldOverflowError):
            await ooc.buy_exemption(scratch_session, rule["id"], "review_action", cost_rpp=5,
                                    permanent=False, ttl_hours=999_999_999_999)
        assert (await self._row(scratch_session))["roleplay_points"] == 99, \
            "the balance moved although the exemption was never stored"
        assert await Database.fetchval(
            "SELECT count(*) FROM maya_rp.ooc_exemptions WHERE session_id=$1", scratch_session) == 0

    @pytest.mark.parametrize("price", [-5, 0])
    async def test_a_price_that_is_not_positive_is_refused_before_any_points_move(
            self, scratch_session, price):
        """A negative `cost_rpp` passed the balance check and `roleplay_points - price` minted points.

        The CHECK (cost_rpp > 0) on the table refused the insert, but the guard belongs before
        the debit: a price of zero or less is a caller bug, not a purchase.
        """
        await ooc.state(scratch_session)
        await Database.execute(
            "UPDATE maya_rp.ooc_system_state SET roleplay_points=99 WHERE session_id=$1",
            scratch_session)
        rule = await Database.fetchrow("SELECT id FROM maya_rp.ooc_rules ORDER BY id LIMIT 1")
        assert rule is not None, "migration 114 seeds a rule, so there is always one to name"
        with pytest.raises(ValueError, match="positive price"):
            await ooc.buy_exemption(scratch_session, rule["id"], "review_action", cost_rpp=price)
        assert (await self._row(scratch_session))["roleplay_points"] == 99, \
            f"a price of {price} moved the balance"
        assert await Database.fetchval(
            "SELECT count(*) FROM maya_rp.ooc_exemptions WHERE session_id=$1", scratch_session) == 0, \
            f"a price of {price} left an exemption row"


class TestTheSuiteNeverMirrorsIntoTheLiveStateFile:
    """The plugin reads `~/.dsh/ooc/tkg-state.json`; scratch sessions written there hid the live arc."""

    def test_the_state_file_is_a_temp_path_for_the_whole_run(self):
        path = ooc.state_file_path()
        assert path != pathlib.Path("~/.dsh/ooc/tkg-state.json").expanduser(), "the suite would write the live store"
        assert pathlib.Path(tempfile.gettempdir()) in path.parents, f"{path} is outside the temp directory"
