"""Tests for core/ooc.py — the OOC engine (engine plane).

Pure halves (layer split, rule evaluation, awards, ladder) run without a
database; the state/cascade/provenance trio runs against the live ledger on a
scratch session that the fixture removes afterwards.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from core.db import Database  # noqa: E402
from core.ooc import (  # noqa: E402
    LAYER_BOTH,
    LAYER_DIALOGUE,
    LAYER_SOMATIC,
    LAYER_TOOL,
    OocRule,
    audit_text,
    compile_rule,
    debuff_for,
    loophole_score,
    rpp_award,
    split_layers,
)

SOMATIC_RULE = OocRule("somatic-cry", "somatic_lock", "re:(tears|crying)", 8, LAYER_SOMATIC)
DIALOGUE_RULE = OocRule("modern-slip", "modern_phrasing", "re:(okay|ok|hey)", 4, LAYER_DIALOGUE)
BOTH_RULE = OocRule("any-slip", "modern_phrasing", "wanna", 2, LAYER_BOTH)
SCRATCH_SESSION = 999


class TestLayerSplit:
    """§2 — determinism without an LLM deciding what a rule may see."""

    def test_splits_plain_quotes(self):
        layers = split_layers('Her shoulders drop. "I am fine," she says.')
        assert "I am fine" in layers[LAYER_DIALOGUE]
        assert "shoulders" in layers[LAYER_SOMATIC]
        assert "I am fine" not in layers[LAYER_SOMATIC]

    def test_splits_smart_quotes_and_cjk_brackets(self):
        layers = split_layers("She nods. “Proceed.” He bows. 「Yes, my King.」")
        assert "Proceed." in layers[LAYER_DIALOGUE]
        assert "Yes, my King." in layers[LAYER_DIALOGUE]
        assert "Proceed." not in layers[LAYER_SOMATIC]

    def test_contraction_stays_somatic(self):
        layers = split_layers("Sera's grip tightens on the rail.")
        assert layers[LAYER_DIALOGUE] == ""
        assert "Sera's grip" in layers[LAYER_SOMATIC]

    def test_empty_text(self):
        assert split_layers("") == {LAYER_SOMATIC: "", LAYER_DIALOGUE: ""}


class TestRuleSurfaces:
    """The two false-positive directions the split exists to kill."""

    def test_somatic_rule_ignores_quoted_token(self):
        findings = audit_text('She holds the rail steady. "Stop crying, soldier."', [SOMATIC_RULE], LAYER_DIALOGUE)
        assert findings == []

    def test_somatic_rule_fires_on_narration(self):
        findings = audit_text('Tears streak her cheek. "Report ready."', [SOMATIC_RULE], LAYER_DIALOGUE)
        assert [f.rule_id for f in findings] == ["somatic-cry"]
        assert findings[0].layer == LAYER_SOMATIC

    def test_dialogue_rule_ignores_narration(self):
        findings = audit_text("She shrugs, okay with the plan.", [DIALOGUE_RULE], LAYER_DIALOGUE)
        assert findings == []

    def test_dialogue_rule_fires_on_quoted_token(self):
        findings = audit_text('She nods slowly. "Okay. Proceed."', [DIALOGUE_RULE], LAYER_DIALOGUE)
        assert [f.rule_id for f in findings] == ["modern-slip"]
        assert findings[0].layer == LAYER_DIALOGUE

    def test_tool_text_still_reaches_prose_rules(self):
        findings = audit_text("Proceed when it is okay with you", [DIALOGUE_RULE], LAYER_TOOL)
        assert [f.rule_id for f in findings] == ["modern-slip"]
        assert findings[0].layer == LAYER_TOOL

    def test_tool_authored_rule_never_polices_prose(self):
        tool_rule = OocRule("tool-slip", "modern_phrasing", "wanna", 2, "tool")
        assert audit_text('She wanna go. "I wanna go."', [tool_rule], LAYER_DIALOGUE) == []

    def test_both_rule_sees_every_surface(self):
        assert audit_text('"I wanna go."', [BOTH_RULE], LAYER_DIALOGUE)
        assert audit_text("She wanna go.", [BOTH_RULE], LAYER_DIALOGUE)


class TestCompileBounds:
    """R1 — a pattern compiles once and cannot backtrack without a bound."""

    def test_compile_is_cached(self):
        assert compile_rule(SOMATIC_RULE) is compile_rule(SOMATIC_RULE)

    def test_nested_quantifier_rejected(self):
        with pytest.raises(ValueError):
            compile_rule(OocRule("bad", "modern_phrasing", "re:(a+)+b", 5, LAYER_BOTH))

    def test_bad_pattern_is_inert_not_fatal(self):
        findings = audit_text("aaaaaab", [OocRule("bad", "modern_phrasing", "re:(a+)+b", 5, LAYER_BOTH)], LAYER_DIALOGUE)
        assert findings == []

    def test_word_boundaries_hold(self):
        rule = OocRule("gun", "forbidden_lexicon", "gun", 8, LAYER_BOTH)
        assert audit_text("the gun fired", [rule], LAYER_SOMATIC)
        assert audit_text("it had begun", [rule], LAYER_SOMATIC) == []


class TestAwards:
    """D4 / O1 — a lexical score alone is farmable, so action evidence is required."""

    def test_clean_protective_text_earns_with_evidence(self):
        award, score = rpp_award("Reroute the medical escort and reinforce the guard.", [], action_evidence=True)
        assert score >= 40
        assert award == 1

    def test_no_evidence_no_award(self):
        award, score = rpp_award("Reroute the medical escort and reinforce the guard.", [], action_evidence=False)
        assert score >= 40
        assert award == 0

    def test_findings_cancel_award(self):
        findings = audit_text('"I am fine," she says.', [DIALOGUE_RULE], LAYER_DIALOGUE)
        award, score = rpp_award("I am fine", findings, action_evidence=True)
        assert (award, score) == (0, 0)

    def test_scoring_is_bounded(self):
        assert 0 <= loophole_score("protect " * 50) <= 100
        assert loophole_score("I love you, protect you") == 0


class TestLadder:
    """§7 — thresholds are per stage, not global config."""

    @staticmethod
    def name_at(deviation: int, stage: str) -> str | None:
        active = debuff_for(deviation, stage)
        return active[0] if active else None

    def test_lockdown_is_stricter_than_selective(self):
        assert self.name_at(30, "lockdown") == "Neural Tremor"
        assert self.name_at(30, "selective") is None

    def test_top_rungs(self):
        assert self.name_at(60, "lockdown") == "Meridian Lock"
        assert self.name_at(80, "lockdown") == "System Reclamation"
        assert self.name_at(100, "confrontation") == "System Reclamation"

    def test_below_warning_no_penalty(self):
        assert debuff_for(0, "lockdown") is None


# Order matters: exemptions reference rules, suspicion references characters.
_SCRATCH_CLEANUP = (
    "DELETE FROM maya_rp.ooc_audit_events WHERE session_id=$1",
    "DELETE FROM maya_rp.ooc_exemptions WHERE session_id=$1",
    "DELETE FROM maya_rp.ooc_milestones WHERE session_id=$1",
    "DELETE FROM maya_rp.ooc_suspicion WHERE session_id=$1",
    "DELETE FROM maya_rp.events WHERE session_id=$1",
    "DELETE FROM maya_rp.objectives WHERE session_id=$1",
    "DELETE FROM maya_rp.ooc_directives WHERE session_id=$1",
    "DELETE FROM maya_rp.ships WHERE session_id=$1",
    "DELETE FROM maya_rp.ooc_endings WHERE session_id=$1",
    "DELETE FROM maya_rp.ooc_lorebook WHERE session_id=$1",
    "DELETE FROM maya_rp.ooc_rules WHERE session_id=$1",
    "DELETE FROM maya_rp.characters WHERE session_id=$1 AND name='Scratch Observer'",
    "DELETE FROM maya_rp.ooc_system_state WHERE session_id=$1",
    "DELETE FROM maya_rp.social_events WHERE session_id=$1",
    "DELETE FROM maya_rp.sessions WHERE id=$1",
)


@pytest.fixture()
async def scratch_session():
    """A disposable session row in the live ledger, removed afterwards.

    The harness mirror is redirected to a temp file, so a test never touches the
    state the running plugin reads.
    """
    from core.db import Database
    from core import ooc

    await Database.init()
    previous_state_file = os.environ.get("OOC_STATE_FILE")
    state_file = Path(tempfile.mkdtemp()) / "tkg-state.json"
    os.environ["OOC_STATE_FILE"] = str(state_file)
    # Reset the scratch row first: a leftover deviation from an earlier run would
    # make `deviation == delta` assertions depend on test order.
    for statement in _SCRATCH_CLEANUP:
        await Database.execute(statement, SCRATCH_SESSION)
    await ooc.state(SCRATCH_SESSION)
    # A character row needs a session to hang from, and the suspicion meter is
    # keyed to a character, so the scratch session needs both.
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1,'OOC test session','active')"
        " ON CONFLICT (id) DO NOTHING",
        SCRATCH_SESSION,
    )
    observer = await Database.fetchval(
        "INSERT INTO maya_rp.characters (session_id, name, status, bond, romance_flag)"
        " VALUES ($1,'Scratch Observer','active',50,true) RETURNING id",
        SCRATCH_SESSION,
    )
    try:
        yield {"session": SCRATCH_SESSION, "observer": int(observer), "state_file": state_file}
    finally:
        for statement in _SCRATCH_CLEANUP:
            await Database.execute(statement, SCRATCH_SESSION)
        if previous_state_file is None:
            os.environ.pop("OOC_STATE_FILE", None)
        else:
            os.environ["OOC_STATE_FILE"] = previous_state_file


class TestLedger:
    """D2/D3 — cascade, provenance, and decay against the real store."""

    async def test_campaign_cascade_includes_persona_traits(self, scratch_session):
        from core import ooc

        rules = await ooc.effective_rules(SCRATCH_SESSION, ("aloof",))
        ids = {rule.id for rule in rules}
        assert "gen-emotive-love" in ids       # campaign floor
        assert "aloof-somatic-tears" in ids    # the persona's own rule
        assert "tyrant-apology" not in ids     # another trait's rule stays out

    async def test_audit_records_provenance_without_prose(self, scratch_session):
        from core import ooc

        result = await ooc.audit('Tears streak her cheek. "I am fine."', SCRATCH_SESSION, traits=("aloof",), turn_ref="test")
        assert result["findings"], "expected the seeded rules to flag this text"
        assert result["deviation"] == result["delta"]
        assert result["disposition"] == "flagged"
        rows = await Database.fetch(
            "SELECT rule_id, layer, disposition, match_sha256, match_len FROM maya_rp.ooc_audit_events"
            " WHERE session_id=$1 ORDER BY id DESC LIMIT 1",
            SCRATCH_SESSION,
        )
        latest = rows[0]
        assert latest["match_sha256"] and len(latest["match_sha256"]) == 64
        assert latest["match_len"] > 0
        assert "Tears" not in str(latest)

    async def test_clean_audit_decays_at_selective(self, scratch_session):
        from core import ooc

        await ooc.set_stage(SCRATCH_SESSION, "selective")
        try:
            await ooc.audit('"I am fine."', SCRATCH_SESSION, traits=("aloof",))
            before = (await ooc.state(SCRATCH_SESSION))["deviation"]
            assert before > 0
            await ooc.audit("Quiet assessment of the ledger.", SCRATCH_SESSION, traits=("aloof",))
            after = (await ooc.state(SCRATCH_SESSION))["deviation"]
            assert after == max(0, before - 2), "selective stage decays 2 deviation per clean turn"
        finally:
            await ooc.set_stage(SCRATCH_SESSION, "lockdown")

    async def test_set_stage_rejects_unknown(self, scratch_session):
        from core import ooc

        with pytest.raises(ValueError):
            await ooc.set_stage(SCRATCH_SESSION, "anarchy")


class TestActionEvidence:
    """D4 — §5/O1: a point needs an action behind the words, never words alone."""

    def test_phase_slip_alone_earns_nothing(self):
        award, score = rpp_award("Shield the escort under standing order.", [], action_evidence=False)
        assert award == 0
        assert score >= 40, "the lexical score is high — evidence is what is missing"

    async def test_only_a_companion_id_counts_as_evidence(self):
        from core import ooc

        ids = await ooc.companion_ids(3)
        assert ids, "session 3 should have companions on record"
        assert await ooc.evidence_from_actions(3, [{"tool": "assign", "args": {"character_id": ids[0]}}])
        assert not await ooc.evidence_from_actions(3, [{"tool": "assign", "args": {"character_id": 987654}}])
        assert not await ooc.evidence_from_actions(3, [])


class TestBeats:
    """D4 — a scripted beat is paid once, and only when it is proven."""

    async def _author(self, name: str = "scratch-beat", reward: int = 5) -> None:
        await Database.execute(
            "INSERT INTO maya_rp.ooc_rules"
            " (id, scope, session_id, trait, kind, layer, pattern, is_regex, delta)"
            " VALUES ($1,'session',$2,NULL,'scripted_beat','both',$3,true,1)"
            " ON CONFLICT (id) DO UPDATE SET pattern=EXCLUDED.pattern",
            f"beat:{name}",
            SCRATCH_SESSION,
            r"re:(kneels|holds the line)",
        )
        await Database.execute(
            "INSERT INTO maya_rp.ooc_milestones (session_id, name, trait, stage, rpp_reward)"
            " VALUES ($1,$2,NULL,'lockdown',$3)"
            " ON CONFLICT (session_id, name) DO UPDATE SET rpp_reward=EXCLUDED.rpp_reward",
            SCRATCH_SESSION,
            name,
            reward,
        )

    async def test_beat_needs_the_prose_and_pays_once(self, scratch_session):
        from core import ooc

        await self._author()
        missed = await ooc.complete_milestone(SCRATCH_SESSION, "scratch-beat", text="She walks away.")
        assert missed["ok"] is False and missed["reason"] == "beat_not_met"
        hit = await ooc.complete_milestone(
            SCRATCH_SESSION, "scratch-beat", text="She kneels and holds the line."
        )
        assert hit["ok"] is True and hit["rpp_reward"] == 5
        assert (await ooc.state(SCRATCH_SESSION))["roleplay_points"] == 5
        again = await ooc.complete_milestone(SCRATCH_SESSION, "scratch-beat", text="She kneels.")
        assert again["ok"] is False and again["reason"] == "already_completed"

    async def test_beat_without_a_rule_needs_action_evidence(self, scratch_session):
        from core import ooc

        await Database.execute(
            "INSERT INTO maya_rp.ooc_milestones (session_id, name, trait, stage, rpp_reward)"
            " VALUES ($1,'scratch-unprovable',NULL,'lockdown',3)"
            " ON CONFLICT (session_id, name) DO UPDATE SET rpp_reward=3",
            SCRATCH_SESSION,
        )
        refused = await ooc.complete_milestone(SCRATCH_SESSION, "scratch-unprovable")
        assert refused["ok"] is False and refused["reason"] == "no_action_evidence"
        declared = await ooc.complete_milestone(SCRATCH_SESSION, "scratch-unprovable", evidence=True)
        assert declared["ok"] is True and declared["rpp_reward"] == 3

    async def test_beat_from_another_stage_is_inert(self, scratch_session):
        from core import ooc

        await self._author(name="scratch-later", reward=2)
        await Database.execute(
            "UPDATE maya_rp.ooc_milestones SET stage='confrontation' WHERE session_id=$1 AND name='scratch-later'",
            SCRATCH_SESSION,
        )
        result = await ooc.complete_milestone(SCRATCH_SESSION, "scratch-later", text="She kneels.")
        assert result["ok"] is False and result["reason"] == "wrong_stage"


class TestExemption:
    """D5 — roleplay points buy silence for one rule, and nothing else."""

    async def test_buying_silences_that_rule_only(self, scratch_session):
        from core import ooc

        await Database.execute(
            "UPDATE maya_rp.ooc_system_state SET roleplay_points=10 WHERE session_id=$1",
            SCRATCH_SESSION,
        )
        bought = await ooc.buy_exemption(SCRATCH_SESSION, "gen-modern-slip", "gentle_touch", 4)
        assert bought["ok"] is True and bought["roleplay_points"] == 6
        result = await ooc.audit("That is okay for now.", SCRATCH_SESSION, traits=("general",), turn_ref="test")
        assert result["disposition"] == "exempt"
        assert result["delta"] == 0 and result["deviation"] == 0
        assert result["exempted"][0]["rule_id"] == "gen-modern-slip"
        assert await ooc.live_exemptions(SCRATCH_SESSION) == {"gen-modern-slip": "gentle_touch"}

    async def test_condition_scopes_the_exemption(self, scratch_session):
        from core import ooc

        await Database.execute(
            "UPDATE maya_rp.ooc_system_state SET roleplay_points=10 WHERE session_id=$1",
            SCRATCH_SESSION,
        )
        await ooc.buy_exemption(
            SCRATCH_SESSION, "gen-modern-slip", "private_words", 1, condition="scene:medical"
        )
        outside = await ooc.audit("That is okay.", SCRATCH_SESSION, context={"scene": "bridge"})
        assert outside["disposition"] == "flagged"
        inside = await ooc.audit("That is okay.", SCRATCH_SESSION, context={"scene": "medical"})
        assert inside["disposition"] == "exempt"

    async def test_insufficient_points_refuse_loudly(self, scratch_session):
        from core import ooc

        refused = await ooc.buy_exemption(SCRATCH_SESSION, "gen-modern-slip", "too_expensive", 99)
        assert refused["ok"] is False and refused["reason"] == "insufficient_rpp"

    async def test_unknown_rule_is_refused(self, scratch_session):
        from core import ooc

        refused = await ooc.buy_exemption(SCRATCH_SESSION, "no-such-rule", "gentle_touch", 1)
        assert refused["ok"] is False and refused["reason"] == "unknown_rule"


class TestSuspicion:
    """D6 — the observer's slower meter: micro-inconsistency in, no penalty out."""

    async def test_hiding_a_micro_slip_raises_suspicion(self, scratch_session):
        from core import ooc

        first = await ooc.audit("That is okay.", SCRATCH_SESSION, traits=("general",), turn_ref="t1")
        assert first["findings"] and first["delta"] <= ooc.SUSPICION_MICRO_MAX
        second = await ooc.audit("The order stands.", SCRATCH_SESSION, traits=("general",), turn_ref="t2")
        assert second["suspicion_delta"] == ooc.SUSPICION_MU
        assert (second["suspicion_reason"] or "").startswith("micro_consistency")
        rows = await ooc.suspicion(SCRATCH_SESSION)
        assert rows and rows[0]["observer_id"] == scratch_session["observer"]
        assert rows[0]["suspicion"] == ooc.SUSPICION_MU

    async def test_a_clean_turn_lets_the_observer_relax(self, scratch_session):
        from core import ooc

        await Database.execute(
            "INSERT INTO maya_rp.ooc_suspicion (session_id, observer_id, suspicion, last_reason)"
            " VALUES ($1,$2,10,'earlier lapse')",
            SCRATCH_SESSION,
            scratch_session["observer"],
        )
        result = await ooc.audit("The order stands.", SCRATCH_SESSION, traits=("general",), turn_ref="t")
        assert result["suspicion_delta"] == -ooc.SUSPICION_MU_DECAY
        assert result["suspicion_reason"] is None


