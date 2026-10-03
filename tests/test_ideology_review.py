"""Module review tests for modules/ideology.py.

Defects covered:

1. `_recalculate` broke a five-way tie at zero by dictionary order:
   `max(scores, key=scores.get)` returns the FIRST key, so a campaign with no
   action history was declared a MILITARY DICTATORSHIP and the guess was
   persisted. Both live sessions carry exactly that: ideology
   `military_dictatorship` with every score 0 and an empty `player_action_log`.
   No evidence now means undetermined, and nothing is written.
2. `get()` returned `scores_jsonb` straight from the jsonb column, which
   asyncpg hands back as text, while the derived path returned a dict: the same
   key was two different types depending on which path answered.
3. An ideology stored in the database that is not in IDEOS silently returned the
   democratic profile while reporting the stored name.
4. `run_tick` logged its crash at info level while `tax_tolerance`'s unknown-name
   default was a bare literal.

The live rows are NOT cleared here: session 3 is frozen and session 5's label is
a canon decision. The lead has the numbers.

No database: every test drives a fake Database.
"""
from __future__ import annotations

import json

import pytest

import modules.ideology as ideology


class FakeDB:
    def __init__(self, fetchrow=None, fetch=None, execute_tag="INSERT 0 1"):
        self.fetchrow_value = fetchrow
        self.fetch_rows = fetch if fetch is not None else []
        self.execute_tag = execute_tag
        self.calls = []

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", " ".join(sql.split()), args))
        return self.fetchrow_value

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        return self.fetch_rows

    async def execute(self, sql, *args):
        self.calls.append(("execute", " ".join(sql.split()), args))
        return self.execute_tag

    def sql(self, kind=None):
        return [c[1] for c in self.calls if kind is None or c[0] == kind]

    def args_for(self, needle, kind=None):
        return [c[2] for c in self.calls
                if needle in c[1] and (kind is None or c[0] == kind)]


def _install(monkeypatch, fake):
    for name in ("fetchrow", "fetch", "execute"):
        monkeypatch.setattr("modules.ideology.Database." + name, getattr(fake, name))
    return fake


# ── 1. No evidence is not a dictatorship ─────────────────────────────────

async def test_a_campaign_with_no_actions_is_undetermined_and_writes_nothing(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow=None, fetch=[]))

    out = await ideology.get(5)

    assert out["ideology"] == ideology.UNDETERMINED_IDEOLOGY
    assert set(out["scores"].values()) == {0}
    assert not fake.sql("execute"), "a guess was persisted"


async def test_evidence_still_picks_its_ideology_and_persists_it(monkeypatch):
    rows = [{"action_category": "combat", "t": 10}]
    fake = _install(monkeypatch, FakeDB(fetchrow=None, fetch=rows))

    out = await ideology.get(5)

    assert out["ideology"] == "military_dictatorship"
    written = fake.args_for("INSERT INTO maya_rp.ideology_state", "execute")[0]
    assert written[0] == 5 and written[1] == "military_dictatorship"
    assert json.loads(written[2])["military_dictatorship"] == 3


async def test_mercy_and_diplomacy_still_reach_democracy(monkeypatch):
    rows = [{"action_category": "mercy", "t": 9}, {"action_category": "diplomacy", "t": 40}]
    _install(monkeypatch, FakeDB(fetchrow=None, fetch=rows))

    out = await ideology.get(5)

    assert out["ideology"] == "benevolent_democracy"


# ── 2. The scores type is the same on both paths ─────────────────────────

async def test_stored_scores_are_decoded_from_jsonb_text(monkeypatch):
    stored = {"military_dictatorship": 0, "technocratic_utopia": 3}
    _install(monkeypatch, FakeDB(fetchrow={"ideology": "technocratic_utopia",
                                           "scores_jsonb": json.dumps(stored)}))

    out = await ideology.get(5)

    assert out["scores"] == stored
    assert isinstance(out["scores"], dict)


async def test_unreadable_scores_report_empty_instead_of_crashing(monkeypatch):
    _install(monkeypatch, FakeDB(fetchrow={"ideology": "technocratic_utopia",
                                           "scores_jsonb": "{not json"}))

    out = await ideology.get(5)

    assert out["scores"] == {}


# ── 3. An unknown stored ideology is named ───────────────────────────────

async def test_an_unknown_stored_ideology_falls_back_and_says_so(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.ideology.info", lambda mod, msg: seen.append(msg))
    _install(monkeypatch, FakeDB(fetchrow={"ideology": "benevolent_tyranny",
                                           "scores_jsonb": None}))

    out = await ideology.get(5)

    assert out["ideology"] == "benevolent_tyranny"        # reported as stored
    assert out["tone"] == ideology.UNDETERMINED_PROFILE["tone"]
    assert any("benevolent_tyranny" in m for m in seen), seen


# ── 4. Tax tolerance and the tick ────────────────────────────────────────

@pytest.mark.parametrize("name,tolerance", sorted(ideology.TAX_TOLERANCE.items()))
def test_each_declared_ideology_keeps_its_tolerance(name, tolerance):
    assert ideology.tax_tolerance(name) == tolerance


def test_an_unknown_ideology_takes_the_declared_neutral_default():
    assert ideology.tax_tolerance("no such society") == ideology.DEFAULT_TAX_TOLERANCE
    assert ideology.tax_tolerance(ideology.UNDETERMINED_IDEOLOGY) == ideology.DEFAULT_TAX_TOLERANCE


async def test_run_tick_reports_the_ideology(monkeypatch):
    _install(monkeypatch, FakeDB(fetchrow={"ideology": "pirate_confederacy",
                                           "scores_jsonb": "{}"}))

    assert await ideology.run_tick(5) == {"ideology": "pirate_confederacy"}


async def test_run_tick_reports_a_crash_as_an_error(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.ideology.error", lambda mod, msg: seen.append(msg))

    async def boom(_session_id):
        raise RuntimeError("no society")

    monkeypatch.setattr("modules.ideology.get", boom)

    out = await ideology.run_tick(5)

    assert "no society" in out["error"]
    assert any("no society" in m for m in seen), seen


# ── Contract the module claims ───────────────────────────────────────────

async def test_contract_the_prompt_renders_for_every_ideology(monkeypatch):
    for name in list(ideology.IDEOS) + [ideology.UNDETERMINED_IDEOLOGY]:
        _install(monkeypatch, FakeDB(fetchrow={"ideology": name, "scores_jsonb": "{}"}))
        prompt = await ideology.get_prompt(5)
        assert prompt.startswith("[SOCIETY: ")
        assert "Tone: " in prompt and "Recruits: " in prompt


async def test_contract_every_profile_names_the_four_prompt_fields():
    for name, profile in ideology.IDEOS.items():
        assert set(profile) == {"values", "bonuses", "penalties", "recruits", "tone"}, name
    assert set(ideology.UNDETERMINED_PROFILE) == {"values", "bonuses", "penalties",
                                                  "recruits", "tone"}


async def test_contract_the_read_is_session_scoped(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow=None, fetch=[]))

    await ideology.get(5)

    for sql in fake.sql("fetchrow") + fake.sql("fetch"):
        assert "session_id=$1" in sql, sql
    assert fake.args_for("ideology_state", "fetchrow")[0] == (5,)
