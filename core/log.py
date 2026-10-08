"""Structured logging for all engines — replaces print() everywhere."""

import sys, json, logging, os
from datetime import datetime, timezone
from typing import Optional
from core.config import Config

_log = logging.getLogger("rp")
_log.setLevel(logging.DEBUG)
# StreamHandler → stderr (NOT stdout): kilo_bridge prints JSON on stdout and
# must never have log lines mixed in — stdout is the JSON contract channel.
# (2026-08-15 fix — lore_pack/novel_recall JSON was corrupted by log lines.)
_handler = logging.StreamHandler(sys.stderr)
_handler.setFormatter(
    logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s %(message)s", datefmt="%H:%M:%S"
    )
)
_log.handlers.clear()
_log.addHandler(_handler)
_log.propagate = False

# File handler — logs to tick_YYYYMMDD.log
os.makedirs(Config.LOG_DIR, exist_ok=True)


def _log_path() -> str:
    """The file for the day the record is written on, asked for per record.

    The path used to be chosen once, at import, so a process that outlived midnight kept appending
    to yesterday's `tick_YYYYMMDD.log` and the new day's file never appeared. The ticker on the
    other host has been running for days.
    """
    return os.path.join(Config.LOG_DIR, f"tick_{datetime.now():%Y%m%d}.log")


class _DatedFileHandler(logging.FileHandler):
    """A FileHandler that follows the date instead of freezing it at import."""

    def __init__(self) -> None:
        super().__init__(_log_path())

    def emit(self, record: logging.LogRecord) -> None:
        # The roll opens a file, so it can raise (disk full, permissions) on the first record after
        # midnight. It ran outside Handler.emit's own error handling, so the OSError escaped
        # warn()/info()/error() into business code. It goes to handleError like any failed write.
        try:
            if os.path.abspath(self.baseFilename) != os.path.abspath(_log_path()):
                self._roll_to_today()
        except Exception:  # noqa: BLE001 - logging must never raise into the caller
            self.handleError(record)
            return
        super().emit(record)

    def _roll_to_today(self) -> None:
        self.acquire()
        try:
            if self.stream:
                self.stream.close()
                self.stream = None
            self.baseFilename = os.path.abspath(_log_path())
            self.stream = self._open()
        finally:
            self.release()


_file_handler = _DatedFileHandler()
_file_handler.setFormatter(
    logging.Formatter("[%(asctime)s] %(levelname)s %(name)s %(message)s")
)
_log.addHandler(_file_handler)


def info(module: str, msg: str):
    _log.info(f"{module:<12} {msg}")


def warn(module: str, msg: str):
    _log.warning(f"{module:<12} {msg}")


def error(module: str, msg: str):
    _log.error(f"{module:<12} {msg}")
