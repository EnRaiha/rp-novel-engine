"""Manual-script fixes: import_character_card, scene_selector, turn_watcher, char_query.

Every database write goes to a scratch session (900-999) and `Config.SESSION_ID` is pinned to it, so no
default can reach session 3 or 5. The tests that need no database use fakes and temp files. Nothing
here touches the live novel files, `data/roster.yaml`, `~/.cache` or `~/backups`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import pytest
import pytest_asyncio

from core import portraits, session
from core.config import Config
from core.db import Database
from scripts import char_query as cq
from scripts import import_character_card as icc
from scripts import scene_selector as ss
from scripts import turn_watcher as tw

NAME = "Zz Fixture Ranger"


# ── import_character_card ────────────────────────────────────────────────────

def _fields(**over) -> dict:
    base = {
        "name": NAME,
        "description": "A tall ranger. She wears a grey cloak. Her hair is black.",
        "personality": "calm, dry, watchful",
        "scenario": "Guards the north gate.",
        "first_mes": "She looks up from the map.",
        "mes_example": "",
        "creator_notes": "",
        "tags": ["scout"],
        "alternates": [],
        "origin": "test",
    }
    return {**base, **over}


@pytest_asyncio.fixture
async def card_env(tmp_path, monkeypatch, scratch_campaign):
    """A scratch campaign, a temp characters folder and a pinned default session."""
    await Database.init()
    monkeypatch.setattr(Config, "SESSION_ID", scratch_campaign)
    monkeypatch.setattr(portraits, "CHARACTERS_ROOT", tmp_path / "characters")
    (tmp_path / "characters").mkdir()
    return scratch_campaign


async def _import(session_id: int, fields: dict, **over) -> str:
    kwargs = {"force": False, "dry_run": False, "queue_portrait": False, **over}
    return await icc.import_card(session_id, fields, **kwargs)


async def _row(session_id: int) -> dict:
    return dict(await Database.fetchrow(
        "SELECT id, description, appearance, background, traits FROM maya_rp.characters"
        " WHERE session_id=$1 AND name=$2", session_id, NAME))


async def test_a_reimport_fills_an_empty_field(card_env):
    """A re-import fills an empty field. The UPDATE placeholders must be gapless, or asyncpg raises."""
    await _import(card_env, _fields())
    await Database.execute(
        "UPDATE maya_rp.characters SET appearance='' WHERE session_id=$1 AND name=$2", card_env, NAME)

    outcome = await _import(card_env, _fields())

    assert outcome.startswith("updated 1 field(s)")
    assert (await _row(card_env))["appearance"], "the empty appearance was not filled"


async def test_a_forced_reimport_updates_every_field_and_binds_traits_as_json(card_env):
    await _import(card_env, _fields())

    outcome = await _import(
        card_env, _fields(description="A new line. She wears red.", personality="bold, loud"), force=True)

    row = await _row(card_env)
    assert outcome.startswith("updated 4 field(s)")
    assert row["description"] == "A new line. She wears red."
    assert json.loads(row["traits"]) == ["bold", "loud"]


async def test_a_reimport_keeps_a_hand_written_intro(card_env):
    await _import(card_env, _fields())
    intro = portraits.character_dir(NAME) / "intro.md"
    assert "She looks up" in intro.read_text(encoding="utf-8"), "a fresh import writes the first message"
    intro.write_text("# Hand written\n\nMy own entrance.\n", encoding="utf-8")

    await _import(card_env, _fields(first_mes="A different first message."))

    assert intro.read_text(encoding="utf-8") == "# Hand written\n\nMy own entrance.\n"


async def test_force_does_not_touch_the_intro(card_env):
    await _import(card_env, _fields())
    intro = portraits.character_dir(NAME) / "intro.md"
    intro.write_text("# Hand written\n", encoding="utf-8")

    await _import(card_env, _fields(first_mes="A different first message."), force=True)

    assert intro.read_text(encoding="utf-8") == "# Hand written\n"


async def test_force_intro_replaces_the_intro(card_env):
    await _import(card_env, _fields())
    intro = portraits.character_dir(NAME) / "intro.md"
    intro.write_text("# Hand written\n", encoding="utf-8")

    await _import(card_env, _fields(first_mes="A different first message."), force_intro=True)

    assert "A different first message." in intro.read_text(encoding="utf-8")


async def test_a_blank_intro_is_filled(card_env):
    await _import(card_env, _fields())
    intro = portraits.character_dir(NAME) / "intro.md"
    intro.write_text("  \n\n", encoding="utf-8")

    await _import(card_env, _fields(first_mes="Filled in."))

    assert "Filled in." in intro.read_text(encoding="utf-8")


def _main_env(monkeypatch, tmp_path, argv_tail):
    """Run `icc.main` with the pool and the import faked. Returns what `import_card` received."""
    card = tmp_path / "card.json"
    card.write_text(json.dumps({"name": NAME, "description": "A ranger."}), encoding="utf-8")
    seen: dict = {}

    async def fake_import(session_id, fields, **kwargs):
        seen["session"] = session_id
        seen.update(kwargs)
        return "ok"

    async def noop(*_a, **_k):
        return None

    monkeypatch.setattr(icc, "import_card", fake_import)
    monkeypatch.setattr(Database, "init", noop)
    monkeypatch.setattr(Database, "close", noop)
    monkeypatch.setattr(sys, "argv", ["import_character_card", "--card", str(card), *argv_tail])
    return seen


def _other(scratch: int) -> int:
    return 900 + (scratch - 900 + 1) % 100


async def test_the_default_session_resolves_through_require_session(
        monkeypatch, tmp_path, scratch_session):
    """The default session comes from `require_session`, not `Config.SESSION_ID`. Another scratch id plays the stale one."""
    monkeypatch.setattr(Config, "SESSION_ID", _other(scratch_session))
    monkeypatch.setenv("RP_SESSION", str(scratch_session))
    seen = _main_env(monkeypatch, tmp_path, [])

    assert await icc.main() == 0
    assert seen["session"] == scratch_session


async def test_an_explicit_session_wins_over_the_environment(monkeypatch, tmp_path, scratch_session):
    explicit = _other(scratch_session)
    monkeypatch.setattr(Config, "SESSION_ID", scratch_session)
    monkeypatch.setenv("RP_SESSION", str(scratch_session))
    seen = _main_env(monkeypatch, tmp_path, ["--session", str(explicit)])

    assert await icc.main() == 0
    assert seen["session"] == explicit


async def test_no_resolvable_session_is_an_error_not_a_default(monkeypatch, tmp_path, scratch_session):
    monkeypatch.setattr(Config, "SESSION_ID", scratch_session)
    monkeypatch.delenv("RP_SESSION", raising=False)
    monkeypatch.setattr(session, "ACTIVE_ARC", tmp_path / "no_such_arc")
    monkeypatch.setattr(session, "_maintenance_active", lambda: False)
    seen = _main_env(monkeypatch, tmp_path, [])

    with pytest.raises(RuntimeError, match="no session resolved"):
        await icc.main()
    assert "session" not in seen, "an import ran without a session"


async def test_force_intro_reaches_import_card(monkeypatch, tmp_path, scratch_session):
    monkeypatch.setenv("RP_SESSION", str(scratch_session))
    seen = _main_env(monkeypatch, tmp_path, ["--force-intro"])

    await icc.main()

    assert seen["force_intro"] is True and seen["force"] is False


# ── scene_selector ───────────────────────────────────────────────────────────

NOVEL = ("# Book\n\nPreface.\n\n"
         "## Blok A\n\nAlpha body.\n\n"
         "## Blok C\n\nOld body.\n\n"
         "## Blok D\n\nDelta body.\n")


@pytest.fixture
def novel(tmp_path, monkeypatch):
    root = tmp_path / "adventures"
    path = root / "novel" / "book.md"
    path.parent.mkdir(parents=True)
    path.write_text(NOVEL, encoding="utf-8")
    monkeypatch.setattr(ss, "NOVEL_ROOTS", (root,))
    monkeypatch.setattr(ss, "VAULT", tmp_path)
    monkeypatch.setattr(ss, "BACKUP_DIR", tmp_path / "archive")
    return path


def _rewrite(tmp_path, text: str, scene: str = "Blok C") -> int:
    draft = tmp_path / "draft.md"
    draft.write_text(text, encoding="utf-8")
    return ss.cmd_rewrite(argparse.Namespace(
        novel="book", scene=scene, level=2, from_file=str(draft), dry_run=False))


@pytest.mark.parametrize("draft", [
    "The door opened.\nSecond line.\n",
    "\nThe door opened.\nSecond line.\n",
    "\n\nThe door opened.\nSecond line.\n\n\n",
])
def test_a_rewrite_keeps_the_heading_on_its_own_line(novel, tmp_path, draft):
    """The heading match stops before its newline. The rewrite must write the line break itself."""
    assert _rewrite(tmp_path, draft) == 0

    text = novel.read_text(encoding="utf-8")
    assert "## Blok CThe" not in text
    assert "## Blok C\n\nThe door opened.\nSecond line.\n\n## Blok D\n" in text
    assert [s["title"] for s in ss.scenes(novel)] == ["Blok A", "Blok C", "Blok D"]


def test_a_rewrite_leaves_the_other_scenes_alone(novel, tmp_path):
    _rewrite(tmp_path, "New.\n")

    text = novel.read_text(encoding="utf-8")
    assert text.startswith("# Book\n\nPreface.\n\n## Blok A\n\nAlpha body.\n\n## Blok C\n\nNew.\n\n")
    assert text.endswith("## Blok D\n\nDelta body.\n")


def test_rewriting_the_last_scene_keeps_its_heading_on_its_own_line(novel, tmp_path):
    assert _rewrite(tmp_path, "Closing line.", scene="Blok D") == 0

    assert novel.read_text(encoding="utf-8").endswith("## Blok D\n\nClosing line.\n\n")


def test_a_rewrite_archives_the_original(novel, tmp_path):
    _rewrite(tmp_path, "New.\n")

    archived = list((tmp_path / "archive").glob("book-*.md"))
    assert len(archived) == 1
    assert archived[0].read_text(encoding="utf-8") == NOVEL


# ── turn_watcher ─────────────────────────────────────────────────────────────

SESSION_A, SESSION_B = 901, 902


def _turn(id_: int) -> dict:
    return {"id": id_, "role": "assistant", "text_content": "x", "created_at": None}


@pytest.fixture
def wm(tmp_path, monkeypatch):
    """A temp watermark location and fakes for the database read, the tracker and the freeze door."""
    monkeypatch.setattr(tw, "WATERMARK", tmp_path / "watermark.json")
    monkeypatch.setattr(tw, "_session_is_writable", lambda _sid: True)
    state = {"turns": [], "after": [], "processed": []}

    async def fake_new_turns(_label, after, limit):
        state["after"].append(after)
        return [t for t in state["turns"] if t["id"] > after][:limit]

    async def fake_process(_sid, turn, *, write):
        state["processed"].append(turn["id"])
        return {"turn": turn["id"], "chars": 1, "scene_declared": False, "scene_corrections": 0,
                "scene_moved": False, "terms_found": 0, "terms_written": 0}

    monkeypatch.setattr(tw, "new_turns", fake_new_turns)
    monkeypatch.setattr(tw, "process_one", fake_process)
    return state


async def _pass(session_id: int, *, apply: bool, label: str = "x") -> int:
    return await tw.once(session_id=session_id, label=label, apply=apply, limit=50, skip_failed=False)


def test_each_session_and_label_has_its_own_file(wm):
    paths = {tw.watermark_path(SESSION_A, "x"), tw.watermark_path(SESSION_B, "x"),
             tw.watermark_path(SESSION_A, "y"), tw.watermark_path(SESSION_A, "a/b"),
             tw.watermark_path(SESSION_A, "a_b")}

    assert len(paths) == 5, "two keys share a file"
    assert all(p.parent == tw.WATERMARK.parent for p in paths), "a label escaped the directory"


def test_a_cursor_does_not_cross_sessions_or_labels(wm):
    tw.write_watermark({"last_id": 100, "processed": 3}, SESSION_A, "x")

    assert tw.read_watermark(SESSION_A, "x")["last_id"] == 100
    assert tw.read_watermark(SESSION_B, "x")["last_id"] == 0
    assert tw.read_watermark(SESSION_A, "y")["last_id"] == 0


async def test_a_pass_reads_and_writes_only_its_own_cursor(wm):
    tw.write_watermark({"last_id": 100, "processed": 0}, SESSION_A, "x")
    wm["turns"] += [_turn(50), _turn(101), _turn(102)]

    assert await _pass(SESSION_B, apply=True) == 0

    assert wm["after"] == [0], "session B started from session A's cursor"
    assert wm["processed"] == [50, 101, 102]
    assert tw.read_watermark(SESSION_B, "x")["last_id"] == 102
    assert tw.read_watermark(SESSION_A, "x")["last_id"] == 100, "session B moved session A's cursor"


async def test_a_dry_run_reads_the_cursor_of_its_own_session(wm):
    tw.write_watermark({"last_id": 100, "processed": 0}, SESSION_A, "x")
    wm["turns"] += [_turn(101)]

    await _pass(SESSION_A, apply=False)

    assert wm["after"] == [100]
    assert tw.read_watermark(SESSION_A, "x")["last_id"] == 100


def test_the_shared_file_belongs_to_the_session_it_was_written_for(wm, monkeypatch):
    """The shared file predates per-session cursors. Its session reads it, so a restart replays nothing."""
    monkeypatch.setattr(tw, "LEGACY_SESSION", SESSION_A)
    shared = tw.WATERMARK
    shared.write_text(json.dumps({"last_id": 232, "processed": 40, "updated_at": "t"}), encoding="utf-8")

    assert tw.read_watermark(SESSION_A, tw.DEFAULT_LABEL)["last_id"] == 232
    assert tw.read_watermark(SESSION_B, tw.DEFAULT_LABEL)["last_id"] == 0
    assert tw.read_watermark(SESSION_A, "other")["last_id"] == 0

    tw.write_watermark({"last_id": 240, "processed": 41}, SESSION_A, tw.DEFAULT_LABEL)

    assert tw.read_watermark(SESSION_A, tw.DEFAULT_LABEL)["last_id"] == 240
    assert json.loads(shared.read_text(encoding="utf-8"))["last_id"] == 232, "the shared file was modified"


CORRUPT = ["{not json", "", "[]", "null", '{"last_id": "7"}', '{"last_id": -1}', '{"last_id": true}',
           '{"last_id": 1.5}', '{"processed": 3}']


@pytest.mark.parametrize("content", CORRUPT)
def test_a_corrupt_watermark_raises(wm, content):
    path = tw.watermark_path(SESSION_A, "x")
    path.write_text(content, encoding="utf-8")

    with pytest.raises(tw.WatermarkCorrupt):
        tw.read_watermark(SESSION_A, "x")


@pytest.mark.parametrize("content", CORRUPT)
@pytest.mark.parametrize("apply", [True, False])
async def test_a_corrupt_watermark_processes_nothing_and_exits_3(wm, content, apply):
    """A corrupt cursor must not start at 0. Starting at 0 replays every turn through the tracker."""
    path = tw.watermark_path(SESSION_A, "x")
    path.write_text(content, encoding="utf-8")
    wm["turns"] += [_turn(1), _turn(2), _turn(3)]

    assert await _pass(SESSION_A, apply=apply) == 3

    assert wm["processed"] == [], "turns were processed from a guessed cursor"
    assert wm["after"] == [], "the database was read from a guessed cursor"
    assert path.read_text(encoding="utf-8") == content, "the corrupt file was overwritten"


async def test_a_corrupt_legacy_file_is_refused_too(wm, monkeypatch):
    monkeypatch.setattr(tw, "LEGACY_SESSION", SESSION_A)
    tw.WATERMARK.write_text("{not json", encoding="utf-8")
    wm["turns"] += [_turn(1)]

    assert await _pass(SESSION_A, apply=True, label=tw.DEFAULT_LABEL) == 3
    assert wm["processed"] == []


async def test_a_corrupt_file_of_one_session_does_not_stop_another(wm):
    tw.watermark_path(SESSION_A, "x").write_text("{not json", encoding="utf-8")
    wm["turns"] += [_turn(1)]

    assert await _pass(SESSION_B, apply=True) == 0
    assert wm["processed"] == [1]


async def test_reset_recovers_a_corrupt_file(wm, monkeypatch, capsys):
    path = tw.watermark_path(SESSION_A, "x")
    path.write_text("{not json", encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["turn_watcher", "--status", "--session", str(SESSION_A),
                                      "--label", "x"])
    assert await tw.main() == 3
    assert str(path) in capsys.readouterr().out

    monkeypatch.setattr(sys, "argv", ["turn_watcher", "--reset", "--session", str(SESSION_A),
                                      "--label", "x"])
    assert await tw.main() == 0
    assert tw.read_watermark(SESSION_A, "x")["last_id"] == 0
    assert tw.read_watermark(SESSION_B, "x")["last_id"] == 0


# ── char_query ───────────────────────────────────────────────────────────────

def test_like_pattern_escapes_its_metacharacters():
    assert cq._like("a%b_c\\d") == "%a\\%b\\_c\\\\d%"
    assert cq._like("plain") == "%plain%"


@pytest_asyncio.fixture
async def cq_env(monkeypatch, scratch_campaign):
    await Database.init()
    monkeypatch.setattr(Config, "SESSION_ID", scratch_campaign)
    monkeypatch.setenv("RP_SESSION", str(scratch_campaign))
    return scratch_campaign


async def test_every_like_escapes_and_binds_an_escaped_pattern(cq_env, monkeypatch):
    calls = []

    async def fake_fetch(sql, *params):
        calls.append((sql, params))
        return []

    monkeypatch.setattr(Database, "fetch", fake_fetch)

    await cq.resolve_loc("10%_x", cq_env)
    await cq.resolve_ship("50%", cq_env)

    likes = [(sql, params) for sql, params in calls if " LIKE " in sql]
    assert len(likes) == 3
    for sql, params in likes:
        assert sql.count("LIKE") == sql.count("ESCAPE '\\'"), sql
        assert not any(p == "%10%_x%" or p == "%50%%" for p in params), params
    patterns = {p for _sql, params in likes for p in params if isinstance(p, str)}
    assert patterns == {"%10\\%\\_x%", "%50\\%%"}


async def test_a_percent_sign_matches_nothing(cq_env):
    """`%` and `_` match themselves. The queries run here, so Postgres checks the ESCAPE clause."""
    await Database.execute(
        "INSERT INTO maya_rp.territory (session_id, system_name, controlling_faction)"
        " VALUES ($1, 'Alpha Station', 'None')", cq_env)

    assert (await cq.resolve_loc("%", cq_env))["ok"] is False
    assert (await cq.resolve_loc("alpha_station", cq_env))["kind"] != "name", "`_` matched a space"
    assert (await cq.resolve_ship("%", cq_env))["ok"] is False
    found = await cq.resolve_loc("alpha stat", cq_env)
    assert found["kind"] == "name" and found["territories"][0]["system_name"] == "Alpha Station"


async def test_the_coordinate_lookup_reads_the_territory_of_the_session(cq_env, monkeypatch, tmp_path):
    """The lookup reads the session's territory rows. A file at the old backup path must change nothing."""
    decoy = tmp_path / "territory.json"
    decoy.write_text(json.dumps([{"system_name": "740-280", "controlling_faction": "Decoy"}]),
                     encoding="utf-8")
    monkeypatch.setattr(cq, "TERR_1000_FILE", str(decoy), raising=False)
    for name, faction in (("741-280", "Real"), ("100-100", "Far"), ("Mastika", "Named")):
        await Database.execute(
            "INSERT INTO maya_rp.territory (session_id, system_name, controlling_faction)"
            " VALUES ($1, $2, $3)", cq_env, name, faction)

    result = await cq.resolve_loc("740,280", cq_env)

    assert result["grid"] == "1000"
    names = [s["system_name"] for s in result["systems"]]
    assert names == ["741-280", "100-100"], names
    assert result["systems"][0]["controlling_faction"] == "Real"
    assert (result["systems"][0]["x"], result["systems"][0]["y"]) == (741, 280)
    assert "population" in result["systems"][0]


