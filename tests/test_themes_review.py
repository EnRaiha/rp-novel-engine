"""Module review tests for modules/themes.py.

Defect covered:

1. `detect` parsed `events.tags` with a bare `except:` that swallowed any error
   into an empty list, so a malformed tag payload was counted as an event with
   no tags and nobody could tell. The handler is narrowed and it logs now.

Checked and found correct, so the row is not silent about what it looked at:
`events.tags` is jsonb and the str branch decodes it; a list of tags joins
cleanly; the event window is seven days and session-scoped; the profile bonuses
come from the session's own player profile; only themes scoring 2 or more are
returned, at most two; the instruction picks one beat per domain and returns ""
when nothing resonates; and `run_tick` persists the detected themes through an
upsert on session_id.

No database: every test drives a fake Database.
"""
from __future__ import annotations

import json

import pytest

import modules.themes as themes


class FakeDB:
    def __init__(self, fetch=None, execute_tag="INSERT 0 1"):
        self.fetch_rows = fetch if fetch is not None else []
        self.execute_tag = execute_tag
        self.calls = []

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        return self.fetch_rows

    async def execute(self, sql, *args):
        self.calls.append(("execute", " ".join(sql.split()), args))
        return self.execute_tag

    def sql(self, kind=None):
        return [c[1] for c in self.calls if kind is None or c[0] == kind]

    def args_for(self, needle, kind=None):
        return [c[2] for c in self.calls
                if needle in c[1] and (kind is None or c[0] == kind)]


def _install(monkeypatch, fake, profile=None):
    for name in ("fetch", "execute"):
        monkeypatch.setattr("modules.themes.Database." + name, getattr(fake, name))

    async def get_profile(session_id):
        return profile or {"distribution": {}}

    monkeypatch.setattr("core.player_profile.get_profile", get_profile)
    return fake


def _event(title, description="", tags="[]"):
    return {"title": title, "description": description, "tags": tags}


# ── 1. Malformed tags are named, not swallowed ───────────────────────────

async def test_malformed_tag_json_is_logged_and_the_event_still_counts(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.themes.info", lambda mod, msg: seen.append(msg))
    rows = [_event("Betrayal and loyalty at the gate", tags="{not json")]
    _install(monkeypatch, FakeDB(fetch=rows))

    out = await themes.detect(5)

    assert any(t["theme"] == "trust" for t in out), out     # "betray" is a trust keyword
    assert any("not JSON" in m for m in seen), seen


async def test_a_tag_list_still_counts_its_keywords(monkeypatch):
    rows = [_event("Quiet report", tags=["freedom", "escape", "loss", "death"])]
    _install(monkeypatch, FakeDB(fetch=rows))

    out = await themes.detect(5)

    assert {t["theme"] for t in out} == {"freedom", "loss"}, out


async def test_jsonb_tags_decoded_from_text_count_too(monkeypatch):
    rows = [_event("Quiet report", tags=json.dumps(["freedom", "escape", "loss", "death"]))]
    _install(monkeypatch, FakeDB(fetch=rows))

    out = await themes.detect(5)

    assert {t["theme"] for t in out} == {"freedom", "loss"}, out


# ── Contract the module claims ───────────────────────────────────────────

async def test_only_themes_at_or_above_the_threshold_come_back(monkeypatch):
    rows = [_event("A single mention of trust")]
    _install(monkeypatch, FakeDB(fetch=rows))

    assert await themes.detect(5) == []


async def test_at_most_two_themes_and_the_strongest_first(monkeypatch):
    rows = [_event("trust trust trust loyalty", tags=[]),
            _event("loss loss loss death", tags=[]),
            _event("freedom freedom escape", tags=[])]
    _install(monkeypatch, FakeDB(fetch=rows))

    out = await themes.detect(5)

    assert len(out) == 2
    assert out[0]["score"] >= out[1]["score"]
    # three themes tie at 2; the KW declaration order breaks the tie, so the
    # two oldest-declared themes are the pair that comes back
    assert {t["theme"] for t in out} == {"trust", "loss"}, out


async def test_the_profile_bonus_lifts_a_theme(monkeypatch):
    _install(monkeypatch, FakeDB(fetch=[]), profile={"distribution": {"mercy": 20}})

    out = await themes.detect(5)

    assert out == [{"theme": "freedom", "score": 3}]


async def test_the_events_window_is_seven_days_and_session_scoped(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[]))

    await themes.detect(5)

    sql = fake.sql("fetch")[0]
    assert "session_id=$1" in sql and "INTERVAL'7 days'" in sql
    assert fake.args_for("maya_rp.events", "fetch")[0] == (5,)


async def test_an_empty_theme_set_renders_no_instruction(monkeypatch):
    _install(monkeypatch, FakeDB(fetch=[]))

    assert await themes.get_instruction(5) == ""


async def test_the_instruction_names_every_domain_for_each_theme(monkeypatch):
    rows = [_event("trust trust trust loyalty", tags=[])]
    _install(monkeypatch, FakeDB(fetch=rows))
    monkeypatch.setattr(themes.random, "choice", lambda seq: seq[0])

    out = await themes.get_instruction(5)

    assert out.startswith("[ACTIVE THEMES]")
    assert "TRUST" in out
    for domain in ("combat", "romance", "political", "exploration"):
        assert f"    {domain}: " in out, out


async def test_run_tick_persists_the_detected_themes(monkeypatch):
    rows = [_event("trust trust trust loyalty", tags=[])]
    fake = _install(monkeypatch, FakeDB(fetch=rows))

    out = await themes.run_tick(5)

    assert out == {"active": ["trust"]}
    written = fake.args_for("INSERT INTO maya_rp.theme_state", "execute")[0]
    assert written[0] == 5
    assert json.loads(written[1]) == [{"theme": "trust", "score": 2}]


async def test_contract_every_theme_has_vocabulary_for_every_domain(monkeypatch):
    for theme, domains in themes.VOCAB.items():
        assert set(domains) == {"combat", "romance", "political", "exploration"}, theme
        for domain, beats in domains.items():
            assert beats, (theme, domain)
    for theme, kws in themes.KW.items():
        assert theme in themes.VOCAB, theme
        assert kws, theme