class TestSuspicionConsumers:
    """§6.1 — `social`/`council` read the meter and never write it (one-way read)."""

    async def _suspicion_row(self, observer: int) -> dict | None:
        row = await Database.fetchrow(
            "SELECT session_id, observer_id, suspicion, last_reason, last_event_id, updated_at"
            " FROM maya_rp.ooc_suspicion WHERE session_id=$1 AND observer_id=$2",
            SCRATCH_SESSION,
            observer,
        )
        return dict(row) if row else None

    async def _seed_meter(self, observer: int, value: int) -> None:
        await Database.execute(
            "INSERT INTO maya_rp.ooc_suspicion (session_id, observer_id, suspicion, last_reason)"
            " VALUES ($1,$2,$3,'earlier lapse')"
            " ON CONFLICT (session_id, observer_id) DO UPDATE SET suspicion=EXCLUDED.suspicion",
            SCRATCH_SESSION,
            observer,
            value,
        )

    async def test_social_event_probes_without_writing(self, scratch_session):
        from modules import social

        await self._seed_meter(scratch_session["observer"], 60)
        before = await self._suspicion_row(scratch_session["observer"])
        event = await social.generate_social_event(
            SCRATCH_SESSION, "gossip", companions=["Scratch Observer"]
        )
        after = await self._suspicion_row(scratch_session["observer"])
        assert before == after, "the consumer must not write ooc_suspicion"
        assert event["suspicion"]["band"] == "probing"
        probes = [beat for beat in event["beats"] if beat["type"] == "observer_probe"]
        assert probes and probes[0]["speaker"] == "Scratch Observer"
        assert probes[0]["line"] == social.SUSPICION_PROBE_LINES["probing"]

    async def test_social_event_without_suspicion_adds_no_probe(self, scratch_session):
        from modules import social

        event = await social.generate_social_event(
            SCRATCH_SESSION, "gossip", companions=["Scratch Observer"]
        )
        assert event["suspicion"]["band"] == "unaware"
        assert not [beat for beat in event["beats"] if beat["type"] == "observer_probe"]

    async def test_council_tick_reads_without_writing(self, scratch_session):
        from modules import council

        await self._seed_meter(scratch_session["observer"], 60)
        before = await self._suspicion_row(scratch_session["observer"])
        result = await council.run_tick(SCRATCH_SESSION)
        after = await self._suspicion_row(scratch_session["observer"])
        assert before == after, "the consumer must not write ooc_suspicion"
        assert result["observer_suspicion"]["band"] == "probing"
        assert result["notice"] == council.SUSPICION_NOTICES["probing"]

    def test_band_boundaries(self):
        from core import ooc

        assert ooc.suspicion_band(0) == "unaware"
        assert ooc.suspicion_band(24) == "unaware"
        assert ooc.suspicion_band(25) == "watchful"
        assert ooc.suspicion_band(59) == "watchful"
        assert ooc.suspicion_band(60) == "probing"
        assert ooc.suspicion_band(90) == "certain"


