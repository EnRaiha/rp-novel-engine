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
        assert any("not JSON" in message for message in said), said
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
