"""Stale-session sweep: briefing, master_briefing, decision_models, terms, pacing, player_profile,
memory, dramatic_structure.

`Config.SESSION_ID` is fixed at import. A long-lived tick or worker that fell back to it kept writing
into the campaign it started with after the active arc moved. Every default-session path now resolves
per call through `core.session.require_session(None)`; an explicit id, 0 included, is used as given.

Also pinned here, found in the same pass:

- the dashboard raised TypeError on one NULL resource column and replaced itself with "(unavailable)";
- the briefing's PRESENT list selected `status='active'`, not presence, and the choices query had no LIMIT;
- `check_transitions` never asked whether the current mode still held: combat and crisis flapped every
  tick and nothing returned to downtime;
- `policy_features` / `survival_features` read pickles that do not exist, so every feature was the
  constant `len({})` and the classifier answered one class for any input, labelled `ml:<group>`;
- `terms.paragraphs` glued a heading to the text under it and `_kind` dropped the obligation.

No database: every test drives a fake. Scratch ids 901 (stale process default) and 902 (the live arc).
"""
from __future__ import annotations

import pytest

from core import briefing, decision_models as dm, dramatic_structure, master_briefing, memory
from core import pacing, player_profile, terms
from core.config import Config

STALE, LIVE = 901, 902


class FakeDB:
    """Records every positional query argument; answers with empty results."""

    def __init__(self, fetchrow=None, fetchval=None, fetch=None):
        self.seen: list = []
        self._fetchrow = fetchrow
        self._fetchval = fetchval
        self._fetch = fetch

    async def init(self): ...
    async def close(self): ...

    def _note(self, sql, args):
        self.seen.append((sql, args))

    def _answer(self, handler, sql, args, default):
        return handler(sql, *args) if callable(handler) else default

    async def execute(self, sql, *args):
        self._note(sql, args)
        return "UPDATE 1"

    async def fetch(self, sql, *args):
        self._note(sql, args)
        return self._answer(self._fetch, sql, args, [])

    async def fetchrow(self, sql, *args):
        self._note(sql, args)
        return self._answer(self._fetchrow, sql, args, None)

    async def fetchval(self, sql, *args):
        self._note(sql, args)
        return self._answer(self._fetchval, sql, args, None)

    def ints(self) -> set[int]:
        return {a for _, args in self.seen for a in args if isinstance(a, int)}


@pytest.fixture
def stale(monkeypatch):
    """Process default frozen at 901 while the live arc (RP_SESSION) is 902."""
    monkeypatch.setattr(Config, "SESSION_ID", STALE)
    monkeypatch.setenv("RP_SESSION", str(LIVE))


def _install(monkeypatch, module, fake=None):
    fake = fake or FakeDB()
    monkeypatch.setattr(module, "Database", fake)
    return fake


async def _drive(coro):
    """Run a call whose downstream shape on empty data is not under test."""
    try:
        return await coro
    except Exception:  # noqa: BLE001 - only the session id the call queried with matters
        return None


def _assert_live(fake, name):
    ids = fake.ints()
    assert LIVE in ids, f"{name} did not query with the live arc {LIVE}; saw {sorted(ids)}"
    assert STALE not in ids, f"{name} fell back to the import-time Config.SESSION_ID {STALE}"


CASES = [
    ("pacing.get_mode", pacing, lambda: pacing.PacingDirector.get_mode()),
    ("pacing.transition", pacing, lambda: pacing.PacingDirector.transition("combat", "t")),
    ("pacing.check_transitions", pacing, lambda: pacing.PacingDirector.check_transitions()),
    ("pacing.adjust_tension", pacing, lambda: pacing.PacingDirector.adjust_tension(1)),
    ("pacing.increment", pacing, lambda: pacing.PacingDirector.increment()),
    ("pacing.run_tick", pacing, lambda: pacing.PacingDirector.run_tick()),
    ("player_profile.record", player_profile, lambda: player_profile.record("I kill the guard")),
    ("player_profile.get_profile", player_profile, lambda: player_profile.get_profile()),
    ("dramatic_structure.get_current_arc", dramatic_structure, lambda: dramatic_structure.get_current_arc()),
    ("dramatic_structure.advance_phase", dramatic_structure, lambda: dramatic_structure.advance_phase()),
    ("dramatic_structure.session_start", dramatic_structure, lambda: dramatic_structure.session_start()),
    ("terms.record", terms, lambda: terms.record(text="")),
    ("terms.open_terms", terms, lambda: terms.open_terms()),
    ("briefing.generate_briefing", briefing, lambda: briefing.generate_briefing()),
    ("decision_models.detect_pirate_group", dm, lambda: dm.detect_pirate_group(7)),
    ("decision_models.log_decision", dm, lambda: dm.log_decision(7, "m", {}, "x")),
]