async def campaign_learn(session_id, observer, fact):
    """Small helper so tests do not import the campaign module twice."""
    from core import campaign

    return await campaign.learn(session_id, observer, fact, "test")


async def _author_scratch_beat(
    name: str,
    *,
    trait: str | None = None,
    latch: str | None = None,
    reward: int = 5,
    pattern: str = r"re:(kneels|holds the line)",
) -> None:
    """Author one scratch beat (paired rule + milestone) on the scratch session."""
    await Database.execute(
        "INSERT INTO maya_rp.ooc_rules"
        " (id, scope, session_id, trait, kind, layer, pattern, is_regex, delta)"
        " VALUES ($1,'session',$2,$3,'scripted_beat','both',$4,true,1)"
        " ON CONFLICT (id) DO UPDATE SET trait=EXCLUDED.trait, pattern=EXCLUDED.pattern",
        f"beat:{name}",
        SCRATCH_SESSION,
        trait,
        pattern,
    )
    await Database.execute(
        "INSERT INTO maya_rp.ooc_milestones (session_id, name, trait, stage, rpp_reward, latch_ruleset)"
        " VALUES ($1,$2,$3,'lockdown',$4,$5)"
        " ON CONFLICT (session_id, name) DO UPDATE SET rpp_reward=EXCLUDED.rpp_reward,"
        " latch_ruleset=EXCLUDED.latch_ruleset",
        SCRATCH_SESSION,
        name,
        trait,
        reward,
        latch,
    )


