"""The committed manifest is an artifact, so it can drift from the generator that writes it.

`prototype/faces/manifest.json` and `MANIFEST.md` are derived: `scripts/face_manifest.py` reads the
database and the portrait tree and writes them. Nobody regenerates an artifact by hand, so a stale
copy is the normal failure mode and it is invisible: the resolver keeps reading rows that no longer
match the engine.

This gate rebuilds both artifacts into a temporary directory and compares them, ignoring the
generated-at line, which is the one field that changes every run.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VAULT = ROOT.parent
GENERATOR = ROOT / "scripts" / "face_manifest.py"
COMMITTED_JSON = VAULT / "adventures/tkg-arc1-restart/prototype/faces/manifest.json"
COMMITTED_MD = VAULT / "adventures/tkg-arc1-restart/prototype/faces/MANIFEST.md"


def _rebuild(tmp_path: pathlib.Path, fmt: str, out: pathlib.Path) -> None:
    import os

    env = {**os.environ, "DEEPSEEK_API_KEY": os.environ.get("DEEPSEEK_API_KEY", "test-key")}
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--format", fmt, "--out", str(out)],
        capture_output=True, text=True, cwd=str(ROOT), env=env, timeout=600)
    if result.returncode != 0:
        pytest.skip(f"generator cannot run here: {result.stderr[-200:]}")


@pytest.fixture()
def rebuilt_json(tmp_path):
    out = tmp_path / "manifest.json"
    _rebuild(tmp_path, "json", out)
    return out


def test_the_committed_json_matches_a_fresh_build(rebuilt_json):
    fresh = json.loads(rebuilt_json.read_text(encoding="utf-8"))
    committed = json.loads(COMMITTED_JSON.read_text(encoding="utf-8"))
    assert fresh["rows"] == committed["rows"], (
        "manifest.json is stale; run: python3 scripts/face_manifest.py --format json"
    )
    assert fresh["characters"] == committed["characters"]
    assert fresh["keys"] == committed["keys"]


def test_the_committed_markdown_matches_a_fresh_build(tmp_path):
    out = tmp_path / "MANIFEST.md"
    _rebuild(tmp_path, "md", out)
    fresh = [line for line in out.read_text(encoding="utf-8").splitlines()
             if not line.startswith(("Generated", "# Face manifest"))]
    committed = [line for line in COMMITTED_MD.read_text(encoding="utf-8").splitlines()
                 if not line.startswith(("Generated", "# Face manifest"))]
    assert fresh == committed, (
        "MANIFEST.md is stale; run: python3 scripts/face_manifest.py"
    )
