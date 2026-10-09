"""`RP_ENGINE_DSN` and `RP_ENGINE_DB` override the built-in DSN, and the fallback says so once.

No database: `_resolve_dsn` is pure (each test passes an environ dict) and the pool is a fake.
Assertions compare booleans, never a DSN, so a red run does not print the password.
"""
from __future__ import annotations

import asyncpg
import pytest
from urllib.parse import urlsplit

from core import db
from core.config import _DEFAULT_DSN, Config, _resolve_dsn
from core.db import Database

_PASSWORD = urlsplit(_DEFAULT_DSN).password


def test_the_default_dsn_carries_a_password_to_guard():
    assert _PASSWORD, "the leak checks below need a password to look for"


def test_no_environment_uses_the_built_in_dsn():
    dsn, used_default = _resolve_dsn({})
    same = dsn == _DEFAULT_DSN
    assert same
    assert used_default is True
    parts = urlsplit(dsn)
    assert parts.username == "rp_engine"
    assert parts.path == "/maya_memory"
    assert "search_path=maya_rp" in parts.query


@pytest.mark.parametrize("blank", [None, "", "  "])
def test_a_blank_dsn_counts_as_unset(blank):
    environ = {} if blank is None else {"RP_ENGINE_DSN": blank}
    dsn, used_default = _resolve_dsn(environ)
    same = dsn == _DEFAULT_DSN
    assert same
    assert used_default is True


def test_a_dsn_in_the_environment_replaces_the_default():
    assert _resolve_dsn({"RP_ENGINE_DSN": "postgres://u:p@h:1/x"}) == ("postgres://u:p@h:1/x", False)


def test_a_database_name_replaces_only_the_database():
    base = urlsplit(_DEFAULT_DSN)
    dsn, used_default = _resolve_dsn({"RP_ENGINE_DB": "rp_test_42"})
    parts = urlsplit(dsn)
    assert used_default is True
    assert parts.path == "/rp_test_42"
    assert parts.username == "rp_engine"
    same_password = parts.password == base.password
    assert same_password
    assert parts.netloc == base.netloc
    assert parts.query == "search_path=maya_rp,public"


def test_a_database_name_over_a_given_dsn_swaps_only_the_path():
    dsn, used_default = _resolve_dsn({"RP_ENGINE_DSN": "postgres://u:p@h:1/x?a=b", "RP_ENGINE_DB": "other"})
    assert (dsn, used_default) == ("postgres://u:p@h:1/other?a=b", False)


@pytest.mark.parametrize("bad", ["x; DROP", "1abc", "a-b", "a b", "a" * 64])
def test_a_bad_database_name_is_refused_without_the_dsn(bad):
    with pytest.raises(RuntimeError) as caught:
        _resolve_dsn({"RP_ENGINE_DB": bad})
    text = str(caught.value)
    leaked = _PASSWORD in text or "postgres://" in text
    assert not leaked
    assert "RP_ENGINE_DB" in text


def test_a_bad_database_name_over_a_given_dsn_leaks_nothing():
    with pytest.raises(RuntimeError) as caught:
        _resolve_dsn({"RP_ENGINE_DSN": "postgres://u:hunter2@h:1/x", "RP_ENGINE_DB": "a-b"})
    leaked = "hunter2" in str(caught.value) or "postgres://" in str(caught.value)
    assert not leaked


def test_config_follows_the_resolver():
    dsn, used_default = _resolve_dsn()
    same = Config.DSN == dsn
    assert same
    assert Config.DSN_FALLBACK_USED is used_default


def test_the_summary_never_prints_the_password():
    text = Config.summary()
    leaked = _PASSWORD in text
    assert not leaked
    assert urlsplit(Config.DSN).path.lstrip("/") in text


def test_the_summary_names_the_database_and_host_of_the_dsn(monkeypatch):
    monkeypatch.setattr(Config, "DSN", "postgres://u:s3cret-pw@h.example:6432/other_db?search_path=a")
    text = Config.summary()
    leaked = "s3cret-pw" in text
    assert not leaked
    assert "h.example:6432/other_db" in text


def test_the_summary_reads_a_dsn_without_credentials(monkeypatch):
    monkeypatch.setattr(Config, "DSN", "postgres://h.example:5432/other_db")
    assert "h.example:5432/other_db" in Config.summary()


async def _create_pool_with_warnings(monkeypatch, fallback_used: bool) -> list[str]:
    """Run `Database._create_locked` twice against a fake pool and return the `warn` messages."""
    messages: list[str] = []

    async def fake_create_pool(**kw):
        return object()

    from core import name_gen

    monkeypatch.setattr(asyncpg, "create_pool", fake_create_pool)
    monkeypatch.setattr(name_gen, "set_global_conn", lambda pool: None)
    monkeypatch.setattr(db, "warn", lambda module, msg: messages.append(msg))
    monkeypatch.setattr(Database, "pool", None)
    monkeypatch.setattr(Database, "_fallback_warned", False)
    monkeypatch.setattr(db.Config, "DSN_FALLBACK_USED", fallback_used)
    await Database._create_locked()
    Database.pool = None
    await Database._create_locked()
    return messages


async def test_the_fallback_is_said_once(monkeypatch):
    messages = await _create_pool_with_warnings(monkeypatch, fallback_used=True)
    assert len([m for m in messages if "RP_ENGINE_DSN" in m]) == 1, messages


async def test_no_warning_when_the_environment_names_a_dsn(monkeypatch):
    messages = await _create_pool_with_warnings(monkeypatch, fallback_used=False)
    assert messages == []