class TestBeatsFromProse:
    """§6.3 — the narrator's prose proves a scripted beat; no manual call."""

    async def test_seeded_shape_beat_rule_resolves_in_its_stage(self, scratch_session):
        from core import ooc

        # F1 regression: a beat authored with a persona trait (the seeded shape)
        # must resolve; before the fix `trait` was read as a stage and it never did.
        await _author_scratch_beat("scratch-trait-beat", trait="aloof")
        rules = {rule.id for rule in await ooc.effective_rules(SCRATCH_SESSION, ("aloof",))}
        assert "beat:scratch-trait-beat" in rules
        await Database.execute(
            "UPDATE maya_rp.ooc_milestones SET stage='confrontation'"
            " WHERE session_id=$1 AND name='scratch-trait-beat'",
            SCRATCH_SESSION,
        )
        rules = {rule.id for rule in await ooc.effective_rules(SCRATCH_SESSION, ("aloof",))}
        assert "beat:scratch-trait-beat" not in rules, "another stage's beat stays inert"

    async def test_beats_from_prose_completes_and_pays(self, scratch_session):
        from core import ooc

        await _author_scratch_beat("scratch-prose-beat")
        completed = await ooc.beats_from_prose(
            SCRATCH_SESSION, "She kneels and holds the line.", traits=("aloof",)
        )
        assert [beat["name"] for beat in completed] == ["scratch-prose-beat"]
        assert completed[0]["rpp_reward"] == 5
        row = await Database.fetchrow(
            "SELECT completed_at FROM maya_rp.ooc_milestones"
            " WHERE session_id=$1 AND name='scratch-prose-beat'",
            SCRATCH_SESSION,
        )
        assert row["completed_at"] is not None
        assert (await ooc.state(SCRATCH_SESSION))["roleplay_points"] == 5

    async def test_audit_turn_completes_the_beat(self, scratch_session):
        from core import ooc

        await _author_scratch_beat("scratch-audit-beat")
        result = await ooc.audit(
            "She kneels before the throne.", SCRATCH_SESSION, traits=("aloof",), turn_ref="t-beat"
        )
        assert [beat["name"] for beat in result["beats_completed"]] == ["scratch-audit-beat"]
        assert result["state"]["roleplay_points"] == 5

    async def test_preview_turn_never_completes_a_beat(self, scratch_session):
        from core import ooc

        await _author_scratch_beat("scratch-preview-beat")
        result = await ooc.audit(
            "She kneels before the throne.", SCRATCH_SESSION, traits=("aloof",), preview=True
        )
        assert result["beats_completed"] == []
        row = await Database.fetchrow(
            "SELECT completed_at FROM maya_rp.ooc_milestones"
            " WHERE session_id=$1 AND name='scratch-preview-beat'",
            SCRATCH_SESSION,
        )
        assert row["completed_at"] is None

    async def test_tool_turn_never_completes_a_beat(self, scratch_session):
        from core import ooc

        await _author_scratch_beat("scratch-tool-beat")
        result = await ooc.audit(
            "She kneels and holds the line.",
            SCRATCH_SESSION,
            layer=ooc.LAYER_TOOL,
            traits=("aloof",),
            turn_ref="tool",
        )
        assert result["beats_completed"] == []

    async def test_unpaired_beat_is_not_proven_by_prose(self, scratch_session):
        from core import ooc

        await Database.execute(
            "INSERT INTO maya_rp.ooc_milestones (session_id, name, trait, stage, rpp_reward)"
            " VALUES ($1,'scratch-unpaired',NULL,'lockdown',3)",
            SCRATCH_SESSION,
        )
        assert await ooc.beats_from_prose(SCRATCH_SESSION, "She kneels.", traits=("aloof",)) == []
        declared = await ooc.complete_milestone(SCRATCH_SESSION, "scratch-unpaired", evidence=True)
        assert declared["ok"] is True, "a beat with no paired rule still needs action evidence"


