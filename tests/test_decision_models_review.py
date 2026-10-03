"""Module review: core/decision_models.py.

THE DEFECT. The predictors decoded a model's output through a map that describes its *inputs*.

`scripts/train_models.py` writes the label map of the day, and the shipped pickles carry `act_map`
and `action_map`. The code inverted that map to name the predicted class, without asking whether it
describes this model's output at all. The shipped survival model classifies `['DEATH', 'LIVE']` and
its `action_map` names eight raid actions, so `predict_pirate_survival` returned an action name where
its caller writes "the crew's fate" into the raid description, and the per-group bias multiplied an
*outcome* column with an *action* index: `hostage_trade` is index 1, which scaled `LIVE`.

The same trust breaks on the next retrain in the other direction: the current trainer writes
`labels`, which no reader here looks for, so every prediction would have decoded to a bare index
string such as "1".

`_label_map` uses a map only when the classifier's own classes live inside its value space, and
falls back to `classes_`; `_bias_for` applies a multiplier only to a column the prediction has and
logs the labels it drops, where the old code dropped them in silence.

The rest: `detect_pirate_group` wrote `factions.pirate_group` by `id` alone, `log_decision` read the
faction name by `id` alone while holding the session it was told to log for, and an unknown pirate
group silently took the free model while the returned `source` label kept the caller's string.

Reported, not changed: the module docstring promises "low-confidence → rule-based fallback" and no
confidence threshold exists anywhere in the module; and the ML path returns a crew fate (`LIVE`)
while the rule fallback returns a raid action (`hostage_trade`), so one function speaks two
vocabularies and unifying them changes what the raid log says.

The scratch session is derived from the process id in a band no other test file uses. Every row this
file writes is removed in the fixture's finally.
"""
from __future__ import annotations

import inspect
import os
import pathlib
import sys

import numpy as np
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import decision_models as dm  # noqa: E402
from core.db import Database  # noqa: E402

SCRATCH_SESSION = 300 + (os.getpid() % 100)
OTHER_SESSION = SCRATCH_SESSION + 500
FACTION = "Decision Review Cartel"

CLEANUP = (
    "DELETE FROM maya_rp.ai_decision_log WHERE session_id=$1",
    "DELETE FROM maya_rp.faction_relations WHERE session_id=$1",
    "DELETE FROM maya_rp.factions WHERE session_id=$1",
)


async def _clear(session_id: int) -> None:
    for statement in CLEANUP:
        await Database.execute(statement, session_id)


@pytest.fixture()
async def scratch_session():
    """A session with one pirate faction, removed before and after the test."""
    await Database.init()
    await _clear(SCRATCH_SESSION)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status)"
        " VALUES ($1,'Decision review session','active') ON CONFLICT (id) DO NOTHING",
        SCRATCH_SESSION,
    )
    faction = await Database.fetchval(
        "INSERT INTO maya_rp.factions (session_id, name) VALUES ($1,$2) RETURNING id",
        SCRATCH_SESSION,
        FACTION,
    )
    try:
        yield {"session": SCRATCH_SESSION, "faction": faction}
    finally:
        await _clear(SCRATCH_SESSION)
        await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", SCRATCH_SESSION)
        await Database.close()


class _FakeClf:
    """A classifier that answers the same distribution every call."""

    def __init__(self, classes, probs):
        self.classes_ = np.array(classes)
        self._probs = np.array(probs, dtype=float)

    def predict_proba(self, _features):
        return np.array([self._probs])


#: The shipped `pirate_survival_tree.pkl`, reduced to the parts the readers use.
SURVIVAL_ACTIONS = {"den_surrenders": 0, "hostage_trade": 1, "pirate_crew_captured": 2,
                    "pirate_king_captured": 3, "pirate_queen_captured": 4,
                    "queen_offers_alliance": 5, "relic_offer": 6, "tender_of_alliance": 7}
#: The shipped `pirate_policy_tree.pkl`: an encoded label space that a subset was trained on.
POLICY_ACTIONS = {"bullet": 0, "bullet_or_ransom": 1, "check_first": 2, "clear_all": 3,
                  "confirm_first": 4, "convert": 5, "debt_bound": 6, "level": 7}


def _prime(monkeypatch, name: str, model: dict) -> None:
    """Serve one model from the cache, so the test never touches the pickles on disk."""
    monkeypatch.setitem(dm._cache, name, model)


