"""Module review: session.py.

The resolver itself is sound: precedence is explicit, then RP_SESSION, then the
active-arc file, then maintenance, then it refuses. Four smaller things were not.

`unset` compared the *text* to "0", so `"00"`, `"0.0"` and `False` were read as a
real session id and `--session=00` resolved to session 0, a campaign that cannot
exist, instead of following the arc. `frozen()` dropped an entry it could not parse
in silence, and that entry names a campaign that is supposed to be read-only: the
file read as if the campaign were protected while the engine would write to it.
`mode_label()` swallowed every error and reported `play`. And a bad id raised the
bare `int()` message, which does not say whether the caller or the environment
supplied it.

One finding is reported to the Lead rather than fixed here: `stale_process_default`
has no production caller. The drift detector exists, is tested, and nothing runs
it, so the mechanism this module documents cannot announce itself.

Every test below works on a temporary state directory. `RP_MAINT_DIR` is read at
import, so `STATE_DIR`, `ACTIVE_ARC` and `FROZEN` are patched together, and the
real `~/.config/rp-engine/active_arc` is never touched.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import session as session_mod  # noqa: E402


@pytest.fixture()
def state_dir(tmp_path, monkeypatch):
    """A private engine state directory; the live arc file is untouched."""
    state = tmp_path / "rp-engine"
    state.mkdir()
    monkeypatch.setattr(session_mod, "STATE_DIR", state)
    monkeypatch.setattr(session_mod, "ACTIVE_ARC", state / "active_arc")
    monkeypatch.setattr(session_mod, "FROZEN", state / "frozen_sessions")
    monkeypatch.delenv("RP_SESSION", raising=False)
    return state


class TestUnset:
    """The sentinel that decides whether a session was named at all."""

    @pytest.mark.parametrize("value", [None, "", "   ", 0, "0", "00", "0.0", 0.0, False, "-0"])
    def test_a_zero_of_any_shape_is_no_value(self, value):
        assert session_mod.unset(value) is True, value

    @pytest.mark.parametrize("value", [5, "5", " 5 ", -1, True, "abc", 3.5])
    def test_anything_else_is_a_value(self, value):
        assert session_mod.unset(value) is False, value

    def test_zero_no_longer_resolves_to_session_zero(self, state_dir):
        """Before the fix '00' was a value, and int('00') is a campaign that cannot exist."""
        (state_dir / "active_arc").write_text("5\n")
        assert session_mod.resolve_session("00") == 5

    def test_false_no_longer_resolves_to_session_zero(self, state_dir):
        (state_dir / "active_arc").write_text("5\n")
        assert session_mod.resolve_session(False) == 5


class TestPrecedence:
    """The module's claim, in the order it documents."""

    def test_an_explicit_id_wins_over_the_arc(self, state_dir):
        (state_dir / "active_arc").write_text("5\n")
        assert session_mod.resolve_session(7) == 7

    def test_the_environment_wins_over_the_arc(self, state_dir, monkeypatch):
        (state_dir / "active_arc").write_text("5\n")
        monkeypatch.setenv("RP_SESSION", "9")
        assert session_mod.resolve_session() == 9

    def test_the_arc_answers_when_nothing_else_names_a_session(self, state_dir):
        (state_dir / "active_arc").write_text("12\n")
        assert session_mod.resolve_session() == 12

    def test_maintenance_answers_none_rather_than_guessing(self, state_dir, monkeypatch):
        monkeypatch.setattr(session_mod, "_maintenance_active", lambda: True)
        assert session_mod.resolve_session() is None

    def test_with_nothing_at_all_it_refuses(self, state_dir, monkeypatch):
        monkeypatch.setattr(session_mod, "_maintenance_active", lambda: False)
        with pytest.raises(RuntimeError, match="Refusing to guess"):
            session_mod.resolve_session()

    def test_a_bad_id_names_where_it_came_from(self, state_dir, monkeypatch):
        with pytest.raises(ValueError, match="the caller"):
            session_mod.resolve_session("not-a-number")
        monkeypatch.setenv("RP_SESSION", "also-not-a-number")
        with pytest.raises(ValueError, match="RP_SESSION"):
            session_mod.resolve_session()

    def test_the_active_arc_file_may_carry_whitespace(self, state_dir):
        (state_dir / "active_arc").write_text("  5  \n")
        assert session_mod.resolve_session() == 5


