"""Module review: core/persona.py.

TWO DEFECTS FIXED, both about a name that is not checked against the table that
defines it.

`field_path` joined whatever `field` it was handed into a path under the persona
folder. `FIELDS` is the canonical set, and it was consulted by `load` and
`scaffold` but not here, so a field name that was not one of the four resolved to
a path that does not exist and read back as an empty string: a typo in a caller
was indistinguishable from a persona with nothing written in that field. The same
join makes `"../outside"` a path out of the folder, and it read that file. The
sibling module learned this already and guards it by hand: `map_server.py:450`
refuses a request field outside its own `CHAR_FILES` before it touches disk. The
check lives here now, naming the value it refused.

`INJECTED` is the allowlist the module docstring leans on: voice and intro may
reach the model, lore and play-guide never do. Nothing read it. `build_block`
hardcoded the pair, so the allowlist four lines above the function documented a
rule the function only happened to satisfy. It reads `INJECTED` now, in its
order, which is what makes the constant real: the test below moves a field into
the allowlist and the block follows.

The intro budget (`audits`) is pinned at both ends of its boundary, and the
parser's arrow-less default is pinned as it stands rather than changed: a line
under `## Boundary` with no `=>` is a case expecting any flag, which is a shape
someone can mean.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core import persona  # noqa: E402


def _persona_root(tmp_path, monkeypatch):
    monkeypatch.setattr(persona, "PERSONA_ROOT", tmp_path)
    return tmp_path


def _write_field(root, slug, field, text):
    folder = root / slug
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{field}.md").write_text(text, encoding="utf-8")


class TestTheFieldName:
    """`FIELDS` is the set; everything that takes a field name says so."""

    def test_an_unknown_field_is_refused_by_name(self, tmp_path, monkeypatch):
        _persona_root(tmp_path, monkeypatch)
        _write_field(tmp_path, "king", "voice", "VOICE-TEXT")

        with pytest.raises(ValueError) as refused:
            persona.read_field("king", "voise")

        assert "voise" in str(refused.value), "the refusal names the value it refused"
        assert list(persona.FIELDS) and "voice" in str(refused.value), "and the set it expected"

    def test_a_field_name_cannot_walk_out_of_the_persona_folder(self, tmp_path, monkeypatch):
        _persona_root(tmp_path, monkeypatch)
        (tmp_path / "outside.md").write_text("SECRET-OUTSIDE", encoding="utf-8")

        with pytest.raises(ValueError):
            persona.read_field("king", "../outside")

    def test_every_declared_field_still_resolves(self, tmp_path, monkeypatch):
        _persona_root(tmp_path, monkeypatch)
        for field in persona.FIELDS:
            _write_field(tmp_path, "king", field, f"TEXT-{field}")
            assert persona.read_field("king", field) == f"TEXT-{field}"

    def test_scaffold_writes_every_declared_field(self, tmp_path, monkeypatch):
        root = _persona_root(tmp_path, monkeypatch)

        written = persona.scaffold("nethara", display_name="Nethara")

        assert sorted(written) == sorted(persona.FIELDS)
        assert all(path.is_file() for path in written.values())
        assert all((root / "nethara" / f"{field}.md").is_file() for field in persona.FIELDS)


class TestTheInjectedAllowlist:
    """`INJECTED` is what `build_block` reads, not a comment beside it."""

    def test_only_the_allowlisted_fields_reach_the_block(self, tmp_path, monkeypatch):
        _persona_root(tmp_path, monkeypatch)
        _write_field(tmp_path, "king", "voice", "VOICE-TEXT")
        _write_field(tmp_path, "king", "intro", "INTRO-TEXT")
        _write_field(tmp_path, "king", "lore", "LORE-TEXT")
        _write_field(tmp_path, "king", "play-guide", "GUIDE-TEXT")

        block = persona.build_block("king")

        assert "VOICE-TEXT" in block and "INTRO-TEXT" in block
        assert "LORE-TEXT" not in block and "GUIDE-TEXT" not in block

    def test_the_allowlist_is_the_source_of_truth(self, tmp_path, monkeypatch):
        _persona_root(tmp_path, monkeypatch)
        _write_field(tmp_path, "king", "voice", "VOICE-TEXT")
        _write_field(tmp_path, "king", "intro", "INTRO-TEXT")
        _write_field(tmp_path, "king", "lore", "LORE-TEXT")
        monkeypatch.setattr(persona, "INJECTED", ("voice", "lore"))

        block = persona.build_block("king")

        assert "LORE-TEXT" in block, "moving a field into the allowlist moves it into the block"
        assert "INTRO-TEXT" not in block

    def test_the_declared_allowlist_is_the_two_the_docstring_names(self):
        assert persona.INJECTED == ("voice", "intro")
        assert set(persona.INJECTED) < set(persona.FIELDS)

    def test_the_voice_leads_the_opening_beat(self, tmp_path, monkeypatch):
        _persona_root(tmp_path, monkeypatch)
        _write_field(tmp_path, "king", "voice", "VOICE-TEXT")
        _write_field(tmp_path, "king", "intro", "INTRO-TEXT")

        block = persona.build_block("king")

        assert block.index("VOICE-TEXT") < block.index("INTRO-TEXT")
        assert "## Opening beat" in block


class TestTheIntroBudget:
    """The opening beat is worth its tokens only while the session is opening."""

    def test_the_beat_survives_up_to_the_budget_and_leaves_after_it(self, tmp_path, monkeypatch):
        _persona_root(tmp_path, monkeypatch)
        _write_field(tmp_path, "king", "voice", "VOICE-TEXT")
        _write_field(tmp_path, "king", "intro", "INTRO-TEXT")

        for audits in range(0, persona.INTRO_MAX_AUDITS + 1):
            assert "INTRO-TEXT" in persona.build_block("king", audits=audits), audits
        assert "INTRO-TEXT" not in persona.build_block("king", audits=persona.INTRO_MAX_AUDITS + 1)
        assert "VOICE-TEXT" in persona.build_block("king", audits=persona.INTRO_MAX_AUDITS + 1)

    def test_an_unnamed_audit_count_keeps_the_beat(self, tmp_path, monkeypatch):
        _persona_root(tmp_path, monkeypatch)
        _write_field(tmp_path, "king", "intro", "INTRO-TEXT")

        assert "INTRO-TEXT" in persona.build_block("king")

    def test_a_persona_with_no_files_is_an_empty_block(self, tmp_path, monkeypatch):
        _persona_root(tmp_path, monkeypatch)

        assert persona.build_block("nobody") == ""
        assert persona.load("nobody")["block"] == ""
        assert persona.load("nobody")["boundary_cases"] == []


class TestTheBoundaryCases:
    """The arrow form the live persona uses, and the shape of a line without one."""

    def test_the_live_line_shape_reads_back_as_the_player_literal(self, tmp_path, monkeypatch):
        _persona_root(tmp_path, monkeypatch)
        _write_field(
            tmp_path,
            "king",
            "voice",
            '# Voice\n\n## Boundary\n\n- "I am sorry, I need you." => gen-emotive-apology\n',
        )

        assert persona.boundary_expectations("king") == [
            {"text": "I am sorry, I need you.", "expect": "gen-emotive-apology"}
        ]

    def test_a_line_with_no_arrow_expects_a_flag(self, tmp_path, monkeypatch):
        _persona_root(tmp_path, monkeypatch)
        _write_field(tmp_path, "king", "voice", "## Boundary\n\n- modern slang\n")

        assert persona.boundary_expectations("king") == [{"text": "modern slang", "expect": "flagged"}]

    def test_only_the_boundary_section_is_a_case(self, tmp_path, monkeypatch):
        _persona_root(tmp_path, monkeypatch)
        _write_field(
            tmp_path,
            "king",
            "voice",
            "## Register rules\n\n- not a case\n\n## Boundary\n\n- a case => flagged\n\n## Other\n\n- not a case\n",
        )

        assert persona.boundary_cases("king") == ["a case => flagged"]
