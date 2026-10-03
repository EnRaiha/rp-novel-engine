"""Module review tests for modules/magic_cost.py.

Defects covered:

1. A Host typo made a witnessed turn CHEAPER than the same act spelled right.
   The witness multiplier was voided by any unknown key in the turn
   (`if acts and witnessed and not unknown`), so a turn declaring
   "well:close_wound" plus a misspelling raised 2 suspicion where the correct
   spelling raised 4. That is a discount for an incomplete declaration, and it
   contradicts the module's own doctrine: an unknown key is refused, not
   guessed. The multiplier now scales what was priced, and the unknown keys are
   still reported.
2. `price_acts("well:touch")` — a bare string, which the caller's own signature
   allows — was iterated character by character, so it priced nothing and
   reported eleven unknown keys. It normalises through `declared_acts` now.

Checked and found correct: no randomness anywhere (the module's second stated
property); an unknown key raises UnknownAct from `price_act` and is collected by
`price_acts`; one act never bills above MAX_ACT_DEVIATION and that stays under
the 75 execution threshold; the free acts stay free; a record is raised only by
an instrument-bearing witness seeing a priced act; `declared_acts` drops blanks
and accepts None; and the same input always prices the same.

No database: the module holds no state and writes nothing.
"""
from __future__ import annotations

import pytest

import modules.magic_cost as cost


# ── 1. A typo must not reduce suspicion ─────────────────────────────────

def test_an_unknown_key_no_longer_discounts_a_witnessed_turn():
    clean = cost.price_acts(["well:close_wound"], witnessed=True)
    typo = cost.price_acts(["well:close_wound", "well:clos_wound"], witnessed=True)

    assert typo["unknown"] == ["well:clos_wound"]
    assert typo["deviation"] == clean["deviation"], "the typo changed the deviation"
    assert typo["suspicion"] == clean["suspicion"], "the typo bought a discount"
    assert typo["suspicion"] == 4          # (deviation 6, suspicion 2) × witness 2


def test_a_turn_of_unknown_keys_alone_prices_at_zero():
    result = cost.price_acts(["not:a_key", "also:not"], witnessed=True, instrument=True)

    assert result["deviation"] == 0
    assert result["suspicion"] == 0
    assert result["record"] is False
    assert result["unknown"] == ["not:a_key", "also:not"]


def test_the_audience_still_scales_only_suspicion():
    clean = cost.price_acts(["well:immersion"])
    seen = cost.price_acts(["well:immersion"], witnessed=True)

    assert seen["deviation"] == clean["deviation"] == 10
    assert seen["suspicion"] == clean["suspicion"] * cost.WITNESS_SUSPICION_MULTIPLIER


def test_an_instrument_records_a_witnessed_priced_act():
    assert cost.price_acts(["sight:mark"], witnessed=True, instrument=True)["record"] is True
    assert cost.price_acts(["sight:mark"], witnessed=False, instrument=True)["record"] is False
    assert cost.price_acts(["well:heat"], witnessed=True, instrument=True)["record"] is False


# ── 2. A bare string is one key, not characters ─────────────────────────

def test_a_bare_string_is_one_act():
    result = cost.price_acts("well:close_wound")

    assert result["priced"] == {"well:close_wound": (6, 2)}
    assert result["unknown"] == []
    assert result["acts"] == ["well:close_wound"]


def test_none_and_blanks_price_at_zero():
    assert cost.price_acts(None)["deviation"] == 0
    assert cost.price_acts(["", "   "])["acts"] == []
    assert cost.price_acts(["well:touch", "  "])["acts"] == ["well:touch"]


def test_the_result_shape_the_caller_reads():
    result = cost.price_acts(["well:touch"], witnessed=True, instrument=True)

    assert set(result) == {"deviation", "suspicion", "record", "record_deviation",
                           "priced", "unknown", "acts"}
    assert result["record_deviation"] == cost.INSTRUMENT_RECORD_DEVIATION


# ── Contract the module claims ──────────────────────────────────────────

def test_contract_no_act_ever_reaches_the_execution_threshold():
    for act in cost.ACT_TABLE:
        deviation, _ = cost.price_act(act)
        assert deviation <= cost.MAX_ACT_DEVIATION
    assert cost.MAX_ACT_DEVIATION < 75


def test_contract_the_free_act_is_still_free():
    assert cost.price_act("well:heat") == (0, 0)


def test_contract_an_unknown_key_is_refused_with_the_known_ones_named():
    with pytest.raises(cost.UnknownAct) as err:
        cost.price_act("dragon:roar")

    message = str(err.value)
    assert "dragon:roar" in message and "well:touch" in message


def test_contract_the_pricing_is_deterministic_for_any_order():
    forward = cost.price_acts(["well:touch", "sight:read", "casting:minor"])
    backward = cost.price_acts(["casting:minor", "sight:read", "well:touch"])

    assert forward["deviation"] == backward["deviation"]
    assert forward["suspicion"] == backward["suspicion"]


def test_contract_every_key_is_namespaced_by_its_source():
    for act in cost.ACT_TABLE:
        assert ":" in act, act
        namespace = act.split(":")[0]
        assert namespace in ("well", "sight", "casting"), act