class TestDefaultSessionResolvesPerCall:
    """Pre-fix: each default path read `Config.SESSION_ID` (901), so a worker started before the arc moved
    wrote into the old campaign."""

    @pytest.mark.parametrize("name,module,call", CASES, ids=[c[0] for c in CASES])
    async def test_omitted_id_follows_the_live_arc(self, stale, monkeypatch, name, module, call):
        """Pre-fix: the queries carried 901 although RP_SESSION named 902."""
        fake = _install(monkeypatch, module)
        await _drive(call())
        _assert_live(fake, name)

    async def test_memory_store_event_follows_the_live_arc(self, stale, monkeypatch):
        """Pre-fix: the vector UPDATE named session 901."""
        fake = _install(monkeypatch, memory)

        async def vec(text, keep_alive="30m"):
            return [0.0] * 768

        monkeypatch.setattr(memory, "_embed", vec)
        await _drive(memory.store_event(7, "t", "d"))
        _assert_live(fake, "memory.store_event")

    async def test_memory_recall_follows_the_live_arc(self, stale, monkeypatch):
        """Pre-fix: recall searched session 901's events."""
        fake = _install(monkeypatch, memory)

        async def vec(text, keep_alive="30m"):
            return [0.0] * 768

        monkeypatch.setattr(memory, "_embed", vec)
        await _drive(memory.recall("q"))
        _assert_live(fake, "memory.recall")

    async def test_master_briefing_generate_follows_the_live_arc(self, stale, monkeypatch):
        """Pre-fix: the first block was built for session 901."""
        _install(monkeypatch, master_briefing)
        got: list = []

        async def spy(session_id):
            got.append(session_id)
            raise RuntimeError("stop after the first block")

        monkeypatch.setattr(master_briefing, "_generate_ui_dashboard", spy)
        await _drive(master_briefing.generate())
        assert got == [LIVE], f"generate used {got}, expected [{LIVE}]"

    async def test_cmd_briefing_follows_the_live_arc(self, stale, monkeypatch):
        """Pre-fix: the CLI helper handed 901 to generate_briefing."""
        _install(monkeypatch, briefing)
        got: list = []

        async def spy(session_id=None):
            got.append(session_id)
            return {}

        monkeypatch.setattr(briefing, "generate_briefing", spy)
        await _drive(briefing.cmd_briefing())
        assert got == [LIVE], f"cmd_briefing used {got}, expected [{LIVE}]"


class TestExplicitIdIsUsedAsGiven:
    """An explicit id wins over the environment, 0 included; only None resolves."""

    async def test_explicit_zero_is_not_read_as_unset(self, stale, monkeypatch):
        """Pre-fix: `session_id or Config.SESSION_ID` turned 0 into 901."""
        fake = _install(monkeypatch, dm)
        await _drive(dm.detect_pirate_group(7, session_id=0))
        assert 0 in fake.ints(), "explicit session 0 was not used"
        assert STALE not in fake.ints() and LIVE not in fake.ints(), (
            "explicit session 0 was replaced by a default")

    async def test_log_decision_explicit_zero(self, stale, monkeypatch):
        """Pre-fix: log_decision wrote the row into 901 for session_id=0."""
        fake = _install(monkeypatch, dm)
        await _drive(dm.log_decision(7, "m", {}, "x", session_id=0))
        assert 0 in fake.ints()
        assert STALE not in fake.ints() and LIVE not in fake.ints()

    async def test_explicit_id_beats_the_environment(self, stale, monkeypatch):
        """An explicit id is never overridden by RP_SESSION."""
        fake = _install(monkeypatch, pacing)
        await _drive(pacing.PacingDirector.get_mode(903))
        assert 903 in fake.ints() and LIVE not in fake.ints()


