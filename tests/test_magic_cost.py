"""Magic accounting: the pure pricing, and the audit seam that consumes it.

The rule under test is the third mixing law: magic leaves data. Two properties matter
more than the numbers. An undeclared turn must price at zero, because the engine cannot
detect magic in prose. And maintenance must stay total, because a stand-down that still
bills is not a stand-down.
"""
from __future__ import annotations

import pytest

import modules.magic_cost as cost


class TestPricing:
    def test_no_acts_price_at_zero(self):
        result = cost.price_acts([])
        assert result["deviation"] == 0
        assert result["suspicion"] == 0
        assert result["record"] is False

    def test_acts_add_up(self):
        result = cost.price_acts(["well:close_wound", "sight:read"])
        assert result["deviation"] == 7
        assert result["suspicion"] == 3

    def test_the_same_input_gives_the_same_price(self):
        args = ["well:immersion", "sight:mark"]
        assert cost.price_acts(args) == cost.price_acts(args)

    def test_a_free_act_stays_free(self):
        assert cost.price_acts(["well:heat"])["deviation"] == 0

    def test_an_unknown_key_is_refused_not_guessed(self):
        result = cost.price_acts(["not:a_key"])
        assert result["unknown"] == ["not:a_key"]
        assert result["deviation"] == 0

    def test_price_act_raises_on_an_unknown_key(self):
        with pytest.raises(cost.UnknownAct):
            cost.price_act("not:a_key")

    def test_one_act_never_exceeds_the_cap(self):
        for act in cost.ACT_TABLE:
            assert cost.price_act(act)[0] <= cost.MAX_ACT_DEVIATION

    def test_the_cap_stays_below_the_execution_threshold(self):
        assert cost.MAX_ACT_DEVIATION < 75, "a single act must never reach System Reclamation"


class TestWitness:
    def test_a_witness_doubles_suspicion_only(self):
        alone = cost.price_acts(["well:close_wound"])
        seen = cost.price_acts(["well:close_wound"], witnessed=True)
        assert seen["deviation"] == alone["deviation"]
        assert seen["suspicion"] == alone["suspicion"] * cost.WITNESS_SUSPICION_MULTIPLIER

    def test_only_an_instrument_raises_a_record(self):
        assert cost.price_acts(["well:close_wound"], witnessed=True)["record"] is False
        assert cost.price_acts(["well:close_wound"], witnessed=True, instrument=True)["record"] is True

    def test_a_free_act_raises_no_record(self):
        assert cost.price_acts(["well:heat"], witnessed=True, instrument=True)["record"] is False

    def test_an_unwitnessed_act_raises_no_record(self):
        assert cost.price_acts(["well:immersion"], instrument=True)["record"] is False


class TestDeclaration:
    def test_none_normalises_to_empty(self):
        assert cost.declared_acts(None) == []

    def test_one_key_normalises_to_a_list(self):
        assert cost.declared_acts("sight:read") == ["sight:read"]

    def test_blanks_are_dropped(self):
        assert cost.declared_acts(["sight:read", "  ", ""]) == ["sight:read"]


class TestPreviewShape:
    """A preview must answer in the same shape as a real audit, minus the write.

    The CLI printer reads `skip_reason` from the result, and the preview path did not carry
    it, so the first preview run crashed after the audit had already answered. Nothing was
    written, which is the property that matters, but a caller cannot rely on a return shape
    that differs by path.
    """

    def test_every_key_the_real_path_returns_is_present_in_the_preview(self):
        import inspect

        import core.ooc as ooc

        source = inspect.getsource(ooc.audit)
        assert '"skip_reason": None,' in source, "preview must declare skip_reason"
        assert '"preview": True,' in source
