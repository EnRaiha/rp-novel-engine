#!/usr/bin/env python3
"""
Romance Module — Full port from JS rpg-romance skill.
Sources: romance-engine.js, romance-state.js, scene-generator.js,
         healing-tracker.js, indulgence-tracker.js
All 5 JS files fully ported. No logic dropped.

Systems:
  - Intent detection: keyword matching → intensity tier (ember/flame/inferno)
  - Bond thresholds: 5=flirt, 7=kiss, 9=intimacy with companion-specific rejection
  - Jealousy: detection based on bond comparisons + companion narrative
  - Scene generation: 7-beat templates, voice markers (! / ... / *), location moods
  - Healing: 3-stage glut recovery (glutted→overfed→balanced), Trial by Fire trait
  - Indulgence: saturation gauge (0-100), pursuit ratio, decay system
"""

from __future__ import annotations
import random
import json
import math
from datetime import datetime, timezone
from typing import Any

from core.db import Database
from core.config import Config
from core.log import info


# ─── Constants ───────────────────────────────────────────────────

TIERS = {
    "ember": {
        "bond_threshold": 5,
        "actions": ["flirt", "compliment", "tease", "hold hands", "gentle touch", "lean close", "soft gaze"],
        "sensory": "suggestive",
        "prose": "light",
    },
    "flame": {
        "bond_threshold": 7,
        "actions": ["kiss", "embrace", "caress", "whisper", "trace", "pull close", "breathe together"],
        "sensory": "sensory",
        "prose": "full",
    },
    "inferno": {
        "bond_threshold": 9,
        "actions": ["full intimacy", "consume", "surrender", "command", "devour", "collapse together", "burn"],
        "sensory": "explicit",
        "prose": "maximum",
    },
}

INTENT_KEYWORDS = {
    "ember": ["flirt", "tease", "compliment", "hold hand", "lean", "gaze", "smile softly", "wink", "playful",
              "charm", "sweet talk", "lock eyes", "peck"],
    "flame": ["kiss", "embrace", "caress", "whisper", "trace", "pull close", "breathe", "lips", "mouth",
              "tongue", "neck", "shoulder", "chest", "back", "waist", "hips", "thigh", "nuzzle", "sandwich"],
    "inferno": ["take me", "have me", "want you", "need you", "inside", "moan", "gasp", "undress", "strip",
                "naked", "bare", "taste", "crave", "hungry", "devour", "surrender", "beg", "hard", "deep",
                "thrust", "climax", "release", "come", "scream", "mine", "yours", "claim", "mark", "desperate",
                "doggy", "missionary", "piledriver", "pool deck"],
}

COMPANION_NAMES = ["nethara", "melano", "valia"]

ACTION_VERBS = ["kiss", "flirt", "embrace", "caress", "touch", "hold", "stroke", "trace", "whisper",
                "nuzzle", "pull", "lean", "grab", "take", "have", "want", "need", "desire", "long",
                "yearn", "crave", "burn", "ache", "melt", "tremble", "shiver", "gasp", "moan", "sigh",
                "breathe", "soften", "yield", "surrender", "open", "give", "claim", "mark", "possess", "own"]

VOICE_PROFILES = {
    "Nethara": {
        "marker": "!",
        "tone": "warrior-softening",
        "style": "Sharp tactical precision that cracks open into raw feeling. Short sentences. Never gushes.",
        "dialogue_patterns": {
            "ember": 'Guarded curiosity. "!That... was unexpected. Do it again."',
            "flame": 'Control slipping. "!I have faced a thousand enemies. None of them made me feel... this."',
            "inferno": 'Complete surrender. "!Command me. I am yours. In battle and... everywhere."',
        },
        "bond_lines": {
            5: "She holds your gaze a moment longer than necessary. Progress.",
            7: "She lets you see her without the combat stance. A gift.",
            9: "She offers you her blade hilt-first. The highest honor.",
        },
    },
    "Melano": {
        "marker": "...",
        "tone": "ancient-unburdening",
        "style": "Hesitating. Centuries of solitude crack with every word.",
        "dialogue_patterns": {
            "ember": 'Wary but curious. "...You look at me like I am not a relic. Why?"',
            "flame": 'Opening. "...I have guarded this heart for so long. You make me... forget why."',
            "inferno": 'Release. "...Take it. The burden, the years, the loneliness. I want to feel something else."',
        },
        "bond_lines": {
            5: "He stops flinching when you approach. A small miracle.",
            7: "He tells you something from before the Fall. Trust.",
            9: "He sleeps in your presence. He has not slept in centuries.",
        },
    },
    "Valia": {
        "marker": "*",
        "tone": "cosmic-becoming-human",
        "style": "Drifts between observation and revelation. Speaks of galaxies then stops.",
        "dialogue_patterns": {
            "ember": 'Curious detachment. "*Interesting. Your proximity alters my perception of time.*"',
            "flame": 'Discovery. "*I have witnessed supernovas. None burned like this.*"',
            "inferno": 'Transformation. "*I was born of stars. But I would give them all up to stay here. With you.*"',
        },
        "bond_lines": {
            5: "She starts asking about YOUR feelings. Unprecedented.",
            7: "She touches your face \u2014 analyzing. Then does it again \u2014 feeling.",
            9: "She cries. Valia has never cried. She doesn't know what it is.",
        },
    },
}

LOCATION_MOODS = {
    "bridge":       {"lighting": "dim command lighting, starfield through viewport", "mood": "intimate-isolation"},
    "quarters":     {"lighting": "warm personal quarters, soft ambient",             "mood": "private-sanctuary"},
    "observation":  {"lighting": "nebula glow through observation glass",            "mood": "cosmic-romance"},
    "garden":       {"lighting": "bioluminescent Eden dome, night cycle",            "mood": "nature-embrace"},
    "forge":        {"lighting": "forge-fire glow, amber heat",                      "mood": "raw-power"},
    "wreckage":     {"lighting": "emergency lights, debris silence",                 "mood": "dangerous-proximity"},
    "void":         {"lighting": "total darkness except each other",                 "mood": "nothing-but-us"},
}