class TestLatchAndOverdue:
    """§6.2 — a fired beat latches its ruleset; a required beat reports its expiry."""

    async def test_latch_ruleset_stays_on_after_the_beat_fires(self, scratch_session):
        from core import ooc

        before = {rule.id for rule in await ooc.effective_rules(SCRATCH_SESSION, ("general",))}
        assert "tyrant-apology" not in before
        await _author_scratch_beat("scratch-latch-beat", latch="tyrant")
        completed = await ooc.beats_from_prose(SCRATCH_SESSION, "She kneels.", traits=("aloof",))
        assert completed and completed[0]["latched_ruleset"] == "tyrant"
        after = {rule.id for rule in await ooc.effective_rules(SCRATCH_SESSION, ("general",))}
        assert "tyrant-apology" in after, "the latched ruleset must stay on"

    async def test_required_beat_overdue_is_queryable(self, scratch_session):
        from core import ooc

        await Database.execute(
            "INSERT INTO maya_rp.ooc_milestones (session_id, name, trait, stage, required, expires_at)"
            " VALUES ($1,'scratch-required',NULL,'lockdown',true, now() - interval '1 hour')",
            SCRATCH_SESSION,
        )
        await Database.execute(
            "INSERT INTO maya_rp.ooc_milestones (session_id, name, trait, stage, required, expires_at)"
            " VALUES ($1,'scratch-on-time',NULL,'lockdown',true, now() + interval '1 day')",
            SCRATCH_SESSION,
        )
        overdue = await ooc.overdue_milestones(SCRATCH_SESSION, traits=("general",))
        assert [beat["name"] for beat in overdue] == ["scratch-required"]
        listed = {beat["name"]: beat for beat in await ooc.milestones(SCRATCH_SESSION, traits=("general",))}
        assert listed["scratch-required"]["overdue"] is True
        assert listed["scratch-on-time"]["overdue"] is False


class TestPortraits:
    """Fasa 5 — the portrait pipeline: sheet -> prompt -> asset -> lookup."""

    def test_slug_and_prompt(self):
        from core import portraits

        assert portraits.slugify("Maya al-Dabaran (Anchor)") == "maya-al-dabaran-anchor"
        assert portraits.slugify("") == "unknown"
        prompt = portraits.build_prompt(
            {"name": "Maya", "role": "Adjutant", "appearance": "amber eyes, dark hair"},
            "flustered",
            sheet="# Maya\n\n## Profile\n\n- **Designation**: Adjutant-01",
        )
        assert "Maya" in prompt and "faint blush" in prompt
        assert "#" not in prompt, "sheet markdown is flattened for the renderer"

    async def test_queue_then_lookup(self, scratch_session, tmp_path):
        from core import portraits

        queued = await portraits.queue(SCRATCH_SESSION, "Scratch Observer", "romance")
        assert queued["emotion"] == "flustered"
        row = await Database.fetchrow(
            "SELECT status FROM maya_rp.character_assets WHERE id=$1", queued["asset_id"]
        )
        assert row["status"] == "pending"
        # A pending asset is not an answer.
        assert await portraits.lookup(SCRATCH_SESSION, "Scratch Observer", "romance") is None

        image = tmp_path / "flustered.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n")
        await portraits.mark_ready(queued["asset_id"], str(image), model="test", seed=None, width=8, height=8)
        hit = await portraits.lookup(SCRATCH_SESSION, "Scratch Observer", "romance")
        assert hit is not None
        assert hit["asset"]["image_path"] == str(image)
        assert hit["emotion"] == "flustered"

    async def test_unknown_character_raises(self, scratch_session):
        from core import portraits

        with pytest.raises(ValueError):
            await portraits.queue(SCRATCH_SESSION, "Nobody Here", "portrait")


