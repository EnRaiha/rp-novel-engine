#!/usr/bin/env python3
"""
Narrative Text Processor — enforces the DS Register on LLM output.
Replaces clinical/mechanical terms with the sensory-metaphor lexicon
from erotic-playbook.md §9, keeping prose consistent with the
established literary register.
"""
import re
import random

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


def enforce_ds_register(text: str) -> str:
    """
    Process LLM output: replace flagged clinical terms with sensory
    metaphors. Returns transformed text.
    """
    processed = text
    for pattern, replacements in REPLACEMENT_LEXICON.items():
        if isinstance(replacements, list):
            def replacer(match, _choices=replacements):
                return random.choice(_choices)
            processed = re.sub(pattern, replacer, processed, flags=re.IGNORECASE)
        else:
            processed = re.sub(pattern, replacements, processed, flags=re.IGNORECASE)
    return processed


def ds_register_delta(original: str, processed: str) -> int:
    """How many terms were transformed (for logging)."""
    return sum(1 for a, b in zip(original, processed) if a != b) if len(original) == len(processed) else -1