class TestDashboardToleratesNullResources:
    async def test_one_null_column_does_not_blank_the_dashboard(self, monkeypatch):
        """Pre-fix: `f"{None:,}"` raised TypeError and the dashboard became "(unavailable)"."""
        def row(sql, *args):
            if "FROM maya_rp.resources" in sql:
                return {"credits": None, "alloys": 5, "fuel": None, "population": None}
            if "FROM maya_rp.ships" in sql:
                return {"count": 1, "avg_tier": 2.0}
            return None

        _install(monkeypatch, master_briefing, FakeDB(fetchrow=row, fetchval=lambda *a: 0))
        out = await master_briefing._generate_ui_dashboard(900)
        assert "(unavailable)" not in out, "a NULL resource replaced the whole dashboard"
        assert "Coffers : 0 Cr | 5 Al | 0 Fuel" in out, out
        assert "0 Souls" in out, out


class TestBriefingPresentAndChoices:
    async def test_present_list_filters_presence_and_choices_are_limited(self, monkeypatch):
        """Pre-fix: PRESENT selected every `status='active'` character, absent ones included, and the
        pending-choices query was unbounded."""
        def row(sql, *args):
            if "FROM maya_rp.sessions" in sql:
                return {"name": "n", "status": "active", "game_day": 1}
            return None

        fake = _install(monkeypatch, briefing, FakeDB(fetchrow=row))
        await _drive(briefing.generate_briefing(900))
        present = [s for s, _ in fake.seen if "FROM maya_rp.characters c" in s and "c.bond" in s and "LIMIT 10" in s]
        assert present, "PRESENT query not issued"
        assert "presence='present'" in present[0], "PRESENT list does not filter on presence"
        choices = [s for s, _ in fake.seen if "FROM maya_rp.choices" in s]
        assert choices and "LIMIT" in choices[0], "pending choices are unbounded"


class TestPacingTransitions:
    """Fake queries keyed on the table each CHECK_QUERIES entry reads."""

    @staticmethod
    def _db(mode, positive):
        def row(sql, *args):
            return {"mode": mode, "tension": 0, "scenes_in_mode": 3}

        def val(sql, *args):
            for table in positive:
                if table in sql:
                    return 1
            return 0

        return FakeDB(fetchrow=row, fetchval=val)

    async def test_combat_and_crisis_both_true_does_not_flap(self, monkeypatch):
        """Pre-fix: combat saw crisis positive and moved; crisis saw combat positive and moved back."""
        both = ("sieges", "narrative_hooks")
        _install(monkeypatch, pacing, self._db("crisis", both))
        assert await pacing.PacingDirector.check_transitions(900) is None, (
            "crisis (held, highest rank) must stay")
        _install(monkeypatch, pacing, self._db("combat", both))
        assert await pacing.PacingDirector.check_transitions(900) == "crisis", (
            "combat yields once, to the higher-ranked crisis")

    async def test_held_mode_ignores_lower_ranked_candidates(self, monkeypatch):
        """Pre-fix: crisis jumped to combat whenever a siege was active."""
        _install(monkeypatch, pacing, self._db("crisis", ("narrative_hooks", "sieges", "science_missions")))
        assert await pacing.PacingDirector.check_transitions(900) is None

    async def test_a_lapsed_detected_mode_decays_to_downtime(self, monkeypatch):
        """Pre-fix: with every query at zero the tick answered None and combat lasted for ever."""
        _install(monkeypatch, pacing, self._db("combat", ()))
        assert await pacing.PacingDirector.check_transitions(900) == "downtime"

    async def test_a_lapsed_mode_moves_to_the_matching_candidate_not_downtime(self, monkeypatch):
        """A mode whose condition ended still yields to a candidate that holds."""
        _install(monkeypatch, pacing, self._db("combat", ("science_missions",)))
        assert await pacing.PacingDirector.check_transitions(900) == "exploration"

    async def test_hand_set_modes_do_not_decay(self, monkeypatch):
        """Social has no query; decaying it would erase a mode the GM chose."""
        _install(monkeypatch, pacing, self._db("social", ()))
        assert await pacing.PacingDirector.check_transitions(900) is None


