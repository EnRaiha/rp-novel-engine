"""Research gate shared by infrastructure, megastructures and containment.

A catalogue column names one `research_projects` row: `infrastructure_types.required_tech`,
`megastructure_types.research_required`, `containment_measures.research_required` and
`bug_war_assets.research_required`. The catalogues held snake_case slugs (`dyson_tech`) while
`research_projects.name` holds display names (`Fusion Reactor Design`), so the gate compared two
different spellings and refused every gated row. A missing project and a locked project also
returned the same text, which hid the fault.

`check_gate` answers one requirement in one place and keeps the two refusals apart.
"""
from __future__ import annotations

from core.db import Database

#: The catalogue names a project that does not exist. A data fault, not a lock.
CATALOGUE_MISS = 'Catalogue names research "{}" but no such project exists.'
#: The project exists and its `unlocked` flag is false.
LOCKED = 'Research "{}" is locked.'


async def check_gate(requirement: str | None, conn=None) -> str | None:
    """The refusal for one catalogue gate value, or None when the gate is open.

    An empty value is no gate: six `infrastructure_types` rows hold `''` and are buildable today.

    @param requirement - the catalogue value, which must be a `research_projects.name`.
    @param conn - the caller's `Database` or transaction connection. Defaults to `Database`, so a
        test that replaces the module attribute still reaches the gate.
    @returns the refusal text, or None when the value is empty or its project is unlocked.
    """
    if not requirement:
        return None
    db = Database if conn is None else conn
    row = await db.fetchrow(
        "SELECT unlocked FROM maya_rp.research_projects WHERE name = $1", requirement)
    if row is None:
        return CATALOGUE_MISS.format(requirement)
    if not row["unlocked"]:
        return LOCKED.format(requirement)
    return None
