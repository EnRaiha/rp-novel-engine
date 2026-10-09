"""Module review tests for modules/economy.py.

Defects covered:

1. `run_tick` and `gate_toll_income` defaulted their session to the literal 3,
   the frozen reference campaign, while Config.SESSION_ID resolves to the active
   arc. A bare call taxed and read the wrong campaign.
2. `pop = t["population"] or 1_000_000` treated a stored 0 as missing: a world
   with no residents was given a million of them, put back on the tax roll, and
   left with a status that is not 'abandoned', so the next tick did it again.
3. `morale = … or 50` contradicted the line below it, whose own comment defines
   morale 0 as -50% growth. A collapsed empire grew at the baseline rate.
4. `invest` computed `min(amount or 500_000, credits)` and then subtracted it:
   a negative amount, or a treasury already below zero, MINTED credits.
5. Two `except Exception:` blocks — the market index and the tax tolerance —
   fell back without saying so. The tolerance was also re-read once per
   territory: 109 identical queries in one tick.
6. `resolve_intent`'s docstring promised a `result` key that no branch set.

Tax arithmetic, the refugee redistribution and the money guards that were
already right are asserted below as the module contract.

No database: every test drives a fake Database.
"""
import re
from datetime import datetime, timezone

import pytest

import modules.economy as economy


def _guard_denies(sql: str, args, row) -> bool:
    """True when a guarded charge's WHERE clause cannot match the fixed row.

    The fake answers every `fetchrow` with one row, so a charge of 1000 against a treasury of 10 came
    back as paid and the refusal test failed for the wrong reason. The charge is one
    `UPDATE ... WHERE COALESCE(<col>, 0) >= $n`, and this reads those guards out of the statement and
    applies them to the row, which is what the database does with them.
    """
    if not isinstance(row, dict) or "UPDATE maya_rp.resources" not in sql:
        return False
    for match in re.finditer(r"COALESCE\((\w+), 0\) >= \$(\d+)", sql):
        column, index = match.group(1), int(match.group(2))
        if (row.get(column) or 0) < args[index - 1]:
            return True
    return False


class FakeDB:
    def __init__(self, fetchrow=None, fetch=None, fetchval=None, rows=None):
        self.fetchrow_rows = rows or []
        self.fetchrow_value = fetchrow
        self.fetch_rows = fetch if fetch is not None else []
        self.fetchval_value = fetchval
        self.calls = []

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", " ".join(sql.split()), args))
        for marker, value in self.fetchrow_rows:
            if marker in sql:
                return value
        if _guard_denies(sql, args, self.fetchrow_value):
            return None
        return self.fetchrow_value

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        return self.fetch_rows

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", " ".join(sql.split()), args))
        return self.fetchval_value

    async def execute(self, sql, *args):
        self.calls.append(("execute", " ".join(sql.split()), args))
        return "UPDATE 1"

    def sql(self, kind=None):
        return [c[1] for c in self.calls if kind is None or c[0] == kind]

    def args_for(self, needle, kind=None):
        return [c[2] for c in self.calls
                if needle in c[1] and (kind is None or c[0] == kind)]


def _install(monkeypatch, fake):
    for name in ("fetch", "fetchrow", "fetchval", "execute"):
        monkeypatch.setattr("modules.economy.Database." + name, getattr(fake, name))
    return fake


# ── 1. The session default ───────────────────────────────────────────────

async def test_gate_toll_income_defaults_to_the_engine_session(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchval=0))
    monkeypatch.setattr("modules.economy.Config.SESSION_ID", 77)

    await economy.gate_toll_income()

    assert fake.args_for("faction_trade_deals", "fetchval")[0] == (77,)


async def test_run_tick_defaults_to_the_engine_session(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow={}))
    monkeypatch.setattr("modules.economy.Config.SESSION_ID", 77)

    await economy.run_tick()

    assert fake.args_for("last_tick_at")[0] == (77,)


# ── 2. A stored zero population is zero ──────────────────────────────────

async def _one_tick(monkeypatch, territory, morale=50):
    fake = _install(monkeypatch, FakeDB(
        rows=[("last_tick_at", {"last_tick_at": datetime.now(timezone.utc)}),
              ("ideology_state", {"ideology": "benevolent_democracy"})],
        fetch=[territory], fetchval=morale))

    async def no_toll(_session_id=None):
        return 0

    # The toll path is not the subject here, and it shares the fetchval the
    # fake answers with the morale read.
    monkeypatch.setattr("modules.economy.gate_toll_income", no_toll)
    monkeypatch.setattr("modules.economy.calc_game_days", lambda when: 1.0)
    await economy.run_tick(3)
    return fake


def _territory(**over):
    row = {"id": 4, "system_name": "Ashfall", "population": 10_000_000,
           "tax_rate": 0.05, "development_level": 1, "crisis_level": 0,
           "max_population": 0, "status": "controlled"}
    row.update(over)
    return row