class TestFrozen:
    """A frozen campaign is reference. A typo must not silently unfreeze one."""

    def test_a_well_formed_file_parses(self, state_dir):
        (state_dir / "frozen_sessions").write_text("3\n7\n")
        assert session_mod.frozen() == {3, 7}

    def test_an_entry_that_is_not_a_number_is_reported(self, state_dir, monkeypatch):
        said = []
        monkeypatch.setattr(session_mod, "_warn", said.append)
        (state_dir / "frozen_sessions").write_text("3\n3x\n")
        frozen = session_mod.frozen()
        assert frozen == {3}, frozen
        assert any("3x" in message for message in said), \
            "the typo'd entry must be named, not dropped in silence"

    def test_commas_and_spaces_both_separate(self, state_dir):
        (state_dir / "frozen_sessions").write_text("3, 7 11\n")
        assert session_mod.frozen() == {3, 7, 11}

    def test_a_missing_file_means_nothing_is_frozen(self, state_dir):
        assert session_mod.frozen() == set()

    def test_is_frozen_answers_for_the_ids_it_has(self, state_dir):
        (state_dir / "frozen_sessions").write_text("3\n")
        assert session_mod.is_frozen(3) is True
        assert session_mod.is_frozen(5) is False
        assert session_mod.is_frozen("not-an-id") is False


class TestWritingTheArc:
    """set_active_arc and set_frozen are the only writers of the two files."""

    def test_the_arc_file_is_replaced_atomically(self, state_dir):
        session_mod.set_active_arc(5)
        assert session_mod.active_arc() == 5
        # No temp file is left behind for the next reader to trip over.
        assert not list(state_dir.glob("*.tmp")), list(state_dir.iterdir())

    def test_a_frozen_list_round_trips(self, state_dir):
        assert session_mod.set_frozen([3, 7]) == {3, 7}
        assert session_mod.frozen() == {3, 7}
        assert not list(state_dir.glob("*.tmp"))

    def test_setting_the_arc_moves_what_the_resolver_answers(self, state_dir):
        session_mod.set_active_arc(3)
        assert session_mod.resolve_session() == 3
        session_mod.set_active_arc(5)
        assert session_mod.resolve_session() == 5


class TestModeLabel:
    """Reporting 'play' is safe. Reporting it in silence is how an operator writes canon by mistake."""

    def test_a_readable_flag_reports_the_mode(self, state_dir, monkeypatch):
        import core.maintenance as maintenance

        monkeypatch.setattr(maintenance, "active", lambda: False)
        assert session_mod.mode_label() == "play"

    def test_an_unreadable_flag_says_so(self, state_dir, monkeypatch, capsys):
        said = []
        monkeypatch.setattr(session_mod, "_warn", said.append)
        monkeypatch.setattr(session_mod, "_maintenance_active", lambda: True)
        import core.maintenance as maintenance

        def boom():
            raise RuntimeError("maintenance file unreadable")

        monkeypatch.setattr(maintenance, "active", boom)
        assert session_mod.mode_label() == "play"
        assert any("maintenance" in message for message in said), said


class TestTheImportOrder:
    """This module sits inside an import cycle, and the cycle is silent when it breaks.

    `core.log` imports `core.config`, and `core.config` imports this module to resolve
    the process default. A module-level logger import here closes the loop, so
    `resolve_session` raises ImportError while `core.config` is half-built, and
    `_default_session` catches it and falls back to the FROZEN legacy session. A
    fresh interpreter is the only place that shows up.
    """

    def test_the_config_default_equals_the_resolver(self):
        """One line, no database, no fixtures. The damage is baked in at import.

        `core.config` resolves this at class-body time inside `except Exception`, so
        any ImportError in the chain reads as "no arc file" and every unnamed call is
        handed the frozen campaign. Both sides of this line are correct on their own;
        the assertion is what pins them together.
        """
        from core.config import Config
        from core.session import resolve_session

        assert Config.SESSION_ID == resolve_session(None)

    def test_importing_the_config_agrees_with_the_resolver(self):
        import subprocess

        script = (
            "import core.config as c;"
            "from core.session import resolve_session;"
            "print(int(c.Config.SESSION_ID) == int(resolve_session()))"
        )
        proc = subprocess.run(
            [sys.executable, "-c", script], cwd=str(ROOT),
            capture_output=True, text=True, timeout=120)
        assert proc.stdout.strip() == "True", (
            f"the config default and the resolver disagree:\n{proc.stdout}\n{proc.stderr}")
        assert "FROZEN" not in proc.stderr, proc.stderr


class TestTheDriftDetector:
    """stale_process_default is correct. It is reported to the Lead as unreachable."""

    def test_a_process_stuck_on_another_session_is_named(self, state_dir):
        session_mod.set_active_arc(5)
        message = session_mod.stale_process_default(3)
        assert message is not None and "session 3" in message

    def test_a_process_that_agrees_says_nothing(self, state_dir):
        session_mod.set_active_arc(5)
        assert session_mod.stale_process_default(5) is None