class TestTheModelsOwnLabelSpace:
    """A model's `classes_` is the only authority for what its output columns mean."""

    def test_a_fate_is_decoded_in_the_models_own_classes(self, monkeypatch):
        monkeypatch.setattr(dm, "_has_sklearn", lambda: True)
        monkeypatch.setattr(dm, "_log", lambda *a: None)
        _prime(monkeypatch, "pirate_survival_free.pkl", None)
        _prime(monkeypatch, "pirate_survival_tree.pkl",
               {"clf": _FakeClf(["DEATH", "LIVE"], [0.05, 0.95]), "action_map": SURVIVAL_ACTIONS})
        fate = dm.predict_pirate_survival("free", 0, 0.5, "hostage_trade")
        assert fate["class"] == "LIVE", "the crew's fate is not the action that was passed in"
        assert fate["source"] == "ml:free"
        assert len(fate["probs"]) == 2

    def test_a_bias_that_names_no_class_of_this_model_is_dropped_and_reported(self, monkeypatch):
        said: list[str] = []
        monkeypatch.setattr(dm, "_has_sklearn", lambda: True)
        monkeypatch.setattr(dm, "_log", lambda module, msg: said.append(msg))
        _prime(monkeypatch, "pirate_survival_free.pkl", None)
        _prime(monkeypatch, "pirate_survival_tree.pkl",
               {"clf": _FakeClf(["DEATH", "LIVE"], [0.05, 0.95]), "action_map": SURVIVAL_ACTIONS})
        fate = dm.predict_pirate_survival("free", 0, 0.5, "hostage_trade")
        assert fate["probs"] == [0.05, 0.95], (
            "an action index must not scale an outcome column")
        assert any("no column" in message for message in said), said

    def test_a_bias_that_names_a_class_is_applied(self, monkeypatch):
        monkeypatch.setattr(dm, "_has_sklearn", lambda: True)
        monkeypatch.setattr(dm, "_log", lambda *a: None)
        _prime(monkeypatch, "pirate_survival_free.pkl",
               {"clf": _FakeClf(["DEATH", "LIVE"], [0.5, 0.5])})
        monkeypatch.setitem(dm.SURVIVAL_BIAS, "free", {"LIVE": 3.0})
        fate = dm.predict_pirate_survival("free", 0, 0.5, "hostage_trade")
        assert fate["class"] == "LIVE"
        assert fate["probs"][1] == pytest.approx(0.75)

    def test_the_policy_pickle_still_decodes_through_its_own_map(self, monkeypatch):
        """`classes_` [0, 1] live inside `act_map`'s values, so that map is this model's map."""
        monkeypatch.setattr(dm, "_has_sklearn", lambda: True)
        monkeypatch.setattr(dm, "_log", lambda *a: None)
        _prime(monkeypatch, "pirate_policy_free.pkl", None)
        _prime(monkeypatch, "pirate_policy_tree.pkl",
               {"clf": _FakeClf([0, 1], [0.4, 0.6]), "act_map": POLICY_ACTIONS})
        out = dm.predict_pirate_policy(
            "free", "ai_policy", "STANDARD UNIFORMITY", "boarding", "check_first")
        assert out["class"] == "bullet_or_ransom"
        assert out["source"] == "ml:free"

    def test_a_pickle_from_the_current_trainer_decodes_through_its_labels(self, monkeypatch):
        """`scripts/train_models.py` writes `labels`; the readers here only knew `act_map`."""
        monkeypatch.setattr(dm, "_has_sklearn", lambda: True)
        monkeypatch.setattr(dm, "_log", lambda *a: None)
        _prime(monkeypatch, "pirate_policy_free.pkl",
               {"clf": _FakeClf([0, 1], [0.9, 0.1]),
                "labels": ["bullet", "bullet_or_ransom"]})
        out = dm.predict_pirate_policy(
            "free", "ai_policy", "THE STANDARD", "boarding", "bullet")
        assert out["class"] == "bullet", "a bare index is not an answer"

    def test_the_label_map_prefers_the_classifiers_own_classes(self):
        model = {"clf": _FakeClf(["DEATH", "LIVE"], [0.5, 0.5]), "action_map": SURVIVAL_ACTIONS}
        assert dm._label_map(model) == {"DEATH": 0, "LIVE": 1}


