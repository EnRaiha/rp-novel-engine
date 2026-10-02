"""The render queue's order, and why it is a parameter rather than a hidden default.

Queueing 35 wives by row id renders whoever was queued first, and that turned out to be Rika
Voss rather than the wives the story leans on. The order was always a decision; this makes it
one the caller states.
"""
from __future__ import annotations

import pytest

from core import portraits


class TestQueueOrders:
    def test_the_three_orders_are_present(self):
        assert set(portraits.QUEUE_ORDERS) == {"id", "bond", "name"}

    def test_the_default_is_the_queue_order(self):
        assert portraits.QUEUE_ORDERS["id"] == "a.id"

    def test_bond_orders_by_bond_level_first(self):
        assert portraits.QUEUE_ORDERS["bond"].startswith("c.bond_level DESC")

    def test_no_fragment_can_end_the_statement(self):
        """The fragments are constants, and the check keeps them from becoming anything else."""
        for name, fragment in portraits.QUEUE_ORDERS.items():
            assert ";" not in fragment, f"{name} must not be able to end a statement"
            assert "--" not in fragment, f"{name} must not carry a comment marker"
            assert "$" not in fragment, f"{name} must not carry a bind marker"

    async def test_an_unknown_order_is_refused_before_the_database_is_touched(self):
        with pytest.raises(ValueError, match="unknown queue order"):
            await portraits.pending(5, limit=1, order="bond_level; DROP TABLE characters")
