"""Module review tests for modules/adventures.py.

Defects covered:

1. `resolve(adventure_type, outcome)` accepted `adventure_type` and never used
   it, so a "merchant" and a "planet_crack" paid the same 500-5000 credits with
   nothing saying so. The type is echoed back and the docstring states that it
   does not price the reward.
2. `outcome` was not validated: any string that was not "success" returned
   `{"reward": 0, "outcome": <typo>}` with no error, so a misspelled outcome read
   as a resolved encounter. It is refused by name now.
3. The reward credit had no check that it landed, so a session with no
   `resources` row (session 5 has none) was told it had been paid.

Checked and found correct: `generate` reads the system from this session, pays
only the trade encounters a gold reward, and flags the two combat types; the
encounter list has no duplicates; and the tick is a stub.

No database: every test drives a fake Database.
"""
from __future__ import annotations

import pytest

import modules.adventures as adv


class FakeDB:
    def __init__(self, fetchval="Mastika", execute_tag="UPDATE 1"):
        self.fetchval_value = fetchval
        self.execute_tag = execute_tag
        self.calls = []

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", " ".join(sql.split()), args))
        return self.fetchval_value

    async def execute(self, sql, *args):
        self.calls.append(("execute", " ".join(sql.split()), args))
        return self.execute_tag

    def sql(self, kind=None):
        return [c[1] for c in self.calls if kind is None or c[0] == kind]

    def args_for(self, needle, kind=None):
        return [c[2] for c in self.calls
                if needle in c[1] and (kind is None or c[0] == kind)]


def _install(monkeypatch, fake):
    for name in ("fetchval", "execute"):
        monkeypatch.setattr("modules.adventures.Database." + name, getattr(fake, name))
    return fake


async def test_generate_reads_the_system_from_this_session(monkeypatch):
    fake = _install(monkeypatch, FakeDB())

    out = await adv.generate(5)

    assert out["system"] == "Mastika"
    assert out["type"] in adv.ENCOUNTER_TYPES
    assert fake.args_for("maya_rp.territory", "fetchval")[0] == (5,)


async def test_generate_falls_back_when_the_campaign_has_no_system(monkeypatch):
    _install(monkeypatch, FakeDB(fetchval=None))

    out = await adv.generate(5)

    assert out["system"] == "Unknown"


@pytest.mark.parametrize("etype,gold,combat", [("merchant", True, False),
                                               ("trade_fleet", True, False),
                                               ("pirate", False, True),
                                               ("ambush", False, True)])
async def test_generate_pays_trade_and_flags_combat(monkeypatch, etype, gold, combat):
    _install(monkeypatch, FakeDB())
    monkeypatch.setattr(adv.random, "choice", lambda seq: etype)

    out = await adv.generate(5)

    assert (out["gold_reward"] > 0) is gold
    assert out["combat"] is combat


# ── 2. The outcome is validated ─────────────────────────────────────────

@pytest.mark.parametrize("outcome", ["sucess", "win", "", "SUCCESS"])
async def test_an_unknown_outcome_is_refused(monkeypatch, outcome):
    fake = _install(monkeypatch, FakeDB())

    with pytest.raises(ValueError, match="outcome must be one of"):
        await adv.resolve("pirate", outcome, 5)

    assert not fake.calls


async def test_a_failure_pays_nothing_and_echoes_the_type(monkeypatch):
    fake = _install(monkeypatch, FakeDB())

    out = await adv.resolve("derelict", "failure", 5)

    assert out == {"reward": 0, "outcome": "failure", "adventure_type": "derelict"}
    assert not fake.sql("execute")


# ── 1 + 3. The payout ───────────────────────────────────────────────────

async def test_a_success_pays_and_names_the_encounter(monkeypatch):
    fake = _install(monkeypatch, FakeDB())
    monkeypatch.setattr(adv.random, "randint", lambda a, b: b)

    out = await adv.resolve("artifact", "success", 5)

    assert out == {"reward": 5000, "outcome": "success", "adventure_type": "artifact"}
    assert fake.args_for("credits=credits+$1", "execute")[0] == (5000, 5)


async def test_the_reward_does_not_vary_by_encounter_type(monkeypatch):
    _install(monkeypatch, FakeDB())
    monkeypatch.setattr(adv.random, "randint", lambda a, b: a)

    merchant = await adv.resolve("merchant", "success", 5)
    crack = await adv.resolve("planet_crack", "success", 5)

    assert merchant["reward"] == crack["reward"] == 500


async def test_a_session_without_a_treasury_is_not_told_it_was_paid(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.adventures.info", lambda mod, msg: seen.append(msg))
    _install(monkeypatch, FakeDB(execute_tag="UPDATE 0"))
    monkeypatch.setattr(adv.random, "randint", lambda a, b: b)

    out = await adv.resolve("pirate", "success", 5)

    assert out["reward"] == 0 and "No treasury row" in out["error"]
    assert any("NOT paid" in m for m in seen), seen


def test_contract_the_encounter_list_is_unique():
    assert len(adv.ENCOUNTER_TYPES) == len(set(adv.ENCOUNTER_TYPES))
    assert adv.OUTCOMES == ("success", "failure")


async def test_contract_run_tick_is_a_stub():
    assert await adv.run_tick(5) == {"status": "adventures_ready"}