async def test_the_coordinate_query_is_scoped_to_the_session(cq_env, monkeypatch):
    calls = []

    async def fake_fetch(sql, *params):
        calls.append((sql, params))
        return []

    monkeypatch.setattr(Database, "fetch", fake_fetch)

    await cq.resolve_loc("740,280", cq_env)

    territory = [c for c in calls if "maya_rp.territory" in c[0]]
    assert territory and all("session_id=$1" in sql and params[0] == cq_env for sql, params in territory)


ROSTER_TEXT = (
    "# header\n"
    "aliases:\n"
    "  forge: Arianna (The Forge)\n"
    "  oracle: Aeliana → Seer\n"
    "groups:\n"
    "  queens:\n"
    "    - Arianna\n"
    "    - Callista\n"
)


@pytest.fixture
def roster_file(tmp_path, monkeypatch):
    path = tmp_path / "data" / "roster.yaml"
    path.parent.mkdir()
    path.write_text(ROSTER_TEXT, encoding="utf-8")
    path.chmod(0o644)
    monkeypatch.setattr(cq, "ROSTER_FILE", str(path))
    monkeypatch.setenv("RP_SESSION", str(SESSION_A))
    return path


def test_a_crash_while_saving_keeps_the_old_roster(roster_file, monkeypatch):
    """A save writes through a temp file. A crash mid-save must leave a roster that still loads."""
    roster = cq._load_roster()

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(cq.yaml, "safe_dump", boom)
    with pytest.raises(OSError):
        cq._save_roster(roster)

    assert roster_file.read_text(encoding="utf-8") == ROSTER_TEXT
    assert [p.name for p in roster_file.parent.iterdir()] == ["roster.yaml"], "a temp file was left behind"