class _Clf:
    classes_ = ["DEATH", "LIVE"]

    def predict_proba(self, feats):
        import numpy as np
        return np.array([[0.2, 0.8]])


class TestPirateFeatureMaps:
    def test_features_vary_with_input_when_the_model_carries_its_maps(self, monkeypatch):
        """Pre-fix: the maps were read from pickles that do not exist, so both inputs encoded to the same
        constants."""
        model = {"clf": _Clf(), "action_map": {"a": 0, "b": 1, "c": 2}}
        monkeypatch.setitem(dm._cache, "pirate_survival_tree.pkl", model)
        assert dm.survival_features(0, 0.5, "a") != dm.survival_features(0, 0.5, "b"), (
            "survival features are constant across actions")
        pol = {"clf": _Clf(), "src_map": {"x": 0, "y": 1}, "pol_map": {"p": 0}, "cond_map": {"c": 0},
               "act_map": {"a": 0}}
        monkeypatch.setitem(dm._cache, "pirate_policy_tree.pkl", pol)
        assert dm.policy_features("x", "p", "c", "a") != dm.policy_features("y", "p", "c", "a")

    def test_missing_maps_use_the_rules_and_warn_once(self, monkeypatch):
        """Pre-fix: a model without maps still answered `ml:<group>` from constant features."""
        errors: list[str] = []
        monkeypatch.setattr(dm, "_has_sklearn", lambda: True)
        monkeypatch.setattr(dm, "_log", lambda *a: None)
        monkeypatch.setattr(dm, "error", lambda module, msg: errors.append(msg))
        monkeypatch.setattr(dm, "_WARNED_MAPS", set())
        for name in ("pirate_survival_free.pkl", "pirate_policy_free.pkl"):
            monkeypatch.setitem(dm._cache, name, None)
        monkeypatch.setitem(dm._cache, "pirate_survival_tree.pkl", {"clf": _Clf()})
        monkeypatch.setitem(dm._cache, "pirate_policy_tree.pkl", {"clf": _Clf()})
        first = dm.predict_pirate_survival("free", 0, 0.5, "hostage_trade")
        second = dm.predict_pirate_survival("free", 1, 0.9, "relic_offer")
        assert first["source"] == "rules:free" and second["source"] == "rules:free"
        assert first["class"] == "pirate_crew_captured"
        pol = dm.predict_pirate_policy("free", "ai_policy", "THE CATCH", "captive", "x")
        assert pol == {"class": "bullet_or_ransom", "probs": [], "source": "rules:free"}
        survival_warnings = [e for e in errors if e.startswith("survival")]
        assert len(survival_warnings) == 1, f"expected one survival warning, got {errors}"

    def test_the_shipped_models_carry_their_maps(self):
        """The repo's own pickles hold the maps the features need."""
        policy = dm._load("pirate_policy_tree.pkl")
        survival = dm._load("pirate_survival_tree.pkl")
        if policy is None or survival is None:
            pytest.skip("sklearn or the shipped models are unavailable")
        assert dm.policy_features("user_policy", "NO MERCY", "captive", "bullet") != \
            dm.policy_features("ai_policy", "THE CATCH", "boarding", "level")
        assert dm.survival_features(0, 0.5, "relic_offer")[2] == 6.0


class TestHeadingDirectlyAboveText:
    def test_obligation_under_a_heading_with_no_blank_line_is_classified(self):
        """Pre-fix: "### 1. Surat\\n*aku boleh janjikan*" was one paragraph starting with '#', so `_kind`
        returned None and the promise was dropped."""
        found = terms.extract("### 1. Surat itu\n*Tiga perkara yang aku boleh janjikan:*\n")
        assert [f["kind"] for f in found] == ["janji"], found
        assert found[0]["speaker"] == "Surat itu"
        assert not found[0]["quote"].startswith("#"), "the heading leaked into the quote"

    def test_paragraph_offsets_still_point_at_their_text(self):
        """Splitting off a heading keeps each offset aligned with the text it names."""
        text = "## A\nbody line\n\nnext"
        for offset, body in terms.paragraphs(text):
            assert text[offset:offset + len(body)] == body, (offset, body)