class TestTheGroupThatWasNotOne:
    def test_an_unknown_group_is_named_and_answered_as_free(self, monkeypatch):
        said: list[str] = []
        monkeypatch.setattr(dm, "_log", lambda module, msg: said.append(msg))
        out = dm.predict_pirate_policy(
            "hiredd", "ai_policy", "THE STANDARD", "boarding", "check_first")
        assert out["source"].endswith(":free"), (
            "the label must name the group that answered, not the one that was asked for")
        assert any("unknown pirate group 'hiredd'" in message for message in said), said


class TestTheGroupDetection:
    """`detect_pirate_group` reads scoped, and used to write unscoped."""

    async def _relation(self, session: int, faction: int, **fields) -> None:
        columns = ", ".join(fields)
        params = ", ".join(f"${n}" for n in range(3, 3 + len(fields)))
        await Database.execute(
            f"INSERT INTO maya_rp.faction_relations (session_id, faction_a, {columns})"
            f" VALUES ($1,$2,{params})",
            session, faction, *fields.values(),
        )

    async def test_no_relations_makes_a_free_pirate(self, scratch_session):
        assert await dm.detect_pirate_group(scratch_session["faction"], SCRATCH_SESSION) == "free"

    async def test_trade_ties_make_a_sponsor(self, scratch_session):
        await self._relation(SCRATCH_SESSION, scratch_session["faction"],
                             standing="neutral", trade_volume=120, military_tension=0.1)
        assert await dm.detect_pirate_group(
            scratch_session["faction"], SCRATCH_SESSION) == "sponsor"

    async def test_one_hot_relation_with_no_trade_makes_a_hired_privateer(self, scratch_session):
        await self._relation(SCRATCH_SESSION, scratch_session["faction"],
                             standing="hostile", trade_volume=0, military_tension=0.8)
        assert await dm.detect_pirate_group(
            scratch_session["faction"], SCRATCH_SESSION) == "hired"

    async def test_an_explicit_override_wins(self, scratch_session):
        await Database.execute(
            "UPDATE maya_rp.factions SET pirate_group='hired' WHERE id=$1", scratch_session["faction"])
        assert await dm.detect_pirate_group(
            scratch_session["faction"], SCRATCH_SESSION) == "hired"

    async def test_the_detected_group_is_written_back_to_its_own_session(self, scratch_session):
        await self._relation(SCRATCH_SESSION, scratch_session["faction"],
                             standing="neutral", trade_volume=50, military_tension=0.0)
        await dm.detect_pirate_group(scratch_session["faction"], SCRATCH_SESSION)
        assert await Database.fetchval(
            "SELECT pirate_group FROM maya_rp.factions WHERE id=$1 AND session_id=$2",
            scratch_session["faction"], SCRATCH_SESSION) == "sponsor"

    async def test_a_faction_of_another_session_is_not_classified(self, scratch_session):
        """The read is scoped, so the ask answers the default rather than the other campaign."""
        assert await dm.detect_pirate_group(
            scratch_session["faction"], OTHER_SESSION) == dm.DEFAULT_GROUP

    async def test_the_log_records_the_faction_name_of_the_session_it_logs_for(self, scratch_session):
        await dm.log_decision(scratch_session["faction"], "pirate_policy", {"src": "ai_policy"},
                              "check_first", [0.5, 0.5], "free", SCRATCH_SESSION)
        row = await Database.fetchrow(
            "SELECT faction_name, session_id, pirate_group FROM maya_rp.ai_decision_log"
            " WHERE session_id=$1 ORDER BY id DESC LIMIT 1", SCRATCH_SESSION)
        assert row["faction_name"] == FACTION
        assert row["pirate_group"] == "free"

    def test_the_detected_group_is_written_back_with_its_session(self):
        """The id came from a scoped read; the write must carry the session too."""
        assert "SET pirate_group=$1 WHERE id=$2 AND session_id=$3" in inspect.getsource(
            dm.detect_pirate_group)

    def test_the_log_reads_the_faction_of_the_session_it_logs_for(self):
        assert "SELECT name FROM maya_rp.factions WHERE id=$1 AND session_id=$2" in inspect.getsource(
            dm.log_decision)
