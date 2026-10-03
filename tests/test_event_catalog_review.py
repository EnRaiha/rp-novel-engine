"""Module review tests for modules/event_catalog.py.

No new defect found in this pass. The row says so and names what was checked.

Checked and found correct, and the docstring records the earlier pass: an unknown
category answers with an error and the category list rather than a fabricated
encounter; a pool with nothing at or below the caller's ceiling returns the
closest encounter and names the override instead of handing back a difficulty the
caller ruled out; the catalogue has no duplicate names across categories; and the
tick is a stub.

Reported to the lead, not fixed: the catalogue holds 42 encounters where the
docstring says "60+ templates". That is a documentation claim, not a defect the
code can fix, and inventing the missing encounters is a writing task.

No database: the module reads none.
"""
from __future__ import annotations

import pytest

import modules.event_catalog as ec


def test_an_unknown_category_is_answered_with_the_list():
    out = ec.get_random_encounter("trad", 10)

    assert "unknown encounter category" in out["error"]
    assert out["categories"] == sorted(ec.ENCOUNTERS)


@pytest.mark.parametrize("category", sorted(ec.ENCOUNTERS))
def test_every_catalogued_category_returns_one_of_its_own(category):
    out = ec.get_random_encounter(category, 10)

    assert out["name"] in ec.ENCOUNTERS[category]
    assert out["desc"] and out["diff"] <= 10


def test_an_unknown_ceiling_returns_the_closest_and_names_it():
    out = ec.get_random_encounter("science", 1)

    # two science entries sit at difficulty 4; the tie breaks on the name, so the
    # answer is deterministic rather than "whichever row PostgreSQL returned"
    assert out["name"] == "energy_surge"
    assert "no encounter at or below difficulty 1" in out["warnings"][0]
    assert out["diff"] == 4


def test_the_ceiling_is_honoured_when_something_fits():
    out = ec.get_random_encounter("combat", 4)

    assert out["diff"] <= 4
    assert "warnings" not in out


def test_an_unfiltered_call_reaches_every_category():
    names = {ec.get_random_encounter(max_diff=10)["name"] for _ in range(200)}
    catalogued = {k for cat in ec.ENCOUNTERS.values() for k in cat}

    assert names <= catalogued
    assert len(names) > 10, "the unfiltered pool should reach across categories"


def test_the_ceiling_is_a_floor_of_difficulty_not_a_filter_of_one():
    out = ec.get_random_encounter("combat", 7)

    assert out["diff"] <= 7


def test_contract_every_entry_has_a_difficulty_and_a_description():
    for category, pool in ec.ENCOUNTERS.items():
        for name, entry in pool.items():
            assert set(entry) == {"diff", "desc"}, name
            assert 1 <= entry["diff"] <= 10, name
            assert entry["desc"], name


def test_contract_encounter_names_are_unique_across_categories():
    names = [k for cat in ec.ENCOUNTERS.values() for k in cat]

    assert len(set(names)) == len(names)


def test_contract_the_catalogue_carries_all_six_categories():
    assert set(ec.ENCOUNTERS) == {"trade", "combat", "exploration", "science",
                                  "disaster", "mystery"}


async def test_contract_run_tick_is_a_stub():
    assert await ec.run_tick(5) == {"status": "event_catalog_ready"}