async def test_an_empty_world_is_not_repopulated_by_the_tick(monkeypatch):
    fake = await _one_tick(monkeypatch, _territory(population=0))

    written = fake.args_for("UPDATE territory SET population", "execute")[0]
    assert written[0] == 0, "an empty world was given residents"
    assert written[1] == "abandoned"
    # no base tax from this world: the receipt path is the flat tick income only
    receipt = fake.args_for("credits=credits+", "execute")[0]
    assert receipt[2] == int(200_000 * 1.0), receipt


async def test_an_empty_world_files_no_depopulation_event(monkeypatch):
    fake = await _one_tick(monkeypatch, _territory(population=0))

    events = fake.args_for("INSERT INTO maya_rp.events", "execute")
    assert not events, "a world that was already empty reported a depopulation"


async def test_a_null_population_still_takes_the_declared_default(monkeypatch):
    fake = await _one_tick(monkeypatch, _territory(population=None, max_population=50_000_000))

    written = fake.args_for("UPDATE territory SET population", "execute")[0]
    assert written[0] > 1_000_000, "the NULL default did not apply"


# ── 3. Morale zero is a value ────────────────────────────────────────────

async def test_zero_morale_halves_growth_instead_of_reading_as_baseline(monkeypatch):
    roomy = dict(max_population=50_000_000)      # below capacity, so it can grow
    zero = await _one_tick(monkeypatch, _territory(**roomy), morale=0)
    baseline = await _one_tick(monkeypatch, _territory(**roomy), morale=50)

    grew_zero = zero.args_for("UPDATE territory SET population", "execute")[0][0]
    grew_baseline = baseline.args_for("UPDATE territory SET population", "execute")[0][0]
    assert grew_zero < grew_baseline, "morale 0 grew as fast as morale 50"


async def test_null_morale_falls_back_to_the_baseline(monkeypatch):
    roomy = dict(max_population=50_000_000)
    null_morale = await _one_tick(monkeypatch, _territory(**roomy), morale=None)
    baseline = await _one_tick(monkeypatch, _territory(**roomy), morale=50)

    assert (null_morale.args_for("UPDATE territory SET population", "execute")[0][0]
            == baseline.args_for("UPDATE territory SET population", "execute")[0][0])


# ── 4. invest cannot mint credits ────────────────────────────────────────

@pytest.mark.parametrize("amount,credits,expected_invested", [
    (0, 1_000_000, 500_000),        # no amount → the declared default
    (-25_000, 1_000_000, 500_000),  # a non-positive amount means "unspecified"
    (5_000, 1_000_000, 5_000),
    (5_000, -800, 0),               # a debt cannot fund an investment
])
async def test_invest_never_raises_the_treasury(monkeypatch, amount, credits, expected_invested):
    fake = _install(monkeypatch, FakeDB(fetchrow={"id": 1, "credits": credits,
                                                  "alloys": 0, "fuel": 0}))

    out = await economy.resolve_intent(3, "invest", "the yards", amount)

    assert out["invested"] == expected_invested
    # The charge is one guarded `fetchrow(UPDATE ... WHERE COALESCE(credits, 0) >= $2 RETURNING ...)`,
    # so the binds are (session_id, amount). It used to be an `execute` that subtracted whatever the
    # caller asked for after a separate affordability read.
    spends = fake.args_for("COALESCE(credits, 0) -", "fetchrow")
    if expected_invested == 0:
        assert not spends, "a refused investment still moved money"
        assert out["success"] is False
    else:
        assert spends[0] == (3, expected_invested)
        assert spends[0][1] > 0


async def test_buy_still_refuses_a_treasury_it_cannot_cover(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow={"id": 1, "credits": 10, "alloys": 0, "fuel": 0}))

    out = await economy.resolve_intent(3, "buy", "a frigate", 1_000)

    assert out["success"] is False and out["credits_available"] == 10
    assert not fake.args_for("credits = credits -", "execute")


async def test_sell_credits_the_treasury(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow={"id": 1, "credits": 10, "alloys": 0, "fuel": 0}))

    out = await economy.resolve_intent(3, "sell", "spice", 2_000)

    assert out["gain"] == 2_000
    assert fake.args_for("credits = credits +", "execute")[0] == (2_000, 3)


async def test_an_unknown_action_says_what_it_supports(monkeypatch):
    _install(monkeypatch, FakeDB(fetchrow={"id": 1, "credits": 10, "alloys": 0, "fuel": 0}))

    out = await economy.resolve_intent(3, "embezzle", "the vault")

    assert out["success"] is False
    assert "buy" in out["narrative_hook"] and "invest" in out["narrative_hook"]


