"""Event catalog module review tests — one per defect found reading modules/event_catalog.py.

Defects covered:

1. An unknown category fell through to a fabricated `default_encounter` — an encounter that exists in
   no category of the catalogue, with the description and difficulty the reader invented for it. A
   typo answered, so a caller could not tell a real draw from a miss.
2. A difficulty ceiling the catalogue could not meet was ignored silently: the code fell back to the
   whole pool, so `max_diff=1` could return a difficulty-9 encounter with nothing said about it.

Not fixed, reported to the lead: `run_tick` takes a session and holds no per-session state, because
the catalogue is a literal in this module. The tick is a no-op by design; the test below pins that so
the signature cannot be mistaken for session scope that went missing.

The module touches no database, so every test here is a pure function call.
"""
from __future__ import annotations

import modules.event_catalog as event_catalog  # noqa: E402
from modules.event_catalog import ENCOUNTERS, get_random_encounter


def _all_names() -> set[str]:
    return {name for cat in ENCOUNTERS.values() for name in cat}


class TestAnUnknownCategorySaysSo:
    def test_a_misspelled_category_is_refused_not_fabricated(self):
        out = get_random_encounter("trad")

        assert "error" in out, out
        assert "trad" in out["error"], out
        assert "name" not in out, f"a fabricated encounter was returned: {out}"

    def test_the_refusal_names_the_categories_that_do_exist(self):
        out = get_random_encounter("nonsense")

        assert out["categories"] == sorted(ENCOUNTERS), out
        assert "combat" in out["categories"], out

    def test_every_real_category_still_draws_from_its_own_pool(self):
        for category in ENCOUNTERS:
            out = get_random_encounter(category)
            assert out["name"] in ENCOUNTERS[category], (category, out)


class TestTheDifficultyCeiling:
    def test_a_ceiling_that_cannot_be_met_is_reported(self):
        """The lowest difficulty in the catalogue is 2, so a ceiling of 1 cannot be honoured."""
        out = get_random_encounter(max_diff=1)

        assert "warnings" in out, out
        assert out["diff"] == 2, out
        assert "difficulty 1" in out["warnings"][0], out

    def test_the_closest_encounter_is_chosen_deterministically(self):
        first = get_random_encounter(max_diff=0)
        second = get_random_encounter(max_diff=0)

        assert first["name"] == second["name"], (first, second)
        assert first["name"] == "crashed_satellite", first

    def test_a_ceiling_that_can_be_met_is_not_warned_about(self):
        for _ in range(20):
            out = get_random_encounter(max_diff=3)
            assert "warnings" not in out, out
            assert out["diff"] <= 3, out

    def test_the_ceiling_holds_for_every_category(self):
        for category in ENCOUNTERS:
            for _ in range(10):
                out = get_random_encounter(category, max_diff=3)
                if "warnings" in out:
                    floor = min(e["diff"] for e in ENCOUNTERS[category].values())
                    assert out["diff"] == floor, (category, out)
                else:
                    assert out["diff"] <= 3, (category, out)


class TestTheCatalogueContract:
    def test_a_draw_with_no_category_comes_from_the_catalogue(self):
        for _ in range(25):
            out = get_random_encounter()
            assert out["name"] in _all_names(), out
            assert "default_encounter" != out["name"], out

    def test_every_entry_carries_the_fields_a_caller_reads(self):
        for cat, entries in ENCOUNTERS.items():
            for name, entry in entries.items():
                assert isinstance(entry["diff"], int) and entry["diff"] > 0, (cat, name, entry)
                assert entry["desc"].strip(), (cat, name, entry)

    async def test_the_tick_holds_no_session_state(self):
        """The module's tick is a status answer; it reads and writes nothing."""
        out = await event_catalog.run_tick(5)

        assert out.get("status") == "event_catalog_ready", out
