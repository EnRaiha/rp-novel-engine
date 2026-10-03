#!/usr/bin/env python3
"""Review of `core/log.py`.

One defect: the file handler chose `tick_YYYYMMDD.log` once, at import. A process that outlived
midnight kept appending to the previous day's file and the new day's file was never created, so a
day's log could be missing everything the process did after it rolled over. The ticker on the other
host runs for days, and the orchestrator's own log is read back when a module misbehaves.

The date is now asked for per record. `core.log.datetime` is monkeypatched here rather than the
clock, so a test can cross midnight without waiting for it.
"""
from __future__ import annotations

import logging
import pathlib
import sys
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import log  # noqa: E402


class _FrozenClock:
    """Stands in for `core.log.datetime`; `now()` answers whatever the test set."""

    current = datetime(2026, 10, 3, 23, 59, 0)

    @classmethod
    def now(cls):
        return cls.current


def _attach(handler: logging.Handler, name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler.setFormatter(logging.Formatter("%(message)s"))
    return logger


def test_the_file_handler_follows_the_date_across_midnight(tmp_path, monkeypatch):
    monkeypatch.setattr(log.Config, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(log, "datetime", _FrozenClock)
    handler = log._DatedFileHandler()
    logger = _attach(handler, "rp-review-log-rollover")
    try:
        _FrozenClock.current = datetime(2026, 10, 3, 23, 59, 0)
        logger.info("before midnight")
        _FrozenClock.current = datetime(2026, 10, 4, 0, 0, 30)
        logger.info("after midnight")
    finally:
        logger.removeHandler(handler)
        handler.close()

    day_one = tmp_path / "tick_20261003.log"
    day_two = tmp_path / "tick_20261004.log"
    assert day_one.exists(), "the first day's file is missing"
    assert day_two.exists(), "the handler kept writing into yesterday's file"
    assert day_one.read_text() == "before midnight\n"
    assert day_two.read_text() == "after midnight\n"


def test_the_module_helpers_land_in_the_days_file(tmp_path, monkeypatch):
    """The contract `info` claims: one file per day, named for the day it was written on."""
    monkeypatch.setattr(log.Config, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(log, "datetime", _FrozenClock)
    _FrozenClock.current = datetime(2026, 10, 3, 12, 0, 0)
    handler = log._DatedFileHandler()
    log._log.addHandler(handler)
    try:
        log.info("review", "written by the module helper")
    finally:
        log._log.removeHandler(handler)
        handler.close()
    assert "written by the module helper" in (tmp_path / "tick_20261003.log").read_text()


def test_a_record_written_twice_does_not_open_a_new_file(tmp_path, monkeypatch):
    """The date check must not roll when the day has not changed."""
    monkeypatch.setattr(log.Config, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(log, "datetime", _FrozenClock)
    _FrozenClock.current = datetime(2026, 10, 3, 8, 0, 0)
    handler = log._DatedFileHandler()
    logger = _attach(handler, "rp-review-log-same-day")
    base = None
    try:
        logger.info("one")
        base = handler.baseFilename
        logger.info("two")
    finally:
        logger.removeHandler(handler)
        handler.close()
    assert handler.baseFilename == base, "the handler reopened its file for the same day"
    assert (tmp_path / "tick_20261003.log").read_text() == "one\ntwo\n"
