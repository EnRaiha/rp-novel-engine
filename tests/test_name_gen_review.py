"""Module review tests for core/name_gen.py.

Defects covered:

1. `unique_name(culture=...)` accepted, documented and ignored the culture. Every
   name came from the Malay pools whatever was asked for, and the live caller
   `scripts/generate_slave_names.py:96` draws a culture per slave and got Malay
   names for all of them. `_compose`, the only function that knows the cultures,
   was unreachable from `unique_name`.
2. `family_rate` was accepted and ignored, so a Malay name always carried a family
   name.
3. `_compose` fell through to a Malay name for an unknown culture, so a typo
   produced plausible output instead of an error.
4. `_compose(culture="malay")` still wrote the patronymic rule ("Ahmad bin
   Abdullah") that the module header, `_compose_malay_first` and Izzat's Day 1481
   rule all cancel. Two copies of one rule, and the stale copy was wrong.
5. The roman-numeral fallback returned its first pick without checking it, under a
   comment that called it a guarantee. It could hand back a name that already
   existed.
6. `_exists` consulted the generator's own `_seen` set only when no connection was
   set, so with a live connection a generator could return the same name twice.

Checked and found correct, so the row is not silent about what it looked at:
`_exists` probes all three tables the module names (characters, crew_roster,
slaves); the cross-session scope of that probe is the documented canon-collision
rule (rule 3 in the header), not an unscoped read; names are composed from fixed
pools, so no user text reaches the ILIKE pattern; `_compose(seed=...)` is
deterministic for a given seed, and `unique_name`'s unseeded draw is generation
rather than a roll a campaign has replayed.

No database: every test drives a fake connection.
"""
from __future__ import annotations

import pytest

from core import name_gen


class FakeConn:
    """Answers the uniqueness probe; `taken` holds names that must not be reused."""

    def __init__(self, taken=(), always_exists=False):
        self.taken = set(taken)
        self.always_exists = always_exists
        self.probes: list[str] = []

    async def fetchrow(self, sql, names):
        """`names` is the list of full and bare candidates; the match is exact and case-insensitive."""
        self.probes.append(names)
        if self.always_exists:
            return {"exists": 1}
        wanted = {n.lower() for n in names}
        return {"exists": 1} if any(t.lower() in wanted for t in self.taken) else None


async def test_culture_reaches_the_composer():
    """(1) A Chinese name is composed from the Chinese pools, not the Malay ones."""
    gen = name_gen.NameGenerator(FakeConn())
    for _ in range(20):
        name = await gen.unique_name(culture="chinese")
        assert name.split()[0] in name_gen.CHINESE_FAMILY, name


async def test_western_culture_reaches_the_composer():
    """(1) Same defect, the other end of the pool."""
    gen = name_gen.NameGenerator(FakeConn())
    for _ in range(20):
        name = await gen.unique_name(culture="western")
        assert name.split()[-1] in name_gen.WESTERN_LAST, name


async def test_module_level_wrapper_passes_culture_through():
    """(1) The documented entry point (`from core.name_gen import unique_name`)."""
    name = await name_gen.unique_name(conn=FakeConn(), culture="east")
    assert name.split()[-1] in name_gen.EAST_FAMILY, name


async def test_mixed_draws_from_the_documented_mix():
    """(1) MIXED_CULTURES is the documented ~70/20/10 draw, so `mixed` uses it."""
    gen = name_gen.NameGenerator(FakeConn())
    names = [await gen.unique_name(culture="mixed") for _ in range(200)]
    assert any(n.split()[0] in name_gen.CHINESE_FAMILY for n in names), names[:5]


async def test_unknown_culture_raises_instead_of_returning_a_malay_name():
    """(3) A typo used to produce a perfect Malay name and no error."""
    with pytest.raises(ValueError, match="unknown culture"):
        await name_gen.NameGenerator(FakeConn()).unique_name(culture="chinse")
    with pytest.raises(ValueError, match="unknown culture"):
        name_gen.NameGenerator._compose(culture="klingon", seed=1)


async def test_family_rate_is_honoured():
    """(2) family_rate=0.0 means single names; it used to mean nothing."""
    gen = name_gen.NameGenerator(FakeConn())
    names = [await gen.unique_name(culture="malay", family_rate=0.0) for _ in range(10)]
    assert all(len(n.split()) == 1 for n in names), names


def test_malay_composition_has_no_patronymic():
    """(4) The patronymic was cancelled on Day 1481; _compose still wrote it."""
    names = [name_gen.NameGenerator._compose(culture="malay", seed=s, family_rate=1.0)
             for s in range(50)]
    assert all(len(n.split()) == 2 for n in names), names[:5]
    assert not any(" bin " in n or " binti " in n for n in names), names[:5]


def test_the_cancelled_patronymic_flag_is_refused():
    """(4) Asking for bin/binti is refused rather than silently served a plain name."""
    with pytest.raises(ValueError, match="cancelled"):
        name_gen.NameGenerator._compose_malay_first(seed=1, with_bin=True)


async def test_exhaustion_raises_rather_than_returning_a_duplicate():
    """(5) With every name taken, the old fallback returned one it never checked."""
    gen = name_gen.NameGenerator(FakeConn(always_exists=True))
    with pytest.raises(RuntimeError, match="exhausted"):
        await gen.unique_name(max_attempts=2)


async def test_a_generator_does_not_reuse_its_own_names(monkeypatch):
    """(6) `_seen` was skipped whenever a connection was set."""
    monkeypatch.setattr(name_gen, "MELAYU_FIRST_M", ["Aidil"])
    monkeypatch.setattr(name_gen, "MELAYU_FIRST_F", ["Aidil"])
    monkeypatch.setattr(name_gen, "PATRONYM_FATHERS", ["Abdullah"])

    gen = name_gen.NameGenerator(FakeConn())
    first = await gen.unique_name(culture="malay", family_rate=1.0, max_attempts=1)
    second = await gen.unique_name(culture="malay", family_rate=1.0, max_attempts=1)

    assert first == "Aidil Abdullah"
    assert second != first, "the same generator returned the same name twice"
    assert second.startswith("Aidil Abdullah "), second


async def test_setia_family_choice_is_still_honoured():
    """The contract the docstring claims: mother takes family_names[0], father [-1]."""
    gen = name_gen.NameGenerator(FakeConn())
    mother = await gen.unique_name(family_names=["Voss", "al-Dabaran"], decided_by="mother")
    father = await gen.unique_name(family_names=["Voss", "al-Dabaran"], decided_by="father")
    assert mother.endswith(" Voss"), mother
    assert father.endswith(" al-Dabaran"), father


async def test_two_family_rules_are_refused():
    """Two family-name rules at once: one used to win in silence."""
    with pytest.raises(ValueError, match="not both"):
        await name_gen.NameGenerator(FakeConn()).unique_name(
            family_names=["Voss"], father_name="Izzat")
