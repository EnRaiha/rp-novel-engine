#!/usr/bin/env python3
"""Tests for the kilo_bridge lore_pack action (2026-08-15).

lore_pack bundles wiki lore + novel recall + character card + scene context
in one JSON call so prose generation can't contradict canon.

Full live test requires PG + Ollama — run manually via:
  python3 scripts/kilo_bridge.py lore_pack '{"query": "Nadia Voss"}'
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.kilo_bridge import handle


async def test_lore_pack_missing_query():
    """No query → clean error dict, status ok (never a crash)."""
    result = await handle("lore_pack", {})
    assert result["status"] == "ok"
    assert "error" in result["data"]


async def test_lore_pack_is_action_registered():
    """The bridge must route lore_pack (not fall through to error)."""
    result = await handle("lore_pack", {})
    assert result["action"] == "lore_pack"


async def test_novel_recall_missing_query():
    """novel_recall without query must not crash the bridge."""
    result = await handle("novel_recall", {})
    assert result["status"] == "ok"
    assert "error" in result["data"]
