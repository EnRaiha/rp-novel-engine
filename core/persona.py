#!/usr/bin/env python3
"""Persona fields — voice, lore, intro, play guide (fasa 6).

A persona is four files, not one prompt. The split follows what actually steers
a model: operational rules and few-shot examples in `voice.md`, backstory in
`lore.md` (never instructions), the opening beat in `intro.md`, and player-only
notes in `play-guide.md` that is never sent to the model.

    <TKG_PERSONA_ROOT>/<slug>/
        voice.md      register rules + few-shot exchanges (incl. boundary cases)
        lore.md       past events, trauma, lore — no instructions
        intro.md      opening interaction: formatting, sensory anchors, friction
        play-guide.md player-only: hooks, expectations, content notes

`build_block` returns the text the harness injects; `boundary_cases` returns the
lines a rule regression can turn into test fixtures.

@module core.persona
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Sequence

PERSONA_ROOT = Path(
    os.environ.get("TKG_PERSONA_ROOT", str(Path.home() / "Bumi-Hijau" / "adventures" / "tkg" / "personas"))
)

FIELDS = ("voice", "lore", "intro", "play-guide")
# The persona the campaign plays as, when the caller names none.
DEFAULT_SLUG = os.environ.get("TKG_PERSONA", "the-king")
# The opening beat is worth its tokens only while the session is still opening.
INTRO_MAX_AUDITS = 3
# The two fields that may reach the model: rules + examples, and the opening
# beat. `lore` is injected only through the lorebook (keyword-triggered) and
# `play-guide` never leaves the table.
INJECTED = ("voice", "intro")


def slugify(name: str) -> str:
    """A filesystem-safe slug for one persona name."""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug or "unknown"


def persona_dir(slug: str) -> Path:
    """Folder that owns one persona's four fields."""
    return PERSONA_ROOT / slugify(slug)


def field_path(slug: str, field: str) -> Path:
    """Path of one persona field file."""
    return persona_dir(slug) / f"{field}.md"


def read_field(slug: str, field: str) -> str:
    """One field's text, or an empty string when the file is absent."""
    path = field_path(slug, field)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def ensure_dirs(slug: str) -> dict[str, Path]:
    """Create one persona folder (and an assets/ subfolder for reference art)."""
    root = persona_dir(slug)
    (root / "assets").mkdir(parents=True, exist_ok=True)
    return {"root": root, "assets": root / "assets"}


def build_block(slug: str, *, audits: int | None = None) -> str:
    """The persona block the harness injects, or an empty string when absent.

    Voice first (rules and examples), then the opening beat — but only while the
    session is still opening (`audits <= INTRO_MAX_AUDITS`): after that the beat
    has done its work and would only spend tokens.
    """
    voice = read_field(slug, "voice")
    intro = read_field(slug, "intro") if audits is None or audits <= INTRO_MAX_AUDITS else ""
    parts: list[str] = []
    if voice:
        parts.append(voice)
    if intro:
        parts.append(f"## Opening beat\n\n{intro}")
    return "\n\n".join(parts).strip()


def boundary_cases(slug: str) -> list[str]:
    """Lines under a `## Boundary` heading in voice.md, one per case.

    Each line is written as `<what the player tries> => <what must not happen>`;
    a ruleset test can assert the second half is flagged.
    """
    voice = read_field(slug, "voice")
    if not voice:
        return []
    cases: list[str] = []
    in_section = False
    for line in voice.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("## "):
            in_section = stripped.lower().startswith("## boundary")
            continue
        if in_section and stripped and not stripped.startswith("#"):
            cases.append(stripped.lstrip("-* ").strip())
    return cases


def boundary_expectations(slug: str) -> list[dict[str, str]]:
    """Boundary cases as runnable assertions (M20).

    A case is written `"<literal line the player writes>" => <what must happen>`;
    the literal is what a ruleset regression feeds to the matcher, and the right
    side names the expected rule (or `flagged`) for the check.
    """
    cases: list[dict[str, str]] = []
    for raw in boundary_cases(slug):
        text, _, expect = raw.partition("=>")
        literal = text.strip().strip('"').strip("'").strip()
        if not literal:
            continue
        cases.append({"text": literal, "expect": expect.strip() or "flagged"})
    return cases


def check_boundaries(cases: Sequence[dict[str, str]], rules: Sequence[Any], layer: str = "dialogue") -> list[dict[str, Any]]:
    """Run each boundary case through the matcher (M20, pure: no writes).

    @param cases - `boundary_expectations` output.
    @param rules - compiled rules from the live ruleset.
    @param layer - surface to audit (dialogue by default).
    @returns one result per case: whether it flagged and whether the named rule matched.
    """
    from core import ooc

    results: list[dict[str, Any]] = []
    for case in cases:
        findings = ooc.audit_text(case["text"], rules, layer)
        matched = [finding.rule_id for finding in findings]
        expect = case["expect"]
        if expect in ("flagged", "flag", ""):
            ok = bool(findings)
        else:
            ok = expect in matched
        results.append({"text": case["text"], "expect": expect, "matched": matched, "ok": ok})
    return results


def load(slug: str) -> dict[str, Any]:
    """All four fields plus the derived block, for callers that need the set."""
    fields = {field: read_field(slug, field) for field in FIELDS}
    return {
        "slug": slugify(slug),
        "fields": fields,
        "block": build_block(slug),
        "boundary_cases": boundary_cases(slug),
        "has_play_guide": bool(fields["play-guide"]),
    }


def scaffold(slug: str, *, display_name: str = "", role: str = "", lore: str = "") -> dict[str, Path]:
    """Write any missing field file with a shape to fill in.

    Existing files are never overwritten: the human-written text is the asset.
    """
    paths = ensure_dirs(slug)
    name = display_name or slug
    templates = {
        "voice": (
            f"# {name} — Voice\n\n"
            "## Register rules\n\n"
            "- (operational rules only: lexicon limits, physical mannerisms, perspective)\n\n"
            f"## Few-shot exchanges\n\n"
            f"**Player:** …\n\n**{name}:** …\n\n"
            "## Boundary\n\n"
            "- player offers warmth => the answer stays clipped; no apology, no modern filler\n"
        ),
        "lore": f"# {name} — Lore\n\n{lore or '- (past events, trauma, lore — no instructions here)'}\n",
        "intro": (
            f"# {name} — Intro\n\n"
            f"- Formatting anchor: third person, sensory anchor (temperature, light, distance)\n"
            f"- Open mid-action with an unresolved tension that demands a response\n"
        ),
        "play-guide": (
            f"# {name} — Play guide (player only, never sent to the model)\n\n"
            "- Scenario hooks:\n- Expectations (pace, what distance means):\n- Content notes:\n"
        ),
    }
    written: dict[str, Path] = {}
    for field, text in templates.items():
        path = field_path(slug, field)
        if not path.exists():
            path.write_text(text, encoding="utf-8")
        written[field] = path
    return written
