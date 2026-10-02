#!/usr/bin/env python3
"""
Narrative Text Processor — enforces the DS Register on LLM output.
Replaces clinical/mechanical terms with the sensory-metaphor lexicon
from erotic-playbook.md §9, keeping prose consistent with the
established literary register.
"""
import re

# Clinical/Mechanical -> Literary/Metaphorical (DS Register)
REPLACEMENT_LEXICON = {
    # Anatomy -> Metaphor
    r"\bpenis\b": ["the dragon", "the core of him", "his heat"],
    r"\bvagina\b": ["the valley", "the lock", "her core"],
    r"\bbreasts\b": ["the swell of her chest", "golden curves", "softness"],
    r"\bnipples\b": ["peaks", "buds", "the rigid proof of her want"],

    # Acts -> Sensory descriptions
    r"\bintercourse\b": ["the joining", "the merging of souls", "the torrent"],
    r"\bsex\b": ["the union", "the heat", "the dance"],
    r"\borgasm\b": ["the breaking point", "the torrent", "the collapse", "the summit"],
    r"\bejaculat(ed|ing|es)?\b": ["spilled his heat", "gave way to the torrent", "found his release"],

    # Modifiers -> Playbook language
    r"\bthrust(s|ing|ed)?\b": ["moved with purpose", "drove the rhythm", "pressed deep"],
    r"\bmoan(ed|ing|s)?\b": ["cried out", "let slip a broken breath", "the sound of yielding"],
    r"\bclimax(ed|ing|es)?\b": ["shattered", "broke the gate", "fell into the torrent"],

    # LLM artifacts -> Engine pacing notes
    r"\bAs an AI language model\b": "[Engine Note: LLM identity slippage detected and scrubbed.]",
    r"\bfade to black\b": "[GM Note: The engine dictates the pacing, not the LLM. Scene continues.]",
}


def _apply(text: str) -> tuple[str, dict[str, int]]:
    """The register pass, once.

    @returns the transformed text and how many substitutions each pattern made.
    """
    processed = text
    counts: dict[str, int] = {}
    for pattern, replacements in REPLACEMENT_LEXICON.items():
        made = [0]
        if isinstance(replacements, list):
            def replacer(_match, _choices=replacements, _made=made):
                # Deterministic by occurrence: the first match always gets the first phrasing, the
                # second the second, and it wraps. `random.choice` used to decide this, which meant
                # the same input produced different canon prose on every call.
                choice = _choices[_made[0] % len(_choices)]
                _made[0] += 1
                return choice
            processed = re.sub(pattern, replacer, processed, flags=re.IGNORECASE)
        else:
            processed, n = re.subn(pattern, replacements, processed, flags=re.IGNORECASE)
            made[0] = n
        if made[0]:
            counts[pattern] = made[0]
    return processed, counts


def enforce_ds_register(text: str) -> str:
    """Process LLM output: replace flagged clinical terms with sensory metaphors."""
    return _apply(text)[0]


def register_report(text: str) -> dict[str, int]:
    """How many substitutions each pattern makes, for logging and tests."""
    return _apply(text)[1]


def ds_register_delta(original: str, processed: str | None = None) -> int:
    """How many terms were transformed.

    The old body compared the two strings character by character and required them to be the same
    length, so a replacement that changed the length — which most of them do, `sex` becomes
    `the union` — returned -1. It counted nothing, ever. The count comes from the pattern matches in
    the original instead, and `processed` is accepted only for callers that still pass it.
    """
    return sum(register_report(original).values())