class TestPersona:
    """Fasa 6 — the four persona fields, and what the model may see."""

    def _write(self, root, slug, field, text):
        from core import persona

        persona.ensure_dirs(slug)
        (persona.persona_dir(slug) / f"{field}.md").write_text(text, encoding="utf-8")

    def test_block_injects_voice_and_intro_only(self, tmp_path, monkeypatch):
        from core import persona

        monkeypatch.setattr(persona, "PERSONA_ROOT", tmp_path)
        self._write(tmp_path, "king", "voice", "# King — Voice\n\n## Register rules\n- clipped\n")
        self._write(tmp_path, "king", "intro", "Open mid-decision.")
        self._write(tmp_path, "king", "lore", "SECRET-BACKSTORY")
        self._write(tmp_path, "king", "play-guide", "SECRET-PLAY-GUIDE")

        block = persona.build_block("king")

        assert "clipped" in block and "Open mid-decision." in block
        assert "SECRET-BACKSTORY" not in block, "lore is routed through the lorebook, not the persona block"
        assert "SECRET-PLAY-GUIDE" not in block, "the play guide never reaches the model"

    def test_boundary_cases_are_parsed(self, tmp_path, monkeypatch):
        from core import persona

        monkeypatch.setattr(persona, "PERSONA_ROOT", tmp_path)
        self._write(
            tmp_path,
            "king",
            "voice",
            "# Voice\n\n## Boundary\n\n- player offers warmth => answer stays clipped\n- modern slang => refused\n\n## Other\n- ignored\n",
        )
        cases = persona.boundary_cases("king")
        assert cases == ["player offers warmth => answer stays clipped", "modern slang => refused"]

    def test_scaffold_never_overwrites(self, tmp_path, monkeypatch):
        from core import persona

        monkeypatch.setattr(persona, "PERSONA_ROOT", tmp_path)
        persona.scaffold("nethara", display_name="Nethara")
        voice = persona.field_path("nethara", "voice")
        voice.write_text("HAND-WRITTEN", encoding="utf-8")
        persona.scaffold("nethara", display_name="Nethara")
        assert voice.read_text(encoding="utf-8") == "HAND-WRITTEN"


class TestContextBlocks:
    """Fasa 6 — M1/M3/M25: the blocks injected before the player's turn."""

    async def test_blocks_render_from_live_data(self, scratch_session, tmp_path, monkeypatch):
        from core import context

        story = tmp_path / "story.md"
        story.write_text("# Brief\n\n[CORE PREMISE & WORLD]\nTest world.", encoding="utf-8")
        monkeypatch.setattr(context, "STORY_PATH", story)
        await Database.execute(
            "INSERT INTO maya_rp.events (session_id, event_type, title, importance)"
            " VALUES ($1,'player_action','A queen lives',5)",
            SCRATCH_SESSION,
        )
        await Database.execute(
            "INSERT INTO maya_rp.objectives (session_id, title, objective_type, status, priority)"
            " VALUES ($1,'Secure the corridor','test','active',1)",
            SCRATCH_SESSION,
        )

        data = await context.build_context(SCRATCH_SESSION)
        text = data["text"]

        assert "Test world." in data["story"]
        assert "[RECENT EVENTS]" in text and "A queen lives" in text
        assert "[RELATIONSHIPS]" in text and "Scratch Observer" in text
        assert "[CURRENT GOAL]" in text and "Secure the corridor" in text
        assert "[SCENE]" in text

    async def test_system_block_carries_due_beats(self, scratch_session):
        from core import context

        await _author_scratch_beat("scratch-context-beat")
        data = await context.build_context(SCRATCH_SESSION, traits=("aloof",))
        assert "[SYSTEM]" in data["text"]
        assert "scratch-context-beat" in data["text"], "the turn sees which beats are due"

    async def test_noise_events_are_filtered(self, scratch_session, monkeypatch):
        from core import context

        await Database.execute(
            "INSERT INTO maya_rp.events (session_id, event_type, title, importance)"
            " VALUES ($1,'policy','POLICY NOISE',9), ($1,'player_action','quiet event',1)",
            SCRATCH_SESSION,
        )
        events = await context.recent_events(SCRATCH_SESSION)
        titles = [event["title"] for event in events]
        assert "POLICY NOISE" not in titles, "engine chatter stays out of the chronicle block"
        assert "quiet event" not in titles, "below the importance floor"


