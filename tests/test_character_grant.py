"""The boundary that hands a character something new.

`add_item` and `add_to_wardrobe` had no caller. Reviewing them before wiring found three defects that
a caller would have inherited: `set_outfit` crashed on its own success line, `add_item` called
`.append` on nine characters whose inventory held `{}`, and nothing normalised the two shapes.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.character_profile import _as_list, grant  # noqa: E402


class TestListCoercion:
    def test_a_null_column_is_an_empty_list(self):
        assert _as_list(None, "inventory_jsonb") == []

    def test_an_empty_dict_is_an_empty_list(self):
        # Nine characters carried this, and `.append` on it raised AttributeError.
        assert _as_list("{}", "inventory_jsonb") == []

    def test_a_list_decodes(self):
        assert _as_list('[{"name": "knife"}]', "inventory_jsonb") == [{"name": "knife"}]

    def test_a_dict_with_contents_is_refused_not_reshaped(self):
        with pytest.raises(ValueError, match="not a list"):
            _as_list('{"items": [1]}', "inventory_jsonb")


class TestGrant:
    async def test_grant_with_nothing_to_do_is_refused(self):
        with pytest.raises(ValueError, match="at least one of"):
            await grant(2077)

    async def test_the_success_line_no_longer_crashes(self):
        """`info(module, msg)` takes two arguments; the old call passed a third as a keyword."""
        import inspect

        from modules import character_profile

        source = inspect.getsource(character_profile.set_outfit)
        assert "char_id=" not in source, "the log call would raise TypeError whenever it fired"


class TestAddItemReachesTheCoercion:
    async def test_an_item_lands_in_a_dict_shaped_inventory(self, scratch_session):
        """The red proof for the fix: before it, this raised AttributeError on `.append`.

        Nine characters carried `{}` in the column. A scratch character set to that shape proves
        `add_item` routes through the coercion rather than testing the helper in isolation.
        """
        import json as _json

        from core.db import Database
        from modules.character_profile import add_item

        await Database.init()
        try:
            await Database.execute("DELETE FROM maya_rp.characters WHERE session_id = $1", scratch_session)
            await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", scratch_session)
            await Database.execute(
                "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1, 'grant scratch', 'active')",
                scratch_session)
            cid = await Database.fetchval(
                "INSERT INTO maya_rp.characters (session_id, name, inventory_jsonb)"
                " VALUES ($1, 'Grant Subject', '{}'::jsonb) RETURNING id", scratch_session)

            await add_item(int(cid), {"name": "red proof item"}, scratch_session)

            after = await Database.fetchval(
                "SELECT inventory_jsonb FROM maya_rp.characters WHERE id=$1", cid)
            items = after if isinstance(after, list) else _json.loads(after)
            assert any(i.get("name") == "red proof item" for i in items), after
        finally:
            await Database.execute("DELETE FROM maya_rp.characters WHERE session_id = $1", scratch_session)
            await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", scratch_session)
            await Database.close()