def test_a_save_keeps_the_mode_the_text_and_the_groups(roster_file):
    roster = cq._load_roster()

    cq._save_roster(roster)

    assert roster_file.stat().st_mode & 0o777 == 0o644
    again = cq._load_roster(SESSION_A)
    assert again["aliases"] == {"forge": "Arianna (The Forge)", "oracle": "Aeliana → Seer"}
    assert again["groups"] == {"queens": ["Arianna", "Callista"]}


def test_aliases_belong_to_one_session(roster_file):
    mine = cq._load_roster(SESSION_A)
    cq.add_alias(mine, "Kitty", "Kira Blackwood")
    cq._save_roster(mine)

    assert cq._load_roster(SESSION_A)["aliases"]["kitty"] == "Kira Blackwood"
    assert "kitty" not in cq._load_roster(SESSION_B)["aliases"]
    assert cq._load_roster(SESSION_B)["aliases"]["forge"] == "Arianna (The Forge)", "shared aliases apply"
    saved = cq.yaml.safe_load(roster_file.read_text(encoding="utf-8"))
    assert saved["session_aliases"] == {"901": {"kitty": "Kira Blackwood"}}
    assert "kitty" not in saved["aliases"], "a session alias leaked into the shared map"


def test_a_session_alias_overrides_a_shared_one(roster_file):
    mine = cq._load_roster(SESSION_A)
    cq.add_alias(mine, "forge", "Someone Else")
    cq._save_roster(mine)

    assert cq._load_roster(SESSION_A)["aliases"]["forge"] == "Someone Else"
    assert cq._load_roster(SESSION_B)["aliases"]["forge"] == "Arianna (The Forge)"