class TestCampaignLayer:
    """Fasa 6 B3 — stage windows, lorebook, endings, snapshots, observers."""

    async def test_stage_window_filters_rules(self, scratch_session):
        from core import ooc

        await Database.execute(
            "INSERT INTO maya_rp.ooc_rules (id, scope, session_id, kind, layer, pattern, delta, min_stage)"
            " VALUES ('scratch-late-rule','session',$1,'modern_phrasing','dialogue','re:(indeed)',3,'selective')"
            " ON CONFLICT (id) DO UPDATE SET min_stage='selective'",
            SCRATCH_SESSION,
        )
        lockdown = {rule.id for rule in await ooc.effective_rules(SCRATCH_SESSION, ("general",), "lockdown")}
        selective = {rule.id for rule in await ooc.effective_rules(SCRATCH_SESSION, ("general",), "selective")}
        assert "scratch-late-rule" not in lockdown, "the rule opens only at selective"
        assert "scratch-late-rule" in selective

    async def test_dead_companions_are_not_evidence(self, scratch_session):
        from core import ooc

        assert scratch_session["observer"] in await ooc.companion_ids(SCRATCH_SESSION)
        await Database.execute(
            "UPDATE maya_rp.characters SET status='dead' WHERE id=$1", scratch_session["observer"]
        )
        assert scratch_session["observer"] not in await ooc.companion_ids(SCRATCH_SESSION)
        await Database.execute(
            "UPDATE maya_rp.characters SET status='active' WHERE id=$1", scratch_session["observer"]
        )

    async def test_present_observers_are_returned(self, scratch_session):
        from core import ooc

        await Database.execute(
            "UPDATE maya_rp.characters SET presence='present' WHERE id=$1", scratch_session["observer"]
        )
        observers = await ooc.observer_ids(SCRATCH_SESSION)
        assert scratch_session["observer"] in observers
        await Database.execute(
            "UPDATE maya_rp.characters SET presence=NULL WHERE id=$1", scratch_session["observer"]
        )
        assert await ooc.observer_ids(SCRATCH_SESSION) == [await ooc.observer_id(SCRATCH_SESSION)]

    async def test_lorebook_matches_keywords(self, scratch_session):
        from core import campaign

        await Database.execute(
            "INSERT INTO maya_rp.ooc_lorebook (session_id, keywords, title, content)"
            " VALUES ($1, ARRAY['lantern','wreck'], 'The Lantern', 'A beacon that answers only the crown.')",
            SCRATCH_SESSION,
        )
        entries = await campaign.lore_entries(SCRATCH_SESSION)
        assert campaign.lore_for("the lantern answers", entries), "keyword present -> entry triggers"
        assert not campaign.lore_for("nothing relevant here", entries)
        block = campaign.render_lore(campaign.lore_for("the lantern answers", entries))
        assert "[LORE]" in block and "The Lantern" in block

    async def test_ending_conditions_and_near_hints(self):
        from core import campaign

        values = {"deviation": 82, "roleplay_points": 10, "suspicion_max": 30}
        assert campaign.condition_met({"stat": "deviation", "op": ">=", "value": 80}, values)
        assert not campaign.condition_met({"stat": "deviation", "op": ">=", "value": 100}, values)
        near = campaign.near_endings(
            [{"name": "Reclamation", "condition": {"stat": "deviation", "op": ">=", "value": 100}, "met": False}],
            values,
        )
        assert near and "Reclamation" in near[0]

    async def test_snapshot_round_trip(self, scratch_session, tmp_path):
        from core import campaign

        await Database.execute(
            "UPDATE maya_rp.ooc_system_state SET deviation=12, roleplay_points=7 WHERE session_id=$1",
            SCRATCH_SESSION,
        )
        data = await campaign.snapshot(SCRATCH_SESSION)
        assert data["state"]["deviation"] == 12
        path = campaign.save_snapshot(data, tmp_path / "snap.json")
        loaded = campaign.load_snapshot(path)
        result = await campaign.restore_snapshot(loaded)
        assert result["ok"] is True

    async def test_spend_sinks_move_state(self, scratch_session):
        from core import campaign

        await Database.execute(
            "UPDATE maya_rp.ooc_system_state SET roleplay_points=40 WHERE session_id=$1", SCRATCH_SESSION
        )
        await _author_scratch_beat("scratch-skip-me")
        row = await campaign.spend(SCRATCH_SESSION, "skip_beat", "scratch-skip-me")
        assert row["price"] == campaign.SPEND_PRICES["skip_beat"]
        balance = await Database.fetchval(
            "SELECT roleplay_points FROM maya_rp.ooc_system_state WHERE session_id=$1", SCRATCH_SESSION
        )
        assert balance == 40 - row["price"], "the price is actually deducted"
        with pytest.raises(ValueError):
            await campaign.spend(SCRATCH_SESSION, "teleport", None)

    async def test_debuff_effects_map(self, scratch_session):
        from core import campaign

        fx = await campaign.debuff_effects(SCRATCH_SESSION)
        assert fx["debuff"] is None and fx["battle_penalty"] == 0
        await Database.execute(
            "UPDATE maya_rp.ooc_system_state SET debuff='Meridian Lock' WHERE session_id=$1", SCRATCH_SESSION
        )
        fx = await campaign.debuff_effects(SCRATCH_SESSION)
        assert fx["romance_blocked"] is True and fx["battle_penalty"] == 3

    async def test_knowledge_ledger(self, scratch_session):
        from core import campaign

        await campaign.learn(SCRATCH_SESSION, scratch_session["observer"], "the queen lives", "scene")
        facts = await campaign.knowledge_of(SCRATCH_SESSION, scratch_session["observer"])
        assert [fact["fact_key"] for fact in facts] == ["the queen lives"]

    async def test_character_rules_by_trait(self, scratch_session):
        from core import campaign

        await Database.execute(
            "UPDATE maya_rp.characters SET traits=$2::jsonb WHERE id=$1",
            scratch_session["observer"],
            json.dumps(["aloof", "loyal"]),
        )
        found = await campaign.character_rules(SCRATCH_SESSION, "Scratch Observer")
        assert "aloof" in found["traits"]
        assert all(row["kind"] for row in found["rules"])

    async def test_knowledge_rule_flags_the_uninformed(self, scratch_session):
        from core import ooc

        await Database.execute(
            "INSERT INTO maya_rp.ooc_rules (id, scope, session_id, kind, layer, pattern, is_regex, delta)"
            " VALUES ('fact:scratch_fact','session',$1,'knowledge','both','re:the vault opened',true,1)"
            " ON CONFLICT (id) DO UPDATE SET enabled=true",
            SCRATCH_SESSION,
        )
        rules = [rule for rule in await ooc.effective_rules(SCRATCH_SESSION, ("general",)) if rule.kind == "knowledge"]
        assert rules, "the knowledge rule resolves"
        leaked = await ooc.knowledge_findings(SCRATCH_SESSION, "The vault opened that night.", rules, "both")
        assert [finding.rule_id for finding in leaked] == ["fact:scratch_fact"]

        await campaign_learn(SCRATCH_SESSION, scratch_session["observer"], "scratch_fact")
        quiet = await ooc.knowledge_findings(SCRATCH_SESSION, "The vault opened that night.", rules, "both")
        assert quiet == [], "a watcher who knows the fact stops the leak"

    async def test_debuff_reaches_battle_and_romance(self, scratch_session):
        from modules import battle, romance

        await Database.execute("DELETE FROM maya_rp.ships WHERE session_id=$1", SCRATCH_SESSION)
        for index in range(5):
            await Database.execute(
                "INSERT INTO maya_rp.ships (session_id, name, status) VALUES ($1,$2,'active')",
                SCRATCH_SESSION,
                f"Scratch Hull {index + 1}",
            )
        await Database.execute(
            "UPDATE maya_rp.ooc_system_state SET debuff='Meridian Lock' WHERE session_id=$1", SCRATCH_SESSION
        )
        outcome = await battle.resolve_intent(SCRATCH_SESSION, "attack", "the target")
        assert outcome["debuff_battle_penalty"] == 3
        assert outcome["player_power_effective"] >= 1
        assert "Meridian Lock" in outcome["narrative_hook"]

        blocked = await romance.advance_bond(scratch_session["observer"], 1, SCRATCH_SESSION)
        assert blocked.get("blocked_by") == "Meridian Lock"

    async def test_director_note_is_recorded(self, scratch_session):
        from core import campaign

        row = await campaign.add_directive(SCRATCH_SESSION, "keep the pace slow")
        assert row["id"]
        notes = await campaign.directives(SCRATCH_SESSION)
        assert notes and notes[0]["note"] == "keep the pace slow"


