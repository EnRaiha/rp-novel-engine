"""Four relationship fields, and the trap in having two of them named alike.

`maya_rp.characters` carries `bond`, `bond_level`, `affection`, `loyalty` and `aggro`. The engine's
RELATIONSHIPS block reads **`bond`** (core/context.py orders companions by it and filters on
`COALESCE(bond,0) > 0`), while `bond_level` is read in three places only. Two columns, one meaning,
and the live one is not the obvious one.

That is a trap: a writer who sets `bond_level` and expects the engine to notice gets silence. The
King's ruling that the wives are not married yet made it worse, because the carryover had set
`bond_level` and the engine never saw it.

These tests pin the model and the trap:
- the engine's companion query reads `bond`, asserted by reading the source, so nobody quietly
  changes which field is live;
- no row may carry a `bond_level` with nothing in `bond`, because that is a relationship the engine
  cannot see.
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTEXT = ROOT / "core" / "context.py"


def _rows(sql: str) -> list[tuple]:
    import os
    import psycopg2

    env = pathlib.Path.home() / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, _, value = line.partition("=")
                key = key.removeprefix("export ").strip()
                if key.startswith(("OC_PG_", "POSTGRES_")) and key not in os.environ:
                    os.environ[key] = value.strip().strip("'\"")
    if not os.environ.get("OC_PG_HOST"):
        pytest.skip("no OC_PG_* settings")
    conn = psycopg2.connect(host=os.environ["OC_PG_HOST"], port=int(os.environ.get("OC_PG_PORT", 5432)),
                            user=os.environ["OC_PG_USER"], password=os.environ.get("OC_PG_PASS"),
                            dbname=os.environ.get("OC_PG_DB", "maya_memory"))
    try:
        cur = conn.cursor()
        cur.execute(sql)
        return cur.fetchall()
    finally:
        conn.close()


class TestTheLiveField:
    def test_the_companion_query_reads_bond_not_bond_level(self):
        source = CONTEXT.read_text(encoding="utf-8")
        assert "c.bond" in source, "the RELATIONSHIPS block must read `bond`"
        assert "ORDER BY COALESCE(c.bond, 0) DESC" in source

    def test_the_filter_uses_bond_too(self):
        source = CONTEXT.read_text(encoding="utf-8")
        assert "COALESCE(c.bond, 0) > 0" in source


class TestNoInvisibleRelationship:
    def test_no_row_carries_a_bond_level_the_engine_cannot_see(self):
        """A bond_level with an empty bond is a relationship the engine cannot read.

        The trap this exists to catch: the carryover set `bond_level` on 35 wives, the engine
        filters on `bond`, and nothing in the scene ever noticed the difference.
        """
        invisible = _rows(
            """SELECT id, name, bond, bond_level FROM maya_rp.characters
               WHERE session_id = 5 AND COALESCE(bond_level, 0) > 0 AND COALESCE(bond, 0) = 0
               ORDER BY id""")
        assert not invisible, f"bond_level set while bond is empty: {invisible[:5]}"

    def test_session_5_has_no_bonded_companions_yet(self):
        """The King's ruling: the marriages have not happened, so nobody is bonded.

        If this starts failing, either a marriage was written or a carryover came back.
        """
        bonded = _rows("SELECT count(*) FROM maya_rp.characters WHERE session_id = 5 AND COALESCE(bond, 0) > 0")
        assert bonded[0][0] == 0


class TestAffectionIsVisible:
    """A field nobody reads is a field nobody has.

    `affection` was added to carry the King's first carryover part, and a column audit then found
    it named nowhere in the code. The engine's RELATIONSHIPS block is where such a value matters,
    so the query and the printed line both had to learn it.
    """

    def test_the_companion_query_selects_affection(self):
        source = CONTEXT.read_text(encoding="utf-8")
        assert "c.affection" in source
        assert "COALESCE(c.affection, 0) > 0" in source, "affection must be part of the filter"

    def test_the_printed_line_carries_affection_when_it_is_set(self):
        source = CONTEXT.read_text(encoding="utf-8")
        assert "affection {affection} · " in source

    async def test_a_warm_companion_appears_with_no_marriage_bond(self):
        """The King's model: affection can exist while bond_level and bond stay at zero."""
        from core.context import companions_of_note

        rows = await companions_of_note(5, limit=3)
        assert rows, "session 5 has 35 wives at affection 4; the block must list them"
        assert all((row["bond"] or 0) == 0 for row in rows), "nobody is married yet"
        assert any((row["affection"] or 0) > 0 for row in rows)