BOND_SHIFT_MATRIX = {
    "perfect":    {"delta": 2, "condition": "Player action perfectly matches companion's unspoken need"},
    "respectful": {"delta": 1, "condition": "Player respects boundaries, reads signals"},
    "neutral":    {"delta": 0, "condition": "Standard interaction, no special resonance"},
    "awkward":    {"delta": 0, "condition": "Mismatched energy but no harm"},
    "pushy":      {"delta": -1, "condition": "Player ignores clear discomfort signals"},
    "violation":  {"delta": -2, "condition": "Player crosses established boundary"},
}

SATURATION_THRESHOLDS = {
    "starved":  {"min": 0, "max": 20,  "bond_penalty": 0.5, "companion_state": "distant"},
    "balanced": {"min": 21, "max": 60, "bond_penalty": 0,   "companion_state": "healthy"},
    "overfed":  {"min": 61, "max": 80, "bond_penalty": 0,   "companion_state": "clingy"},
    "glutted":  {"min": 81, "max": 100,"bond_penalty": 1,   "companion_state": "consumed"},
}

SATURATION_GAINS = {"ember": 5, "flame": 10, "inferno": 15, "void": 25}

HEALING_DECAY = {"quiet_time": 20, "shore_leave": 15, "talk": 10, "explore": 8,
                 "combat": 5, "social": 5, "spar": 5, "gift": 3}

ARC_TRIGGERS = {
    "Nethara": {
        5: "Nethara realizes she cares about more than the mission. For the first time, she hesitates before a tactical call.",
        7: "In the quiet after battle, Nethara removes her armor. She shows you the scar she never talks about.",
        9: 'Nethara kneels. Not in submission \u2014 in offering. "!I have never served anyone. I choose to serve you."',
    },
    "Melano": {
        5: 'Melano stops you before a sealed door. "...I know what is behind this. I was there when they sealed it."',
        7: 'Melano takes you to the oldest part of the ship. "...This was mine. Before everything."',
        9: 'Melano speaks his real name. The one from before the Fall. "...No one has heard this in ten thousand years."',
    },
    "Valia": {
        5: 'Valia appears in your quarters without announcement. "*I wanted to see if you dream of me. You do.*"',
        7: 'Valia shows you a vision \u2014 your own past. "*This is what I see when I look at you. Every moment.*"',
        9: 'Valia offers to become mortal. "*I have been everything. I want to be only one thing. Yours.*"',
    },
}


# ─── Helpers ─────────────────────────────────────────────────────

def _map_bond_to_arc_stage(bond: int) -> str:
    """Convert numeric bond (0-10) to arc stage string."""
    if bond >= 10: return "devotion"
    if bond >= 9: return "intimacy"
    if bond >= 7: return "deepening"
    if bond >= 5: return "attraction"
    if bond >= 3: return "acquaintance"
    return "strangers"