def test_removing_an_alias_touches_only_this_session(roster_file):
    mine = cq._load_roster(SESSION_A)
    cq.add_alias(mine, "kitty", "Kira")
    cq.add_alias(mine, "forge", "Someone Else")
    cq._save_roster(mine)

    mine = cq._load_roster(SESSION_A)
    assert cq.remove_alias(mine, "kitty") == "removed"
    assert cq.remove_alias(mine, "kitty") == "absent"
    assert cq.remove_alias(mine, "oracle") == "shared", "a shared alias must stay"
    assert cq.remove_alias(mine, "forge") == "removed"
    assert mine["aliases"]["forge"] == "Arianna (The Forge)", "the shared alias shows again"
    cq._save_roster(mine)

    assert "session_aliases" not in cq.yaml.safe_load(roster_file.read_text(encoding="utf-8"))
    assert cq._load_roster(SESSION_B)["aliases"]["oracle"] == "Aeliana → Seer"


def test_an_alias_needs_a_session(roster_file, monkeypatch):
    def unresolved():
        raise RuntimeError("no session resolved")

    monkeypatch.setattr(cq, "_call_session", unresolved)
    roster = cq._load_roster()

    assert roster["session"] is None
    assert roster["aliases"]["forge"] == "Arianna (The Forge)", "a read falls back to the shared aliases"
    with pytest.raises(RuntimeError, match="no session resolved"):
        cq.add_alias(roster, "kitty", "Kira")


def test_the_default_roster_session_is_the_resolved_one(roster_file, monkeypatch):
    monkeypatch.setenv("RP_SESSION", str(SESSION_A))
    mine = cq._load_roster(SESSION_A)
    cq.add_alias(mine, "kitty", "Kira")
    cq._save_roster(mine)

    assert cq._load_roster()["aliases"]["kitty"] == "Kira"
    monkeypatch.setenv("RP_SESSION", str(SESSION_B))
    assert "kitty" not in cq._load_roster()["aliases"]


def test_the_roster_path_is_not_the_live_file(roster_file):
    assert os.path.abspath(cq.ROSTER_FILE) != os.path.abspath(
        os.path.join(os.path.dirname(cq.__file__), "..", "data", "roster.yaml"))
