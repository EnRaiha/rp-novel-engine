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
    async def test_an_item_lands_in_a_dict_shaped_inventory(self):
        """The red proof for the fix: before it, this raised AttributeError on `.append`.

        Nine characters carried `{}` in the column. Setting one back to that shape and adding an item
        proves `add_item` routes through the coercion rather than testing the helper in isolation.
        """
        import json as _json

        from core.db import Database

        await Database.init()
        target = await Database.fetchrow(
            "SELECT id, inventory_jsonb FROM maya_rp.characters"
            " WHERE session_id = 5 AND jsonb_typeof(inventory_jsonb) = 'array' LIMIT 1")
        assert target, "no character to test against"
        before = target["inventory_jsonb"]
        try:
            await Database.execute(
                "UPDATE maya_rp.characters SET inventory_jsonb='{}'::jsonb WHERE id=$1", target["id"])
            from modules.character_profile import add_item
            await add_item(int(target["id"]), {"name": "red proof item"}, 5)
            after = await Database.fetchval(
                "SELECT inventory_jsonb FROM maya_rp.characters WHERE id=$1", target["id"])
            items = after if isinstance(after, list) else _json.loads(after)
            assert any(i.get("name") == "red proof item" for i in items), after
        finally:
            await Database.execute(
                "UPDATE maya_rp.characters SET inventory_jsonb=$1::jsonb WHERE id=$2",
                before if isinstance(before, str) else _json.dumps(before), target["id"])
            await Database.close()