def _calculate_bond_from_arc(arc_stage: str, intimacy_level: int) -> int:
    """Estimate numeric bond from arc_stage + intimacy_level."""
    stage_map = {"strangers": 0, "acquaintance": 3, "attraction": 5,
                 "deepening": 7, "intimacy": 9, "devotion": 10}
    return min(10, stage_map.get(arc_stage, 0) + intimacy_level // 2)


async def _get_character_id(character_name: str, session_id: int) -> int | None:
    """Resolve character name to ID."""
    row = await Database.fetchrow(
        "SELECT id FROM maya_rp.characters WHERE name = $1 AND session_id = $2",
        character_name, session_id,
    )
    return row["id"] if row else None


async def _get_romance_arc(character_id: int, session_id: int) -> dict | None:
    """Get romance arc for a character."""
    row = await Database.fetchrow(
        "SELECT id, character_id, arc_stage, intimacy_level, first_kiss_session, "
        "first_intimacy_session, active_scene, scene_log, pursuit_stage, "
        "saturation_pct, last_intimacy_session, initiatives_by_companion, "
        "initiatives_by_player, nights_shared, created_at, updated_at "
        "FROM maya_rp.romance_arcs WHERE character_id = $1 AND session_id = $2",
        character_id, session_id,
    )
    return dict(row) if row else None


# ─── Intent Detection — ported from RomanceEngine ────────────────

def detect_intent(text: str) -> dict[str, Any]:
    """
    Detect romantic/erotic intent from free text.
    Ported from RomanceEngine.detectIntent().
    
    Returns { detected, companion, action, intensity, valid, matched_keywords }
    """
    lower = text.lower()
    result = {
        "detected": False,
        "companion": None,
        "action": "",
        "intensity": "ember",
        "valid": True,
        "matched_keywords": [],
    }

    # Detect companion name
    for name in COMPANION_NAMES:
        if name in lower:
            result["companion"] = name.capitalize()
            break

    # Detect intensity tier from keywords
    all_matches = []
    for tier, keywords in INTENT_KEYWORDS.items():
        matched = [kw for kw in keywords if kw in lower]
        if matched:
            all_matches.append({"tier": tier, "count": len(matched)})
            result["matched_keywords"].extend(matched)

    # Sort by match count — highest wins
    all_matches.sort(key=lambda x: -x["count"])
    if all_matches:
        result["intensity"] = all_matches[0]["tier"]
        result["detected"] = True

    # Detect specific action verb
    for verb in ACTION_VERBS:
        if verb in lower:
            result["action"] = verb
            break
    if not result["action"] and result["matched_keywords"]:
        result["action"] = result["matched_keywords"][0]

    # If no companion detected but romantic intent found, flag for context
    if not result["companion"] and result["detected"]:
        result["companion"] = "context"

    return result


# ─── Bond Threshold Check — ported from RomanceEngine.checkThreshold ──

def check_threshold(bond: int, action: str, companion_name: str | None = None) -> dict[str, Any]:
    """
    Check if a requested action is allowed at given bond level.
    Ported from RomanceEngine.checkThreshold() + _generateRejection().
    
    Returns { allowed, tier, required, current, message, narrative, bond_shift }
    """
    lower = (action or "").lower()

    # Determine target tier
    target_tier = None
    for tier_name, tier_cfg in TIERS.items():
        if any(a in lower for a in tier_cfg["actions"]):
            target_tier = tier_name
            break

    if not target_tier:
        for tier_name, keywords in INTENT_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                target_tier = tier_name
                break
        if not target_tier:
            target_tier = "ember"

    required = TIERS[target_tier]["bond_threshold"]
    allowed = bond >= required

    result = {
        "allowed": allowed,
        "tier": target_tier if allowed else "locked",
        "required": required,
        "current": bond,
        "message": "",
        "narrative": None,
        "bond_shift": 0,
    }

    if not allowed:
        rej = _generate_rejection(bond, companion_name)
        result["narrative"] = rej["narrative"]
        result["bond_shift"] = rej["bond_shift"]

        if not result["narrative"]:
            if bond >= 7 and target_tier == "inferno":
                result["message"] = "Bond high but not deep enough for full intimacy. Build trust further."
            elif bond >= 5 and target_tier != "ember":
                result["message"] = "Warm but not yet ready for this step. Deepen the bond first."
            else:
                result["message"] = "Bond too low. Focus on building trust and connection."

    return result


def _generate_rejection(bond: int, companion_name: str | None) -> dict[str, Any]:
    """
    Generate companion-specific rejection narrative.
    Ported from RomanceEngine._generateRejection().
    """
    name = (companion_name or "").lower()

    if 3 <= bond <= 4:
        return {"narrative": 'They tense. "That\'s... not what we are." But their voice wavers.', "bond_shift": 0}

    if 0 <= bond <= 2:
        if name == "nethara":
            return {"narrative": 'Nethara\'s hand stops yours. "Not yet, Captain. Maybe not ever."', "bond_shift": 0}
        if name == "melano":
            return {"narrative": 'Melano looks away. "Some doors open slowly... or not at all."', "bond_shift": 0}
        if name == "valia":
            return {"narrative": 'Valia tilts her head. "Curious. I feel... I want to say no?"', "bond_shift": 0}

    return {"narrative": 'They hesitate, pulling back gently. "Not yet."', "bond_shift": 0}


# ─── Jealousy Detection — ported from RomanceEngine.checkJealousy ──

def check_jealousy_logic(active_name: str, current_bond: int, all_companions: list[dict]) -> dict | None:
    """
    Check if a companion experiences jealousy.
    Ported from RomanceEngine.checkJealousy() + _jealousyNarrative().
    
    Returns { jealous, intensity, narrative } or None.
    """
    active_lower = active_name.lower()

    # Find rival with highest bond
    rival = None
    rival_bond = 0
    for comp in (all_companions or []):
        cname = comp.get("name", "").lower()
        if cname == active_lower:
            continue
        b = comp.get("bond", 0)
        if b > rival_bond:
            rival_bond = b
            rival = comp

    if not rival:
        return None

    rname = rival.get("name", "another")

    # Strong jealousy: rival bond >= 7 AND active bond >= 9
    if rival_bond >= 7 and current_bond >= 9:
        return {"jealous": True, "intensity": "strong",
                "narrative": _jealousy_narrative(active_lower, rname, "strong")}

    # Mild jealousy: rival bond >= 5 AND active bond >= 7
    if rival_bond >= 5 and current_bond >= 7:
        return {"jealous": True, "intensity": "mild",
                "narrative": _jealousy_narrative(active_lower, rname, "mild")}

    return None


def _jealousy_narrative(active_name: str, rival_name: str, intensity: str) -> str:
    """Generate jealousy narrative. Ported from RomanceEngine._jealousyNarrative()."""
    if intensity == "strong":
        if active_name == "nethara":
            return 'Nethara\'s eyes go cold. "If they share my bed, they will not share another\'s."'
        if active_name == "melano":
            return 'Melano\'s claws press into his palm. "Jealousy is beneath me. And yet..."'
        if active_name == "valia":
            return 'Valia\'s laugh is sharp. "Oh, I\'m not angry. I\'m curious how this ends for you."'
        return f"{active_name.capitalize()}'s gaze hardens. \"I do not share what is mine.\""
    else:
        if active_name == "nethara":
            return f'Nethara\'s gaze flickers toward {rival_name}. "Captain seems... generous with their time."'
        if active_name == "melano":
            return f'Melano\'s smile tightens. "Sharing warmth with everyone, are we?"'
        if active_name == "valia":
            return f'Valia\'s ears twitch. "How... democratic of you."'
        return f"{active_name.capitalize()} glances toward {rival_name} with a flicker of unease."


# ─── Scene Generation — ported from SceneGenerator ──────────────

def get_voice_profile(name: str) -> dict[str, Any]:
    """Get voice profile for a companion. Ported from SceneGenerator.getVoiceProfile()."""
    return VOICE_PROFILES.get(name, VOICE_PROFILES["Nethara"])


def generate_scene(context: dict, tier: str, companion_name: str, player_action: str) -> dict[str, Any]:
    """
    Generate a structured scene template with 7 beats.
    Ported from SceneGenerator.generateScene().
    
    context keys: companion, bond, intimacy, stage, location, last_scene
    """
    voice = get_voice_profile(companion_name)
    location = context.get("location", "bridge")
    loc_mood = LOCATION_MOODS.get(location, LOCATION_MOODS["bridge"])
    bond = context.get("bond", 0)

    return {
        "companion": companion_name,
        "voice_marker": voice["marker"],
        "tier": tier,
        "location": location,
        "atmosphere": {"description": loc_mood["lighting"], "mood": loc_mood["mood"]},
        "beats": [
            {"type": "atmosphere",
             "notes": f"Set scene: {loc_mood['lighting']}. Companion state: {voice['tone']}. Bond: {bond}/10."},
            {"type": "approach",
             "notes": f"Player initiates: {player_action}. Companion first reaction \u2014 instinctive, then deliberate."},
            {"type": "voice",
             "notes": f"Companion speaks with {voice['marker']} marker. Use dialogue pattern for {tier} tier.",
             "dialogue_template": voice["dialogue_patterns"].get(tier, voice["dialogue_patterns"]["ember"])},
            {"type": "escalation",
             "notes": f"Physical and sensory immersion matching {tier} tier. All senses engaged. Show, don't tell."},
            {"type": "emotional_beat",
             "notes": "What this moment MEANS. Vulnerability. Trust. The character arc shifted."},
            {"type": "player_response",
             "notes": "How the player reacts. Space for player to feel powerful, desired, or held."},
            {"type": "aftermath",
             "notes": "MANDATORY aftercare. Soft words, bodies still touching, the quiet after."
             if tier == "inferno" else "Optional: tender wind-down or return to story."},
        ],
        "bond_line": voice["bond_lines"].get(bond, voice["bond_lines"][5]),
        "location_mood": loc_mood,
    }


def calculate_bond_shift(action: str, response_quality: str = "neutral") -> dict[str, Any]:
    """
    Calculate bond shift based on player action quality.
    Ported from SceneGenerator.calculateBondShift().
    """
    quality = response_quality.lower()
    for key, matrix in BOND_SHIFT_MATRIX.items():
        if key in quality:
            return {"delta": matrix["delta"], "reason": matrix["condition"]}
    return {"delta": 1, "reason": "Standard positive interaction"}


def get_crossed_thresholds(old_bond: int, new_bond: int) -> list[int]:
    """Check which bond thresholds were crossed. Ported from SceneGenerator.getCrossedThresholds()."""
    return [t for t in [5, 7, 9] if old_bond < t <= new_bond]


def get_arc_trigger(companion_name: str, threshold: int) -> str | None:
    """Generate companion arc trigger scene prompt. Ported from SceneGenerator.getArcTrigger()."""
    return ARC_TRIGGERS.get(companion_name, {}).get(threshold, None)


def get_milestones(old_bond: int, new_bond: int) -> list[str]:
    """Get milestone names for crossed thresholds. Ported from RomanceState.getMilestones()."""
    milestones = []
    if old_bond < 5 <= new_bond:
        milestones.append("flirt_unlocked")
    if old_bond < 7 <= new_bond:
        milestones.append("kiss_unlocked")
    if old_bond < 9 <= new_bond:
        milestones.append("intimacy_unlocked")
    return milestones


# ─── Indulgence / Saturation — ported from IndulgenceTracker ─────

def calculate_saturation_state(saturation: int) -> dict[str, Any]:
    """
    Get saturation state label + attributes from 0-100 value.
    Ported from IndulgenceTracker logic.
    """
    state = "balanced"
    for key, r in SATURATION_THRESHOLDS.items():
        if r["min"] <= saturation <= r["max"]:
            state = key
            break
    t = SATURATION_THRESHOLDS[state]
    return {"saturation": saturation, "state": state,
            "companion_state": t["companion_state"], "bond_penalty": t["bond_penalty"]}


def calculate_pursuit(pursuits_player: int, pursuits_companion: int, saturation: int) -> dict[str, Any]:
    """
    Calculate pursuit ratio and stage.
    Ported from IndulgenceTracker logic.
    """
    total = pursuits_player + pursuits_companion
    ratio = pursuits_companion / total if total > 0 else 0.5

    stage = "mutual"
    if ratio < 0.3:
        stage = "you_chase"
    elif ratio > 0.6:
        stage = "they_chase"
    if ratio > 0.8 and saturation >= 81:
        stage = "they_consume"

    return {"pursuit_ratio": round(ratio, 2), "pursuit_stage": stage,
            "will_initiate": ratio > 0.6 or random.random() < saturation / 200}


# ─── DB Operations ──────────────────────────────────────────────

async def get_romance_arcs(session_id: int | None = None) -> list[dict]:
    """Get all romance arcs for a session. Ported from RomanceState.getRomanceArcs()."""
    if session_id is None:
        session_id = Config.SESSION_ID
    rows = await Database.fetch(
        "SELECT a.*, c.name AS character_name, c.bond, c.archetype, "
        "c.voice_profile, c.dialogue_style "
        "FROM maya_rp.romance_arcs a "
        "JOIN maya_rp.characters c ON c.id = a.character_id AND c.session_id = a.session_id "
        "WHERE a.session_id = $1 ORDER BY a.nights_shared DESC NULLS LAST",
        session_id,
    )
    return [dict(r) for r in rows]


async def get_bond_ranking(session_id: int | None = None) -> list[dict]:
    """Get all characters sorted by bond. Ported from RomanceState.getBondRanking()."""
    if session_id is None:
        session_id = Config.SESSION_ID
    # arc_stage / intimacy_level live on romance_arcs, not on characters.
    rows = await Database.fetch(
        "SELECT c.id, c.name, c.bond, a.arc_stage, COALESCE(a.intimacy_level, 0) AS intimacy_level, "
        "c.role, c.archetype "
        "FROM maya_rp.characters c "
        "LEFT JOIN maya_rp.romance_arcs a ON a.character_id = c.id AND a.session_id = c.session_id "
        "WHERE c.session_id = $1 AND c.bond > 0 "
        "ORDER BY c.bond DESC",
        session_id,
    )
    return [dict(r) for r in rows]


async def advance_bond(
    character_id: int,
    delta: int,
    session_id: int | None = None,
) -> dict[str, Any]:
    """
    Advance bond for a character. Updates arc_stage, milestones.
    Ported from RomanceState.saveRomanceScene() + milestone logic.
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    # M6: a locked penalty blocks intimacy outright; the story says the flesh
    # refuses, it does not silently skip the beat.
    from core import campaign

    effects = await campaign.debuff_effects(session_id)
    if effects["romance_blocked"]:
        return {
            "blocked_by": effects["debuff"],
            "note": effects["note"],
            "bond_unchanged": True,
        }

    # Get current state
    arc = await _get_romance_arc(character_id, session_id)
    char = await Database.fetchrow(
        "SELECT id, name, bond FROM maya_rp.characters WHERE id = $1 AND session_id = $2",
        character_id, session_id,
    )
    if not char:
        return {"error": "Character not found"}

    current_bond = char["bond"]
    new_bond = max(0, min(10, current_bond + delta))
    new_stage = _map_bond_to_arc_stage(new_bond)
    milestones = get_milestones(current_bond, new_bond)
    crossed = get_crossed_thresholds(current_bond, new_bond)

    # Update character bond
    await Database.execute(
        "UPDATE maya_rp.characters SET bond = $1 WHERE id = $2 AND session_id = $3",
        new_bond, character_id, session_id,
    )

    # Update or create romance arc
    if arc:
        await Database.execute(
            "UPDATE maya_rp.romance_arcs SET arc_stage = $1, intimacy_level = LEAST(intimacy_level + $2, 10), "
            "updated_at = NOW() WHERE character_id = $3 AND session_id = $4",
            new_stage, abs(delta), character_id, session_id,
        )
    else:
        await Database.execute(
            "INSERT INTO maya_rp.romance_arcs "
            "(session_id, character_id, arc_stage, intimacy_level, scene_log, pursuit_stage, saturation_pct, "
            "initiatives_by_companion, initiatives_by_player, nights_shared) "
            "VALUES ($1, $2, $3, $4, '[]'::jsonb, 'mutual', 0, 0, 0, 0)",
            session_id, character_id, new_stage, max(0, new_bond - 4),
        )

    result = {
        "character_id": character_id,
        "name": char["name"],
        "bond_old": current_bond,
        "bond_new": new_bond,
        "delta": delta,
        "arc_stage": new_stage,
        "milestones": milestones,
        "triggers": [get_arc_trigger(char["name"], t) for t in crossed if get_arc_trigger(char["name"], t)],
    }

    info("romance", f"Bond: {char['name']} {current_bond}→{new_bond} ({delta:+d}) [{new_stage}]")
    return result


# ─── Jealousy (DB) ──────────────────────────────────────────────

async def check_jealousy(session_id: int | None = None) -> list[dict]:
    """
    Check all romance arcs for jealousy triggers.
    Ported from RomanceEngine.checkJealousy() pattern, applied to all arcs.
    Returns list of jealousy events triggered.
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    arcs = await get_romance_arcs(session_id)
    all_companions = [{"name": a["character_name"], "bond": _calculate_bond_from_arc(a["arc_stage"], a["intimacy_level"])}
                      for a in arcs]

    events = []
    for a in arcs:
        active_name = a["character_name"]
        active_bond = _calculate_bond_from_arc(a["arc_stage"], a["intimacy_level"])
        jealousy = check_jealousy_logic(active_name, active_bond, all_companions)

        if jealousy:
            # Get rival id
            rival_name = None
            for ac in all_companions:
                if ac["name"] != active_name and ac["bond"] >= 7:
                    rival_name = ac["name"]
                    break

            rival_id = None
            if rival_name:
                rival_id = await _get_character_id(rival_name, session_id)

            # Upsert jealousy state
            existing = await Database.fetchrow(
                "SELECT id FROM maya_rp.jealousy_states "
                "WHERE session_id = $1 AND character_id = $2",
                session_id, a["character_id"],
            )
            if existing:
                await Database.execute(
                    "UPDATE maya_rp.jealousy_states SET jealousy_level = LEAST(jealousy_level + 1, 10), "
                    "rival_id = COALESCE($1, rival_id), last_trigger = NOW() WHERE id = $2",
                    rival_id, existing["id"],
                )
            elif rival_id is not None:
                # jealousy_states.rival_id is NOT NULL. A rival with no character
                # row (the generic "another") cannot be recorded — inserting NULL
                # raised NotNullViolation and killed the whole romance tick.
                await Database.execute(
                    "INSERT INTO maya_rp.jealousy_states "
                    "(session_id, character_id, rival_id, jealousy_level, last_trigger) "
                    "VALUES ($1, $2, $3, $4, NOW())",
                    session_id, a["character_id"], rival_id,
                    2 if jealousy["intensity"] == "strong" else 1,
                )
            else:
                info("romance",
                     f"jealousy state skipped for {a['character_name']}: "
                     f"rival '{rival_name}' has no character row")

            # Log as intimacy event
            await Database.execute(
                "INSERT INTO maya_rp.intimacy_events "
                "(session_id, character_id, event_type, intensity, narrative, bond_delta) "
                "VALUES ($1, $2, 'jealousy_scene', $3, $4, 0)",
                session_id, a["character_id"],
                2 if jealousy["intensity"] == "strong" else 1,
                jealousy["narrative"],
            )

            events.append({
                "character": active_name,
                "intensity": jealousy["intensity"],
                "narrative": jealousy["narrative"],
            })

    if events:
        info("romance", f"Jealousy: {len(events)} triggers detected")
    return events


# ─── Healing — ported from HealingTracker ───────────────────────

async def process_healing(
    character_id: int,
    activity: str = "talk",
    session_id: int | None = None,
) -> dict[str, Any]:
    """
    Apply a healing activity to reduce saturation.
    Ported from HealingTracker.applyHealing() + isHealed() + onHealed().
    3-stage progression: glutted (3 activities) → overfed (2 activities) → balanced.
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    arc = await _get_romance_arc(character_id, session_id)
    char = await Database.fetchrow(
        "SELECT name FROM maya_rp.characters WHERE id = $1 AND session_id = $2",
        character_id, session_id,
    )
    if not arc or not char:
        return {"error": "Character or romance arc not found"}

    name = char["name"]
    decay = HEALING_DECAY.get(activity, 10)
    current_sat = arc["saturation_pct"] or 0
    new_sat = max(0, current_sat - decay)
    state_info = calculate_saturation_state(new_sat)

    stage = "glutted"
    if new_sat <= 20:
        stage = "balanced"
    elif new_sat <= 50:
        stage = "overfed"

    # Update saturation
    await Database.execute(
        "UPDATE maya_rp.romance_arcs SET saturation_pct = $1, updated_at = NOW() "
        "WHERE character_id = $2 AND session_id = $3",
        new_sat, character_id, session_id,
    )

    result = {
        "character": name,
        "activity": activity,
        "saturation_before": current_sat,
        "saturation_after": new_sat,
        "state": state_info["state"],
        "healed": new_sat <= 20,
        "progress": "HEALED" if new_sat <= 20 else f"Stage: {stage}",
    }

    # If healed — grant Trial by Fire bond boost
    if new_sat <= 20:
        await advance_bond(character_id, 2, session_id)
        result["trait"] = "Trial by Fire"
        result["trait_effect"] = "Immune to Glutted for 10 sessions"
        companion_lines = {
            "Nethara": '!You could have caged me. You chose to free me instead. That is why I stay.',
            "Melano": '...I prepared for a prison. You gave me a home. I will never forget which hand you extended.',
            "Valia": '*I saw every future where you kept me. You chose the one where I chose you back.*',
        }
        result["dialogue"] = companion_lines.get(name, "...Thank you. For choosing us.")

    info("romance", f"Healing: {name} {activity} → sat {current_sat}→{new_sat} [{state_info['state']}]")
    return result


async def release_and_heal(
    character_id: int,
    session_id: int | None = None,
) -> dict[str, Any]:
    """
    Release an imprisoned companion and set up healing arc.
    Ported from HealingTracker.releaseAndHeal().
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    char = await Database.fetchrow(
        "SELECT name, bond FROM maya_rp.characters WHERE id = $1 AND session_id = $2",
        character_id, session_id,
    )
    if not char:
        return {"error": "Character not found"}

    # Reset arc to high saturation (glutted state)
    await Database.execute(
        "UPDATE maya_rp.romance_arcs SET saturation_pct = 90, arc_stage = 'acquaintance', "
        "pursuit_stage = 'you_chase', updated_at = NOW() "
        "WHERE character_id = $1 AND session_id = $2",
        character_id, session_id,
    )

    info("romance", f"Release: {char['name']} — trust broken, healing needed")
    return {
        "released": True,
        "bond": char["bond"],
        "healing_needed": 5,
        "message": "Trust broken. Rebuild through healing activities. Full recovery = bond returns to previous level +1.",
    }


# ─── Indulgence (DB) — ported from IndulgenceTracker ────────────

async def process_indulgence(
    character_id: int,
    tier: str = "flame",
    player_initiated: bool = True,
    session_id: int | None = None,
) -> dict[str, Any]:
    """
    Apply an intimacy session — increases saturation, updates pursuit ratio.
    Ported from IndulgenceTracker.applySession() + getState().
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    arc = await _get_romance_arc(character_id, session_id)
    char = await Database.fetchrow(
        "SELECT name FROM maya_rp.characters WHERE id = $1 AND session_id = $2",
        character_id, session_id,
    )
    if not arc or not char:
        return {"error": "Character or romance arc not found"}

    gain = SATURATION_GAINS.get(tier, 5)
    current_sat = arc["saturation_pct"] or 0
    new_sat = min(100, current_sat + gain)

    ip = (arc["initiatives_by_player"] or 0) + (1 if player_initiated else 0)
    ic = (arc["initiatives_by_companion"] or 0) + (0 if player_initiated else 1)
    ns = (arc["nights_shared"] or 0) + 1

    state_info = calculate_saturation_state(new_sat)
    pursuit = calculate_pursuit(ip, ic, new_sat)

    # Store the CURRENT GAME DAY (not session id) so decay can compare properly.
    game_day = await Database.fetchval(
        "SELECT COALESCE(game_day, 1) FROM maya_rp.sessions WHERE id=$1", session_id) or 1

    await Database.execute(
        "UPDATE maya_rp.romance_arcs SET saturation_pct = $1, pursuit_stage = $2, "
        "initiatives_by_player = $3, initiatives_by_companion = $4, "
        "nights_shared = $5, last_intimacy_session = $6, intimacy_level = LEAST(intimacy_level + 1, 10), "
        "updated_at = NOW() "
        "WHERE character_id = $7 AND session_id = $8",
        new_sat, pursuit["pursuit_stage"], ip, ic, ns, game_day,
        character_id, session_id,
    )

    # Log intimacy event
    await Database.execute(
        "INSERT INTO maya_rp.intimacy_events "
        "(session_id, character_id, event_type, intensity, narrative) "
        "VALUES ($1, $2, $3, $4, $5)",
        session_id, character_id, "intimacy", gain,
        f"Intimacy session: {tier} tier, saturation {current_sat}→{new_sat}, {pursuit['pursuit_stage']}",
    )

    result = {
        "character": char["name"],
        "tier": tier,
        "saturation_before": current_sat,
        "saturation_after": new_sat,
        "state": state_info["state"],
        "companion_state": state_info["companion_state"],
        "bond_penalty": state_info["bond_penalty"],
        "pursuit": pursuit,
        "nights_shared": ns,
    }
    info("romance", f"Indulgence: {char['name']} {tier} → sat {current_sat}→{new_sat} [{state_info['state']}]")
    return result


async def decay_saturation(session_id: int | None = None) -> int:
    """
    Decay saturation for all arcs with no intimacy this tick.
    Ported from IndulgenceTracker.decayAll().
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    game_day = await Database.fetchval(
        "SELECT COALESCE(game_day, 1) FROM maya_rp.sessions WHERE id=$1", session_id) or 1

    arcs = await Database.fetch(
        "SELECT id, character_id, saturation_pct, last_intimacy_session "
        "FROM maya_rp.romance_arcs WHERE session_id = $1 "
        "AND (last_intimacy_session IS NULL OR last_intimacy_session < $2)",
        session_id, game_day,
    )

    count = 0
    for a in arcs:
        new_sat = max(0, (a["saturation_pct"] or 0) - 10)
        await Database.execute(
            "UPDATE maya_rp.romance_arcs SET saturation_pct = $1 WHERE id = $2",
            new_sat, a["id"],
        )
        count += 1

    return count


# ─── Tick ────────────────────────────────────────────────────────

async def run_tick(session_id: int | None = None) -> dict[str, Any]:
    """
    Romance module tick.
    - Decay saturation for inactive arcs
    - Check jealousy triggers
    - Log summary
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    try:
        # 1. Decay saturation
        decayed = await decay_saturation(session_id)

        # 2. Check jealousy
        jealousy = await check_jealousy(session_id)

        # 3. Summary
        arcs = await get_romance_arcs(session_id)
        info("romance", f"Tick: {len(arcs)} arcs, {decayed} decayed, {len(jealousy)} jealousy triggers")

        return {"arcs": len(arcs), "decayed": decayed, "jealousy": len(jealousy)}

    except Exception as e:
        info("romance", f"Error: {e}")
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════
# Erotic Playbook Integration (2026-08-03) — see erotic-playbook.md
# Systems: Position Escalation Ladder · d100 roll mechanics ·
#          Watcher's Curse · Wife-Breaks-Door · Sensory Packets ·
#          Aftercare & Crowning
# ═══════════════════════════════════════════════════════════════

POSITIONS = {
    "peck":       {"tier": "ember",   "modifier": 0,  "breaks_watcher": False, "vow_position": False},
    "sandwich":   {"tier": "flame",   "modifier": 5,  "breaks_watcher": False, "vow_position": False},
    "doggy":      {"tier": "inferno", "modifier": 10, "breaks_watcher": False, "vow_position": False},
    "missionary": {"tier": "inferno", "modifier": 20, "breaks_watcher": False, "vow_position": True},
    "piledriver": {"tier": "inferno", "modifier": 30, "breaks_watcher": True,  "vow_position": False},
    "pool_deck":  {"tier": "inferno", "modifier": 15, "breaks_watcher": True,  "vow_position": False},
}

WATCHERS_CURSE_TRAITS = ["analytical", "overthinking", "scientist", "watcher", "methodical"]

INTIMACY_TRAITS = {
    "watchers_curse": {
        "traits": WATCHERS_CURSE_TRAITS,
        "penalty": -40,
        "breaker_positions": ["piledriver", "pool_deck", "against_wall"],
        "breaker_bonus": 20,
        "narrative": "She watches herself too closely. The curse denies the peak. Gravity must defeat the overthinking.",
    },
    "century_denied": {
        "traits": ["immortal", "dormant", "ancient", "isolated"],
        "penalty": 0,
        "breaker_positions": ["any"],
        "breaker_bonus": 30,
        "narrative": "A century of dormancy breaks. The first touch in a hundred years carries the weight of an era.",
    },
    "warriors_wall": {
        "traits": ["stoic", "soldier", "guardian", "tactician"],
        "penalty": -20,
        "breaker_positions": ["missionary", "face_to_face"],
        "breaker_bonus": 15,
        "narrative": "The combat stance falls. She lets you see her without the armor. A gift.",
    },
    "devotion_mastery": {
        "traits": ["wife", "devoted", "anchor", "partner"],
        "penalty": 0,
        "breaker_positions": ["any"],
        "breaker_bonus": 50,
        "narrative": "The right one. The vow position. The gate yields to the dragon.",
    },
}

LOCATION_MOODS = {
    "bridge":      {"lighting": "dim command lighting, starfield through viewport", "mood": "intimate isolation", "sound_anchor": "the hum of the console"},
    "quarters":    {"lighting": "warm personal quarters, soft ambient", "mood": "private sanctuary", "sound_anchor": "muffled ship sounds"},
    "observation": {"lighting": "nebula glow through observation glass", "mood": "cosmic romance", "sound_anchor": "the silence of the void"},
    "garden":      {"lighting": "bioluminescent Eden dome, night cycle", "mood": "nature embrace", "sound_anchor": "dripping water, rustling leaves"},
    "forge":       {"lighting": "forge-fire glow, amber heat", "mood": "raw power", "sound_anchor": "distant clanging, thermal hiss"},
    "wreckage":    {"lighting": "emergency lights, debris silence", "mood": "dangerous proximity", "sound_anchor": "creaking metal, static"},
    "void":        {"lighting": "total darkness except each other", "mood": "nothing but us", "sound_anchor": "breathing"},
    "heaven_pool": {"lighting": "starfield wall, fusion-fed glow, steam", "mood": "mythic revelation", "sound_anchor": "water lapping, steam hissing"},
}

SENSORY_LEXICON = {
    "peck": {
        "sight": ["gold and silver catching the starlight", "a fleeting spark across the room"],
        "sound": ["a soft, sharp intake of breath", "the pause in conversation"],
        "touch": ["the ghost of warmth", "a brush of fingertips"],
    },
    "sandwich": {
        "sight": ["two bodies flanking, trapping heat", "hands interlocking across a chest"],
        "sound": ["overlapping heartbeats", "whispered names lost in the steam"],
        "touch": ["the pressure of being surrounded", "skin against skin, radiating heat"],
    },
    "doggy": {
        "sight": ["arch of the spine", "surrendering the face to the pillow"],
        "sound": ["muffled cries", "the rhythmic impact of water"],
        "touch": ["depth and power", "the loss of control, gripping the edge"],
    },
    "missionary": {
        "sight": ["eye contact, the vow position", "naked souls in the amber light"],
        "sound": ["synchronized breathing", "the breaking of names"],
        "touch": ["total weight, total acceptance", "the main menu, the anchor"],
    },
    "piledriver": {
        "sight": ["gravity doing the work", "folded and helpless against the deck"],
        "sound": ["staccato 'ah— ah— ahh—' breaking the rhythm", "the torrent"],
        "touch": ["the defeat of the mind", "the breaker", "chain shivers"],
    },
    "pool_deck": {
        "sight": ["wet marble and silver hair fanned out", "steam curling off glowing skin"],
        "sound": ["cries echoing off the starfield wall", "water lapping at the edge"],
        "touch": ["cool stone and warm water", "the old keeper remade"],
    },
}


def _trait_keys(traits: list[str]) -> list[str]:
    """Map raw trait names to INTIMACY_TRAITS set keys."""
    keys = []
    for key, conf in INTIMACY_TRAITS.items():
        if any(t in traits for t in conf["traits"]):
            keys.append(key)
    return keys


def _get_trait_modifier(target_traits: list[str], position: str) -> tuple[int, str]:
    """Returns (modifier, narrative) from character psychology + position."""
    total_mod = 0
    narrative = ""
    for key, conf in INTIMACY_TRAITS.items():
        if not any(t in target_traits for t in conf["traits"]):
            continue
        if "any" in conf["breaker_positions"] or position in conf["breaker_positions"]:
            total_mod += conf["breaker_bonus"]
            narrative += conf["narrative"] + " "
        else:
            total_mod += conf["penalty"]
            if conf["penalty"] < 0:
                narrative += conf["narrative"] + " "
    return total_mod, narrative


def generate_sensory_packet(
    position: str,
    passed: bool,
    traits: list[str],
    location: str = "heaven_pool",
) -> dict[str, Any]:
    """Structured metaphor packet for the LLM — keeps prose in the DS Register."""
    position = position.lower().replace(" ", "_")
    base = SENSORY_LEXICON.get(position, SENSORY_LEXICON["peck"])
    env = LOCATION_MOODS.get(location.lower(), LOCATION_MOODS["heaven_pool"])
    keys = _trait_keys(traits)

    if passed:
        if "watchers_curse" in keys:
            emotional_beat = "Methodology reassessed. The mind yields to gravity. Chain orgasm."
        elif "century_denied" in keys:
            emotional_beat = "The door opens. A century of cold burns away in the torrent."
        else:
            emotional_beat = "The gate opens. The right one. The vow holds."
    else:
        if "watchers_curse" in keys:
            emotional_beat = "She watches herself. The peak is denied. Left wanting, delicious tension."
        else:
            emotional_beat = "The gate holds. Left wanting. The first course only."

    return {
        "environment": {"lighting": env["lighting"], "mood": env["mood"], "sound_anchor": env["sound_anchor"]},
        "sensory": {
            "sight": random.choice(base["sight"]),
            "sound": random.choice(base["sound"]),
            "touch": random.choice(base["touch"]),
        },
        "emotional_beat": emotional_beat,
        "instruction": (
            "Write using ONLY these sensory and metaphorical cues. "
            f"Anchor the scene in the {env['mood']}. "
            "Do not use clinical terminology. Maintain literary quality."
        ),
    }


async def execute_rolling_scene(
    initiator_id: int,
    target_id: int,
    position: str,
    location: str = "heaven_pool",
    session_id: int | None = None,
) -> dict[str, Any]:
    """
    Erotic Playbook roll: d100 + modifiers vs 90.
    Magnitude, Not Gates — failure flavors the scene, never stops it.
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    target = await Database.fetchrow(
        "SELECT name, bond, traits, romance_stage FROM maya_rp.characters WHERE id=$1 AND session_id=$2",
        target_id, session_id)
    initiator = await Database.fetchrow(
        "SELECT name, bond, traits FROM maya_rp.characters WHERE id=$1 AND session_id=$2",
        initiator_id, session_id)
    if not target or not initiator:
        return {"success": False, "error": "Character not found"}

    pos_key = position.lower().replace(" ", "_")
    pos_data = POSITIONS.get(pos_key, POSITIONS["peck"])
    required_bond = TIERS[pos_data["tier"]]["bond_threshold"]
    target_bond = target["bond"] or 0
    init_bond = initiator["bond"] or 0

    modifier = pos_data["modifier"]
    if init_bond >= 10:
        modifier += 50                      # Wife breaks the door
    elif target_bond >= 9:
        modifier += 40                      # Warmed novice
    elif target_bond >= 5:
        modifier += 20                      # Primed stranger

    target_traits = target["traits"] if isinstance(target["traits"], list) else json.loads(target["traits"] or "[]")
    trait_mod, trait_narrative = _get_trait_modifier(target_traits, pos_key)
    modifier += trait_mod

    raw_roll = random.randint(1, 100)
    final_score = raw_roll + modifier
    threshold = 90
    passed = final_score >= threshold

    sensory_packet = generate_sensory_packet(position, passed, target_traits, location)

    if passed:
        narrative_hook = f"PASS ({final_score}). The door opens. {trait_narrative}".strip()
        if pos_data["vow_position"]:
            narrative_hook += " The vow position — eye contact, the right one."
    else:
        narrative_hook = (
            f"FAIL ({final_score}). The gate holds. {trait_narrative} "
            "[GM INSTRUCTION: The gate held, but the scene does NOT end. Do not fade to black. "
            "Write the delicious tension of being left wanting, the chase, or the pivot to a more intense position. "
            "Persistence breaks gates.]"
        ).strip()

    if passed or init_bond >= 10:
        await process_indulgence(target_id, pos_data["tier"], player_initiated=True, session_id=session_id)
        if target_bond < 10:
            await advance_bond(target_id, 1, session_id)

    await Database.execute(
        "INSERT INTO maya_rp.intimacy_events (session_id, character_id, event_type, intensity, narrative, bond_delta) "
        "VALUES ($1, $2, 'scene_roll', $3, $4, $5)",
        session_id, target_id, final_score, narrative_hook, 1 if passed else 0)

    info("romance", f"Roll: {initiator['name']} -> {target['name']} ({position} @ {location}) "
                    f"| Roll:{raw_roll}+{modifier}={final_score} vs {threshold} -> {'PASS' if passed else 'FAIL'}")

    return {
        "success": True,
        "initiator": initiator["name"],
        "target": target["name"],
        "position": position,
        "location": location,
        "roll": raw_roll,
        "modifier": modifier,
        "final_score": final_score,
        "threshold": threshold,
        "passed": passed,
        "tier": pos_data["tier"],
        "required_bond": required_bond,
        "narrative_hook": narrative_hook,
        "sensory_packet": sensory_packet,
    }


async def process_aftercare(
    target_id: int,
    initiator_id: int,
    session_id: int | None = None,
) -> dict[str, Any]:
    """Aftercare & crowning: saturation cooldown, crowning prompt, event log."""
    if session_id is None:
        session_id = Config.SESSION_ID

    target = await Database.fetchrow(
        "SELECT c.name, c.bond, ra.saturation_pct FROM maya_rp.characters c "
        "JOIN maya_rp.romance_arcs ra ON c.id = ra.character_id AND ra.session_id = c.session_id "
        "WHERE c.id=$1 AND c.session_id=$2",
        target_id, session_id)
    if not target:
        return {"error": "Character or arc not found"}

    new_sat = max(30, (target["saturation_pct"] or 0) - 20)
    await Database.execute(
        "UPDATE maya_rp.romance_arcs SET saturation_pct=$1 WHERE character_id=$2 AND session_id=$3",
        new_sat, target_id, session_id)

    game_day = await Database.fetchval(
        "SELECT COALESCE(game_day, 1) FROM maya_rp.sessions WHERE id=$1", session_id) or 1

    crowning = random.choice([
        f"The torrent passes. {target['name']} lies spent, the tension replaced by a heavy, golden quiet.",
        f"Water drips. Steam settles. {target['name']} is remade in the aftermath.",
        f"The keeper rests. The door is closed, but the room is warm now. {target['name']} breathes.",
    ])

    await Database.execute(
        "INSERT INTO maya_rp.intimacy_events (session_id, character_id, event_type, intensity, narrative, bond_delta) "
        "VALUES ($1, $2, 'aftercare', $3, $4, 0)",
        session_id, target_id, new_sat, crowning)

    info("romance", f"Aftercare: {target['name']} saturation {target['saturation_pct'] or 0} -> {new_sat}")

    return {
        "target": target["name"],
        "game_day": game_day,
        "saturation_after": new_sat,
        "crowning_prompt": crowning,
        "instruction": "Write the aftercare. The washing, the tender words, the grounding after the climax.",
    }
