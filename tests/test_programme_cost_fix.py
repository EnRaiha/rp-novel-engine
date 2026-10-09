"""Regression tests for modules/programme_cost.py and `cli.py programme quote`. No database access."""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.programme_cost as cost  # noqa: E402


def _quote(*flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/cli.py", "programme", "quote", "--tier=5", *flags],
        cwd=ROOT,
        env={**os.environ, "DEEPSEEK_API_KEY": os.environ.get("DEEPSEEK_API_KEY", "test-key")},
        capture_output=True, text=True, timeout=300)


def test_a_new_programme_row_adds_nothing():
    assert cost.advance(100, None, 20, 3, 1825) == 100


def test_the_credit_caps_the_lab_count():
    assert cost.target_credits(5, 99) == cost.target_credits(5, cost.LAB_LEVEL_CAP) == 42500


def test_quote_reads_the_lab_flag():
    with_lab = _quote("--lab=1")
    assert with_lab.returncode == 0, with_lab.stderr
    assert "38,500 C" in with_lab.stdout, with_lab.stdout

    no_lab = _quote()
    assert no_lab.returncode == 0, no_lab.stderr
    assert "42,500 C" in no_lab.stdout, no_lab.stdout
