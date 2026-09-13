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
_file_handler = logging.FileHandler(
    os.path.join(Config.LOG_DIR, f"tick_{datetime.now():%Y%m%d}.log")
)
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
