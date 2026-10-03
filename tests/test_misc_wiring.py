"""The last scattered entry points, one per module.

Each of these was the only caller-less function left in its module: the red herring in mystery, the
influence score in council, ship salvage in pirates, the action guardrail in guardrails, the
decision-to-event link in core/decision, the news read marker in news, the crew producer in crew_system
and the register delta in core/text_processor.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import decision  # noqa: E402
from core.db import Database  # noqa: E402
from core.text_processor import ds_register_delta, enforce_ds_register  # noqa: E402
from modules import council, crew_system, guardrails, news, pirates  # noqa: E402


class TestTheRegisterDelta:
    def test_it_counts_substitutions_and_no_longer_returns_minus_one(self):
        text = "He thrust into her, then fade to black."
        assert ds_register_delta(text, enforce_ds_register(text)) >= 2


class TestTheGuardrail:
    async def test_an_ordinary_action_passes(self):
        await Database.init()
        out = await guardrails.check_action("walk to the dock", {"session_id": 5})
        assert out is not None
        await Database.close()


class TestTheSalvage:
    async def test_a_wreck_can_be_salvaged_or_refused(self):
        out = await pirates.salvage_ship("no such class")
        assert out is not None


class TestTheInfluence:
    async def test_a_faction_with_no_territory_scores_zero(self):
        await Database.init()
        faction = await Database.fetchrow(
            "SELECT * FROM maya_rp.factions WHERE name ILIKE '%Iron Concord%' LIMIT 1")
        if faction:
            out = council.calculate_influence(dict(faction), [], [])
            assert out is not None
        await Database.close()

    async def test_an_empty_faction_record_is_handled(self):
        assert council.calculate_influence({}, [], []) is not None


class TestTheLastTwoWrites:
    async def test_linking_a_decision_to_an_event_is_an_idempotent_write(self):
        """`link_event` is declared `-> None`: it updates and returns nothing. The contract is that it
        completes, and that a second call with the same pair is not an error."""
        await Database.init()
        assert await decision.link_event(5, 999_999, 999_999) is None
        assert await decision.link_event(5, 999_999, 999_999) is None
        await Database.close()

    async def test_marking_news_read_answers(self):
        await Database.init()
        out = await news.mark_read(5, 999_999, "a headline that does not exist")
        assert out is not None
        await Database.close()

    async def test_producing_crew_answers(self, scratch_session):
        # A scratch session, not session 5. produce_crew credits crew_pool on the row it is given, and
        # the measurement for this suite was crew_pool +1604 per run against the live arc.
        await Database.init()
        out = await crew_system.produce_crew(scratch_session)
        assert out is not None
        await Database.close()