class TestStageGates:
    """D7 — the arc stage opens on gates, it is not a toggle."""

    async def test_advance_refuses_while_gates_are_unmet(self, scratch_session):
        from core import ooc

        readiness = await ooc.stage_readiness(SCRATCH_SESSION)
        assert readiness["next"] == "selective" and readiness["ready"] is False
        refused = await ooc.advance_stage(SCRATCH_SESSION, auto=True)
        assert refused["ok"] is False and refused["reason"] == "gates_unmet"
        with pytest.raises(ValueError):
            await ooc.advance_stage(SCRATCH_SESSION)

    async def test_advance_opens_once_a_beat_and_points_exist(self, scratch_session):
        from core import ooc

        await Database.execute(
            "UPDATE maya_rp.ooc_system_state SET roleplay_points=6 WHERE session_id=$1",
            SCRATCH_SESSION,
        )
        await Database.execute(
            "INSERT INTO maya_rp.ooc_milestones (session_id, name, trait, stage, rpp_reward, completed_at)"
            " VALUES ($1,'scratch-done',NULL,'lockdown',0,now())"
            " ON CONFLICT (session_id, name) DO UPDATE SET completed_at=now()",
            SCRATCH_SESSION,
        )
        moved = await ooc.advance_stage(SCRATCH_SESSION, auto=True)
        assert moved["ok"] is True and moved["stage"] == "selective"
        assert (await ooc.state(SCRATCH_SESSION))["arc_stage"] == "selective"


class TestBridge:
    """The seam itself (§13): one JSON request in, one JSON reply out."""

    async def _call(self, request: dict) -> tuple[dict, int]:
        import asyncio
        import json
        import sys as _sys

        root = Path(__file__).resolve().parent.parent
        process = await asyncio.create_subprocess_exec(
            _sys.executable,
            str(root / "scripts" / "ooc_bridge.py"),
            cwd=str(root),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        raw, _ = await process.communicate(json.dumps(request).encode())
        return json.loads(raw.decode() or "{}"), int(process.returncode or 0)

    async def test_state_call_answers_the_row(self, scratch_session):
        reply, code = await self._call({"call": "state", "session_id": SCRATCH_SESSION})
        assert code == 0 and reply["ok"] is True
        assert reply["state"]["session_id"] == SCRATCH_SESSION
        assert reply["state"]["arc_stage"] == "lockdown"

    async def test_preview_never_writes(self, scratch_session):
        from core import ooc

        reply, code = await self._call({
            "call": "turn",
            "session_id": SCRATCH_SESSION,
            "text": "That is okay.",
            "traits": ["general"],
            "preview": True,
        })
        assert code == 0 and reply["preview"] is True
        assert [finding["rule_id"] for finding in reply["findings"]] == ["gen-modern-slip"]
        state = await ooc.state(SCRATCH_SESSION)
        assert state["deviation"] == 0 and state["audits"] == 0

    async def test_canon_call_returns_observers_and_beats(self, scratch_session):
        reply, code = await self._call({"call": "canon", "session_id": SCRATCH_SESSION, "traits": ["aloof"]})
        assert code == 0 and reply["ok"] is True
        assert reply["observer_id"] == scratch_session["observer"]
        assert reply["companions"] == [scratch_session["observer"]]

    async def test_unknown_call_fails_loud(self, scratch_session):
        reply, code = await self._call({"call": "nope", "session_id": SCRATCH_SESSION})
        assert code == 1 and reply["ok"] is False and "unknown call" in reply["error"]


class TestMirror:
    """D7 phase 1 — the engine writes the JSON store the harness reads."""

    async def test_mirror_carries_state_into_the_harness_file(self, scratch_session):
        from core import ooc

        await Database.execute(
            "UPDATE maya_rp.ooc_system_state SET deviation=7, roleplay_points=3 WHERE session_id=$1",
            SCRATCH_SESSION,
        )
        path = await ooc.mirror_state_file(SCRATCH_SESSION)
        assert path == str(scratch_session["state_file"])
        entries = json.loads(Path(path).read_text())
        entry = next(item for item in entries if item["sessionId"] == SCRATCH_SESSION)
        assert entry["deviation"] == 7
        assert entry["roleplayPoints"] == 3
        assert entry["stage"] == "lockdown"
        assert entry["debuff"] is None

    async def test_mirror_keeps_other_sessions(self, scratch_session):
        from core import ooc

        path = Path(str(scratch_session["state_file"]))
        path.write_text(json.dumps([{"sessionId": 3, "deviation": 1}]))
        await ooc.mirror_state_file(SCRATCH_SESSION)
        entries = json.loads(path.read_text())
        assert {item["sessionId"] for item in entries} == {3, SCRATCH_SESSION}