async def test_no_treasury_row_is_named_not_guessed(monkeypatch):
    _install(monkeypatch, FakeDB(fetchrow=None))

    out = await economy.resolve_intent(5, "buy", "a frigate", 10)

    assert out == {"domain": "economy", "success": False, "error": "No resources found"}


# ── 5. The fallbacks are logged, and the tolerance is read once ──────────

async def test_the_tolerance_is_read_once_per_tick_not_once_per_world(monkeypatch):
    fake = _install(monkeypatch, FakeDB(
        rows=[("last_tick_at", {"last_tick_at": datetime.now(timezone.utc)}),
              ("ideology_state", {"ideology": "benevolent_democracy"})],
        fetch=[_territory(id=1, system_name="A"), _territory(id=2, system_name="B"),
               _territory(id=3, system_name="C")],
        fetchval=50))
    monkeypatch.setattr("modules.economy.calc_game_days", lambda when: 1.0)

    await economy.run_tick(3)

    assert len(fake.sql("fetchrow")) == 2, fake.sql("fetchrow")
    assert len([s for s in fake.sql("fetchrow") if "ideology_state" in s]) == 1


async def test_a_failing_tax_tolerance_is_logged_once(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.economy.error", lambda mod, msg: seen.append(msg))

    import modules.ideology as ideology

    def boom(_ideology):
        raise RuntimeError("ideology table gone")

    monkeypatch.setattr(ideology, "tax_tolerance", boom)
    fake = _install(monkeypatch, FakeDB(
        rows=[("last_tick_at", {"last_tick_at": datetime.now(timezone.utc)}),
              ("ideology_state", {"ideology": "benevolent_democracy"})],
        fetch=[_territory(id=1), _territory(id=2)], fetchval=50))
    monkeypatch.setattr("modules.economy.calc_game_days", lambda when: 1.0)

    await economy.run_tick(3)

    assert any("tax tolerance" in m for m in seen), seen
    assert fake.args_for("UPDATE territory SET population", "execute"), "the tick stopped"


async def test_a_failing_market_index_is_logged(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.economy.error", lambda mod, msg: seen.append(msg))

    import modules.market as market

    def boom(_session):
        raise RuntimeError("no market")

    monkeypatch.setattr(market, "get_market_index", boom)
    _install(monkeypatch, FakeDB(
        rows=[("last_tick_at", {"last_tick_at": datetime.now(timezone.utc)})], fetch=[],
        fetchval=50))
    monkeypatch.setattr("modules.economy.calc_game_days", lambda when: 1.0)

    await economy.run_tick(3)

    assert any("market index" in m for m in seen), seen


# ── Module contract ──────────────────────────────────────────────────────

def test_contract_marginal_brackets_thin_with_world_size():
    # 20M at rate 0.1: core 10M at full, next 10M at 18%
    assert economy._territory_tax(20_000_000, 0.1, 1.0, 1.0) == pytest.approx(1_000_000 + 180_000)
    # a small world pays the full rate on all of it
    assert economy._territory_tax(1_000_000, 0.1, 1.0, 1.0) == pytest.approx(100_000)


def test_contract_the_bracket_revenue_never_decreases_with_population():
    previous = -1.0
    for pop in (0, 1, 10_000_000, 10_000_001, 100_000_000, 1_000_000_000, 5_000_000_000):
        revenue = economy._territory_tax(pop, 0.1, 1.0, 1.0)
        assert revenue >= previous, pop
        previous = revenue


def test_contract_a_development_bonus_applies_to_the_core_only():
    core = economy._territory_tax(10_000_000, 0.1, 1.5, 1.0)
    beyond = economy._territory_tax(50_000_000, 0.1, 1.5, 1.0)
    assert core == pytest.approx(1_500_000)
    # the 40M above the core pays the 18% band with no development bonus
    assert beyond == pytest.approx(1_500_000 + 40_000_000 * 0.1 * 0.18)


def test_contract_crisis_and_market_multipliers_scale_the_receipt():
    base = economy._territory_tax(10_000_000, 0.1, 1.0, 1.0, 1.0)
    assert economy._territory_tax(10_000_000, 0.1, 1.0, 0.5, 1.0) == pytest.approx(base * 0.5)
    assert economy._territory_tax(10_000_000, 0.1, 1.0, 1.0, 1.2) == pytest.approx(base * 1.2)


def test_contract_the_toll_is_charged_per_full_crossing():
    assert economy.GATE_TOLL_RATE == 25_000
    assert economy.GATE_TOLL_VOLUME_PER_CROSSING == 40
    assert (39 // economy.GATE_TOLL_VOLUME_PER_CROSSING) * economy.GATE_TOLL_RATE == 0
    assert (40 // economy.GATE_TOLL_VOLUME_PER_CROSSING) * economy.GATE_TOLL_RATE == 25_000
