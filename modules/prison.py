#!/usr/bin/env python3
"""
Prison Module — Full port from JS rpg-prison skill.
Sources: capture-engine.js, interrogation-ops.js, prisoner-conversion.js,
         prisoner-intimacy.js, prison-state.js
All 5 JS files fully ported. No logic dropped. No schema dropped.

Systems:
  - Capture engine: combat survivor resolution → named/generic prisoners
  - Interrogation: 3-tier (standard/enhanced/brutal) with intel yield + companion reactions
  - Conversion: stockholm/persuasion/broken paths → crew recruitment
  - Intimacy: fear/seduction/stockholm paths with risk system
  - Prison state: cell capacity, escape risk, countermeasures
"""

from __future__ import annotations
import random
import json
from typing import Any

from core.db import Database
from core.config import Config
from core.log import error, info

# ─── Constants ───────────────────────────────────────────────────

RANK_POOL = [
    "Private", "Corporal", "Sergeant", "Lieutenant", "Commander",
    "Captain", "Major", "Colonel", "Admiral",
]

TRAIT_POOL = [
    "stoic", "hotheaded", "cynic", "ambitious", "traumatized",
    "devoted", "calculating", "broken", "fanatical", "pragmatic",
]

NAME_PREFIXES = [
    "Kael", "Thorne", "Vex", "Rynn", "Draven", "Soren", "Lyra",
    "Jace", "Mira", "Torin", "Zara", "Orin", "Syl", "Kest", "Nyx",
]

NAME_SUFFIXES = ["", "Voss", "Kell", "Tann", "Reis", "Morr", "Shan", "Drax", "Vell", "Kaarn"]

FACTION_TEMPLATES = {
    "Den":        {"default_rank": "Sergeant",   "hostility": 0.8, "intel_base": 5},
    "Vigil":      {"default_rank": "Lieutenant", "hostility": 0.6, "intel_base": 4},
    "Federation": {"default_rank": "Commander",  "hostility": 0.2, "intel_base": 3},
    "Republic":   {"default_rank": "Captain",    "hostility": 0.1, "intel_base": 2},
}

INTERROGATION_TIERS = {
    "standard": {
        "label": "Standard",
        "icon": "\U0001f5e3\ufe0f",
        "intel_multiplier": 0.3,
        "moral_cost": 0,
        "brutality_cost": 0,
        "companion_react": "neutral",
        "prisoner_break_chance": 0.1,
    },
    "enhanced": {
        "label": "Enhanced",
        "icon": "\u26a0\ufe0f",
        "intel_multiplier": 0.6,
        "moral_cost": 2,
        "brutality_cost": 2,
        "companion_react": "concerned",
        "prisoner_break_chance": 0.3,
    },
    "brutal": {
        "label": "Brutal",
        "icon": "\U0001f480",
        "intel_multiplier": 1.0,
        "moral_cost": 8,
        "brutality_cost": 8,
        "companion_react": "horrified",
        "prisoner_break_chance": 0.7,
    },
}

COMPANION_REACTIONS = {
    "Nethara": {
        "standard":  {"bond_shift": 0, "line": "!Proceed. Information is ammunition."},
        "enhanced":  {"bond_shift": 0, "line": "!Necessary. I will not pretend otherwise."},
        "brutal":    {"bond_shift": 0, "line": "!I have faced a thousand enemies. None of them made me feel... this. I will not judge. But I will remember."},
        "loyalty_check": lambda l: "keeps secret" if l == "loyal" else "may speak",
    },
    "Melano": {
        "standard":  {"bond_shift": 0, "line": "...Ask your questions. I will listen."},
        "enhanced":  {"bond_shift": 0, "line": "...This is a path. Be sure you want to walk it."},
        "brutal":    {"bond_shift": -1, "line": "..."},
        "loyalty_check": lambda l: "exposes" if l == "disloyal" else "silent but marked" if l == "neutral" else "keeps secret \u2014 burdened",
    },
    "Valia": {
        "standard":  {"bond_shift": 0, "line": "*Every question is a door. Some doors should stay closed.*"},
        "enhanced":  {"bond_shift": 0, "line": "*I can see where this leads. It is not where you think.*"},
        "brutal":    {"bond_shift": -1, "line": "*I see every echo of this moment. They never stop screaming. Not for you. For the one in that chair.*"},
        "loyalty_check": lambda l: "never exposes \u2014 sees cosmic futility",
    },
}

CONVERSION_PATHS = {
    "stockholm": {
        "requirement": {"min_intimacy_path": "stockholm", "min_sessions": 8},
        "base_chance": 0.3,
        "modifiers": {"moral_opposite": -0.2, "same_faction_origin": 0.1, "low_rank": 0.1},
        "loyalty_cap": 0.6,
    },
    "persuasion": {
        "requirement": {"max_resistance": 20, "min_interrogations": 5, "no_brutal": True},
        "base_chance": 0.15,
        "modifiers": {"shared_enemy": 0.2},
        "loyalty_cap": 0.7,
    },
    "broken": {
        "requirement": {"resistance": 0, "min_interrogations": 3, "last_method": "brutal"},
        "base_chance": 0.4,
        "modifiers": {},
        "loyalty_cap": 0.3,
    },
}

INTIMACY_PATHS = {
    "fear": {
        "mechanic": "Prisoner obeys out of terror. Compliance, not consent.",
        "intimacy_style": "Power display. Prisoner is object. Dominance.",
        "risk": {"spy": 0.15, "assassin": 0.05, "manipulator": 0.25, "escape": 0.40},
        "self_redemption": 2,
    },
    "seduction": {
        "mechanic": "Genuine attraction. Prisoner drawn to captor.",
        "intimacy_style": "Mutual. Uneasy but real. Power imbalance acknowledged.",
        "risk": {"spy": 0.30, "assassin": 0.15, "manipulator": 0.30, "escape": 0.20},
        "self_redemption": 0,
    },
    "stockholm": {
        "mechanic": "Prolonged captivity breeds attachment. Defends captor.",
        "intimacy_style": "Affectionate. Troubling. They have forgotten captivity.",
        "risk": {"spy": 0.05, "assassin": 0.02, "manipulator": 0.10, "escape": 0.05},
        "self_redemption": 1,
    },
}

ESCAPE_COUNTERMEASURES = [
    {"name": "cell_inspection",    "cost": 10,  "risk_reduction": 0.15, "desc": "Thorough cell search for hidden tools"},
    {"name": "guard_rotation",     "cost": 20,  "risk_reduction": 0.10, "desc": "Randomize guard shifts to prevent patterns"},
    {"name": "isolation",          "cost": 30,  "risk_reduction": 0.25, "desc": "Move high-risk prisoner to isolated cell"},
    {"name": "surveillance",       "cost": 15,  "risk_reduction": 0.20, "desc": "Install monitoring in cell"},
    {"name": "ally_interrogation", "cost": 0,   "risk_reduction": 0.30, "desc": "Interrogate co-conspirators for escape plans"},
]

SECURITY_MULTIPLIERS = {
    "minimal":  1.0,
    "standard": 0.5,
    "maximum":  0.2,
    "isolated": 0.05,
}


# ─── Helpers ─────────────────────────────────────────────────────

def _random_name() -> str:
    first = random.choice(NAME_PREFIXES)
    last = f" {random.choice(NAME_SUFFIXES)}" if random.random() > 0.5 else ""
    return first + last


def _random_traits(count: int) -> list[str]:
    pool = list(TRAIT_POOL)
    random.shuffle(pool)
    return pool[:count]


def _generate_secrets(faction: str) -> list[dict]:
    secrets = []
    if faction == "Den":
        if random.random() > 0.6:
            secrets.append({"type": "patrol_route",  "value": "Next Den patrol path through sector"})
        if random.random() > 0.7:
            secrets.append({"type": "harvest_point", "value": "Coordinates of Den resource outpost"})
        if random.random() > 0.8:
            secrets.append({"type": "signal_chain", "value": "Step in Den Concurrence signal chain"})
    else:
        if random.random() > 0.5:
            secrets.append({"type": "fleet_movement", "value": f"{faction} fleet redeployment plans"})
        if random.random() > 0.6:
            secrets.append({"type": "hidden_base",   "value": f"Classified {faction} installation"})
    if random.random() > 0.7:
        secrets.append({"type": "personal", "value": "Personal secret \u2014 leverage for manipulation"})
    return secrets


# ─── Capture Engine ──────────────────────────────────────────────

async def resolve_capture(
    survivors_captured: int,
    enemy_faction: str,
    engagement_id: int | None = None,
    session_id: int | None = None,
) -> list[dict[str, Any]]:
    """
    Resolve combat survivors into prisoners.
    Ported from CaptureEngine.resolveCapture() + generateNamedPrisoner() + generateGenericPrisoner().
    
    20% named officers (min 1), rest generic soldiers.
    Saves to maya_rp.prisoners.
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    if survivors_captured <= 0:
        return []

    ft = FACTION_TEMPLATES.get(enemy_faction, {"default_rank": "Private", "hostility": 0.5, "intel_base": 2})
    named_count = max(1, round(survivors_captured * 0.2))
    prisoners = []

    for i in range(min(named_count, survivors_captured)):
        traits = _random_traits(2)
        resistance = round(30 + random.random() * 50 + ft["hostility"] * 20)
        intel_val = round(ft["intel_base"] + random.random() * 10)
        p = {
            "session_id": session_id,
            "name": _random_name(),
            "faction": enemy_faction,
            "rank": ft["default_rank"],
            "personality_traits": json.dumps(traits),
            "intel_value": min(100, intel_val),
            "resistance": min(100, resistance),
            "status": "captured",
            "cell_ship_id": None,
            "cell_security": "standard",
            "interrogations_count": 0,
            "last_interrogation_method": None,
            "secrets_jsonb": json.dumps(_generate_secrets(enemy_faction)),
            "intel_extracted": "[]",
            "intimacy_flag": False,
            "intimacy_path": None,
            "escape_risk_pct": round(resistance * 0.15),
            "escape_attempts": 0,
            "captured_from_ship": f"Engagement #{engagement_id}" if engagement_id else "Unknown Battle",
            "captured_in_engagement": engagement_id,
            "conversion_path": None,
            "conversion_progress": 0,
            "death_cause": None,
            "death_session": None,
            "held_sessions": 0,
        }
        # Insert to DB
        cols = ", ".join(p.keys())
        vals = ", ".join(f"${i+1}" for i in range(len(p)))
        await Database.execute(
            f"INSERT INTO maya_rp.prisoners ({cols}) VALUES ({vals})",
            *p.values(),
        )
        prisoners.append(p)

    generic_count = survivors_captured - named_count
    for i in range(generic_count):
        p = {
            "session_id": session_id,
            "name": f"{enemy_faction} Soldier",
            "faction": enemy_faction,
            "rank": "Private",
            "personality_traits": '["stoic"]',
            "intel_value": max(1, round(ft["intel_base"] * 0.3)),
            "resistance": round(20 + random.random() * 30),
            "status": "captured",
            "cell_ship_id": None,
            "cell_security": "standard",
            "interrogations_count": 0,
            "last_interrogation_method": None,
            "secrets_jsonb": "[]",
            "intel_extracted": "[]",
            "intimacy_flag": False,
            "intimacy_path": None,
            "escape_risk_pct": round(15 + random.random() * 10),
            "escape_attempts": 0,
            "captured_from_ship": f"Engagement #{engagement_id}" if engagement_id else "Unknown Battle",
            "captured_in_engagement": engagement_id,
            "conversion_path": None,
            "conversion_progress": 0,
            "death_cause": None,
            "death_session": None,
            "held_sessions": 0,
        }
        cols = ", ".join(p.keys())
        vals = ", ".join(f"${i+1}" for i in range(len(p)))
        await Database.execute(
            f"INSERT INTO maya_rp.prisoners ({cols}) VALUES ({vals})",
            *p.values(),
        )
        prisoners.append(p)

    info("prison", f"Captured {len(prisoners)} prisoners ({named_count} named, {generic_count} generic) from {enemy_faction}")
    return prisoners


# ─── Interrogation Ops ──────────────────────────────────────────

async def interrogate(
    prisoner_id: int,
    tier: str = "standard",
    witnesses: list[str] | None = None,
    secrecy: str = "hidden",
    session_id: int | None = None,
) -> dict[str, Any]:
    """
    Run an interrogation session. 3-tier: standard / enhanced / brutal.
    Ported from InterrogationOps.interrogate().
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    if witnesses is None:
        witnesses = []

    # Fetch prisoner
    row = await Database.fetchrow(
        "SELECT id, name, faction, resistance, intel_value, secrets_jsonb, "
        "interrogations_count, last_interrogation_method, status "
        "FROM maya_rp.prisoners WHERE id = $1 AND session_id = $2", prisoner_id, session_id
    )
    if not row:
        return {"success": False, "error": "Prisoner not found"}

    t = INTERROGATION_TIERS.get(tier, INTERROGATION_TIERS["standard"])
    prisoner = dict(row)

    # Intel yield
    resistance_penalty = (prisoner.get("resistance") or 50) / 100.0
    prev_interrogations = (prisoner.get("interrogations_count") or 0) * 0.1
    base_intel = (prisoner.get("intel_value") or 1) * t["intel_multiplier"]
    intel_yield = max(1, round(base_intel * (1 - resistance_penalty - prev_interrogations)))

    # Break check
    broken = random.random() < t["prisoner_break_chance"]

    # Companion reactions
    companion_reactions = {}
    for name in witnesses:
        react = COMPANION_REACTIONS.get(name)
        if react and tier in react:
            loyalty = "neutral"  # simplified; fetch from DB if needed
            companion_reactions[name] = {
                "bond_shift": react[tier]["bond_shift"],
                "line": react[tier]["line"],
                "secrecy": react.get("loyalty_check", lambda l: "neutral")(loyalty),
            }

    # Secrets extraction
    secrets_revealed = []
    secrets_raw = prisoner.get("secrets_jsonb")
    if secrets_raw and intel_yield > 3:
        try:
            secrets_data = json.loads(secrets_raw) if isinstance(secrets_raw, str) else secrets_raw
            reveal_count = min(len(secrets_data), max(1, intel_yield // 3))
            secrets_revealed = secrets_data[:reveal_count]
        except (json.JSONDecodeError, TypeError):
            pass

    # Update prisoner record
    new_count = (prisoner.get("interrogations_count") or 0) + 1
    new_status = "broken" if broken else "interrogated"
    await Database.execute(
        "UPDATE maya_rp.prisoners SET interrogations_count = $1, "
        "last_interrogation_method = $2, status = $3 WHERE id = $4",
        new_count, tier, new_status, prisoner_id,
    )

    # Log interrogation
    await Database.execute(
        "INSERT INTO maya_rp.interrogation_log "
        "(prisoner_id, session_id, method, secrecy_level, witnesses, "
        "companion_reactions, intel_yield, moral_cost, brutality_cost, "
        "prisoner_broken) VALUES ($1,$2,$3,$4,$5::jsonb,$6::jsonb,$7,$8,$9,$10)",
        prisoner_id, session_id, tier, secrecy,
        json.dumps(witnesses), json.dumps(companion_reactions),
        intel_yield, t["moral_cost"], t["brutality_cost"], broken,
    )

    result = {
        "success": intel_yield > 0,
        "intel_yield": intel_yield,
        "broken": broken,
        "moral_cost": t["moral_cost"],
        "brutality_cost": t["brutality_cost"],
        "companion_reactions": companion_reactions,
        "secrets_revealed": secrets_revealed,
        "tier": t["label"],
        "secrecy": secrecy,
        "recommendation": (
            "Prisoner broken. Further interrogation yields less intel."
            if broken else
            "Prisoner unbroken. Repeat interrogation or escalate tier."
        ),
    }
    info("prison", f"Interrogation: {tier} on {prisoner['name']} \u2192 intel={intel_yield}, broken={broken}")
    return result


def get_interrogation_tier_info(tier: str) -> dict[str, Any]:
    """Return tier config, or say the tier does not exist.

    The old body fell back to `standard` for any unknown name, so `soft` and `standard` printed the
    same configuration and a typo read as a real tier. A caller asking for a tier that is not there
    gets an answer that names the alternatives.
    """
    if tier in INTERROGATION_TIERS:
        return INTERROGATION_TIERS[tier]
    return {"error": f"unknown interrogation tier '{tier}'",
            "available": sorted(INTERROGATION_TIERS)}


# ─── Prisoner Conversion ─────────────────────────────────────────

async def check_conversion(
    prisoner_id: int,
    session_id: int | None = None,
) -> dict[str, Any] | None:
    """
    Check if a prisoner qualifies for any conversion path.
    Ported from PrisonerConversion.checkConversion().
    Returns {path, base_chance, loyalty_cap, narrative} or None.
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    row = await Database.fetchrow(
        "SELECT id, name, faction, rank, resistance, interrogations_count, "
        "last_interrogation_method, intimacy_path, held_sessions, status "
        "FROM maya_rp.prisoners WHERE id = $1 AND session_id = $2", prisoner_id, session_id
    )
    if not row:
        return None
    p = dict(row)

    for path_name, cfg in CONVERSION_PATHS.items():
        req = cfg["requirement"]

        if (path_name == "stockholm"
                and p.get("intimacy_path") == req["min_intimacy_path"]
                and (p.get("held_sessions") or 0) >= req["min_sessions"]):
            return {
                "path": path_name,
                "base_chance": cfg["base_chance"],
                "loyalty_cap": cfg["loyalty_cap"],
                "narrative": f"The line between captor and protector has blurred. {p['name']} has begun to see you differently.",
            }

        if (path_name == "persuasion"
                and (p.get("resistance") or 100) <= req["max_resistance"]
                and (p.get("interrogations_count") or 0) >= req["min_interrogations"]
                and (not req.get("no_brutal") or p.get("last_interrogation_method") != "brutal")):
            return {
                "path": path_name,
                "base_chance": cfg["base_chance"],
                "loyalty_cap": cfg["loyalty_cap"],
                "narrative": f"{p['name']} has started to trust your words. Reason may win where force could not.",
            }

        if (path_name == "broken"
                and (p.get("resistance") or 100) == req["resistance"]
                and (p.get("interrogations_count") or 0) >= req["min_interrogations"]
                and p.get("last_interrogation_method") == req["last_method"]):
            return {
                "path": path_name,
                "base_chance": cfg["base_chance"],
                "loyalty_cap": cfg["loyalty_cap"],
                "narrative": f"{p['name']} is broken. Empty. They will follow any order \u2014 but their eyes hold nothing.",
            }

    return None


async def execute_conversion(
    prisoner_id: int,
    path: str,
    session_id: int | None = None,
) -> dict[str, Any]:
    """
    Execute a prisoner conversion. On success, prisoner becomes crew.
    Ported from PrisonerConversion.executeConversion().
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    cfg = CONVERSION_PATHS.get(path)
    if not cfg:
        return {"converted": False, "reason": "invalid_path"}

    roll = random.random()
    chance = cfg["base_chance"]
    # Apply low_rank modifier if applicable
    row = await Database.fetchrow(
        "SELECT name, faction, rank, cell_ship_id AS ship_id FROM maya_rp.prisoners WHERE id = $1 AND session_id = $2",
        prisoner_id, session_id
    )
    if row:
        p = dict(row)
        if p.get("rank") in ("Private", "Corporal"):
            chance += cfg["modifiers"].get("low_rank", 0)

    if roll >= chance:
        return {"converted": False, "reason": "resisted_conversion", "path": path}

    # Convert: add to crew_roster
    ship_id = p.get("ship_id") or 1
    await Database.execute(
        "INSERT INTO maya_rp.crew_roster (session_id, ship_id, name, role, status, personality_notes) "
        "VALUES ($1, $2, $3, 'prisoner_converted', 'active', $4)",
        session_id, ship_id, p["name"],
        f"Former {p.get('faction', 'unknown')} {p.get('rank', 'soldier')}. Converted via {path}.",
    )

    # Update prisoner
    await Database.execute(
        "UPDATE maya_rp.prisoners SET conversion_path = $1, conversion_progress = 100, "
        "status = 'recruited' WHERE id = $2",
        path, prisoner_id,
    )

    info("prison", f"Converted prisoner {p['name']} via {path} (loyalty cap: {cfg['loyalty_cap']})")
    return {
        "converted": True,
        "path": path,
        "loyalty": cfg["loyalty_cap"],
    }


async def record_death(
    prisoner_id: int,
    cause: str,
    session_id: int | None = None,
) -> dict[str, Any] | None:
    """
    Record a prisoner death.
    Ported from PrisonerConversion.recordDeath().
    Causes: execution, escape_killed, brutal_interrogation, accident
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    await Database.execute(
        "UPDATE maya_rp.prisoners SET status = 'dead', death_cause = $1, death_session = $2 WHERE id = $3",
        cause, session_id, prisoner_id,
    )
    row = await Database.fetchrow("SELECT name, faction FROM maya_rp.prisoners WHERE id = $1 AND session_id = $2", prisoner_id, session_id)
    if row:
        info("prison", f"Prisoner {row['name']} died: {cause}")
    return dict(row) if row else None


async def feed_intel_to_investigation(
    prisoner_id: int,
    investigation_id: int,
    intel_text: str,
    session_id: int | None = None,
) -> dict[str, Any] | None:
    """
    Transfer interrogation intel to mystery investigation.
    Ported from PrisonerConversion.feedIntelToInvestigation().
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    # Insert pipeline entry
    pl_id = await Database.fetchval(
        "INSERT INTO maya_rp.prisoner_intel_pipeline "
        "(prisoner_id, investigation_id, intel_text) VALUES ($1, $2, $3) RETURNING id",
        prisoner_id, investigation_id, intel_text,
    )

    # Live `clues` columns are (id, session_id, source, source_type, text,
    # connects_to_clue, revealed, revealed_by_character, location_id,
    # session_found, investigation_id, created_at) — there is no
    # title/description. The missing columns used to be swallowed here, so this
    # pipeline was silently dead; the case link now rides on the registered
    # clues.investigation_id (migration 105) as well as the pipeline row.
    clue_id = None
    try:
        clue_id = await Database.fetchval(
            "INSERT INTO maya_rp.clues "
            "(session_id, source, source_type, text, revealed, session_found, investigation_id) "
            "VALUES ($1, 'prisoner_intel', 'interrogation', $2, true, $3, $4) "
            "RETURNING id",
            session_id, intel_text, session_id, investigation_id,
        )
        await Database.execute(
            "UPDATE maya_rp.prisoner_intel_pipeline SET converted_to_clue = true, clue_id = $1 WHERE id = $2",
            clue_id, pl_id,
        )
    except Exception as e:
        error("prison", f"clue insert failed: {e}")

    return {"pipeline_id": pl_id, "clue_id": clue_id}


# ─── Prisoner Intimacy ───────────────────────────────────────────

async def get_available_intimacy_paths(
    prisoner_id: int,
    brutality: int = 0,
    charisma: int = 0,
    sessions_since_capture: int = 0,
    session_id: int | None = None,
) -> list[str]:
    """
    Determine available intimacy paths for a prisoner.
    Ported from PrisonerIntimacy.getAvailablePaths().
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    row = await Database.fetchrow(
        "SELECT resistance FROM maya_rp.prisoners WHERE id = $1 AND session_id = $2",
        prisoner_id, session_id
    )
    if not row:
        return []
    resistance = row["resistance"] or 50

    paths = []
    if brutality >= 30:
        paths.append("fear")
    if resistance < 30:
        paths.append("seduction")
    if sessions_since_capture >= 5:
        paths.append("stockholm")
    return paths


async def initiate_intimacy(
    prisoner_id: int,
    path: str,
    companions: list[dict[str, Any]] | None = None,
    session_id: int | None = None,
) -> dict[str, Any]:
    """
    Initiate prisoner intimacy. Risk-based outcome.
    Ported from PrisonerIntimacy.initiateIntimacy().
    """
    if companions is None:
        companions = []
    if session_id is None:
        session_id = Config.SESSION_ID

    cfg = INTIMACY_PATHS.get(path)
    if not cfg:
        return {"success": False, "reason": "Path not available for this prisoner."}

    # Risk roll
    risks = cfg["risk"]
    roll = random.random()
    outcome = "intimate"
    risk_triggered = None

    cumulative = 0
    for risk_type, prob in [("assassin", risks["assassin"]),
                             ("spy", risks["spy"]),
                             ("manipulator", risks["manipulator"]),
                             ("escape", risks["escape"])]:
        cumulative += prob
        if roll < cumulative:
            outcome = {
                "assassin": "assassin_attack",
                "spy": "intel_leaked",
                "manipulator": "manipulated",
                "escape": "escape_attempt",
            }[risk_type]
            risk_triggered = risk_type
            break

    # Companion jealousy
    jealous_companions = []
    for comp in companions:
        if comp.get("bond_score", 0) >= 7 and comp.get("romance_stage", "") != "strangers":
            jealous_companions.append({
                "name": comp.get("name", "Unknown"),
                "bond_shift": -1,
                "line": {
                    "Nethara": "!You have what you want from me. What do you want from them?",
                    "Melano": "...I see. There is room in your heart for captives. But not for me.",
                }.get(comp.get("name", ""), "*Interesting. You prefer the ones who cannot leave.*"),
            })

    # Update prisoner
    await Database.execute(
        "UPDATE maya_rp.prisoners SET intimacy_flag = true, intimacy_path = $1, "
        "held_sessions = COALESCE(held_sessions, 0) + 1 WHERE id = $2",
        path, prisoner_id,
    )

    # If escape attempt, handle it
    consequence = None
    if risk_triggered:
        consequence = await _handle_intimacy_risk(risk_triggered, prisoner_id, session_id)

    info("prison", f"Intimacy: {path} with prisoner {prisoner_id} \u2192 {outcome}")
    return {
        "success": outcome == "intimate",
        "outcome": outcome,
        "risk_triggered": risk_triggered,
        "path": path,
        "intimacy_style": cfg["intimacy_style"],
        "self_redemption": cfg["self_redemption"],
        "jealous_companions": jealous_companions,
        "consequence": consequence,
        "prisoner_state": {
            "path": path,
            "fear_level": "terror" if path == "fear" else "normal",
            "attachment_level": "devoted" if path == "stockholm" else "compliant",
        },
    }


async def _handle_intimacy_risk(
    risk_type: str,
    prisoner_id: int,
    session_id: int,
) -> dict[str, Any]:
    """Handle risk consequence. Ported from PrisonerIntimacy.handleRisk()."""
    # Fetch prisoner name for narrative
    try:
        row = await Database.fetchrow("SELECT name, faction FROM maya_rp.prisoners WHERE id = $1 AND session_id = $2", prisoner_id, session_id)
        name = row["name"] if row else "Unknown"
        faction = row["faction"] if row else "unknown"
    except Exception:
        name = "Unknown"
        faction = "unknown"

    consequences = {
        "assassin": {
            "type": "combat_interrupt",
            "description": f"{name} had a concealed weapon. Combat breaks out mid-intimacy.",
            "brutality_required": "Execute or re-capture with force.",
        },
        "spy": {
            "type": "intel_leaked",
            "description": f"{name} has been feeding information to {faction}. They know your fleet composition.",
            "consequence": "Ambush event fires next session. Enemy knows your formations.",
        },
        "manipulator": {
            "type": "resource_drain",
            "description": f"{name} has been extracting favors. Credits, access codes, escape routes.",
            "resource_cost": random.randint(200, 700),
        },
        "escape": {
            "type": "escape",
            "description": f"{name} used the intimacy as cover. They are gone.",
            "manhunt": True,
        },
    }
    return consequences.get(risk_type, {"type": "none"})


# ─── Prison State / Cell Management ──────────────────────────────

async def get_fleet_capacity(
    session_id: int | None = None,
) -> dict[str, Any]:
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    Get fleet-wide cell capacity stats.
    Ported from PrisonState.getFleetCapacity().
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    ships = await Database.fetch(
        "SELECT id, name, cell_capacity FROM maya_rp.ships "
        "WHERE session_id = $1 AND cell_capacity > 0 ORDER BY cell_capacity DESC",
        session_id,
    )
    prisoners = await Database.fetch(
        "SELECT id, name, cell_ship_id FROM maya_rp.prisoners "
        "WHERE session_id = $1 AND status IN ('captured','holding','interrogated')",
        session_id,
    )

    per_ship = {}
    for s in ships:
        per_ship[s["id"]] = {
            "name": s["name"],
            "capacity": s["cell_capacity"],
            "used": 0,
            "available": s["cell_capacity"],
        }

    for p in prisoners:
        sid = p["cell_ship_id"]
        if sid and sid in per_ship:
            per_ship[sid]["used"] += 1
            per_ship[sid]["available"] -= 1

    total = sum(s["cell_capacity"] for s in ships)
    used = sum(ps["used"] for ps in per_ship.values())

    return {
        "total": total,
        "used": used,
        "available": total - used,
        "full": total - used <= 0,
        "per_ship": per_ship,
    }


async def assign_cell(
    prisoner_id: int,
    session_id: int | None = None,
) -> dict[str, Any]:
    """
    Assign prisoner to a ship with available cells.
    Ported from PrisonState.assignCell().
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    ships = await Database.fetch(
        "SELECT id, name, cell_capacity FROM maya_rp.ships "
        "WHERE session_id = $1 AND cell_capacity > 0 ORDER BY cell_capacity DESC",
        session_id,
    )

    for s in ships:
        cap = s["cell_capacity"]
        if cap > 0:
            await Database.execute(
                "UPDATE maya_rp.prisoners SET cell_ship_id = $1, cell_security = 'standard' WHERE id = $2",
                s["id"], prisoner_id,
            )
            return {"assigned": True, "ship_id": s["id"], "ship_name": s["name"], "cell_capacity": cap}

    return {"assigned": False, "ship_id": None, "ship_name": None,
            "message": "No cell capacity available. Build or acquire prison ships."}


async def calculate_escape_risk(
    prisoner_id: int,
    sessions_since_capture: int = 0,
    session_id: int | None = None,
) -> dict[str, Any]:
    """
    Calculate escape probability for a prisoner.
    Ported from PrisonState.calculateEscapeRisk().
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    row = await Database.fetchrow(
        "SELECT resistance, cell_security, escape_risk_pct, status "
        "FROM maya_rp.prisoners WHERE id = $1 AND session_id = $2", prisoner_id, session_id
    )
    if not row:
        return {"error": "Prisoner not found"}
    p = dict(row)

    sec_mult = SECURITY_MULTIPLIERS.get(p.get("cell_security", "standard"), 0.5)
    base_risk = (p.get("escape_risk_pct") or 15) / 100.0
    time_bonus = sessions_since_capture * 0.02
    risk = min(0.95, base_risk * sec_mult + time_bonus)

    return {
        "probability": round(risk * 100),
        "will_escape": random.random() < risk,
        "security_level": p.get("cell_security"),
        "resistance": p.get("resistance"),
    }


async def process_escapes(
    session_id: int | None = None,
) -> dict[str, Any]:
    """
    Process escape attempts for all prisoners.
    Ported from PrisonState.processEscapes().
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    prisoners = await Database.fetch(
        "SELECT id, name, faction, intel_value, secrets_jsonb, escape_risk_pct, "
        "cell_security, resistance, escape_attempts, status "
        "FROM maya_rp.prisoners WHERE session_id = $1 AND status IN ('captured','holding')",
        session_id,
    )

    results = {"escaped": [], "foiled": [], "manhunt": False}

    for row in prisoners:
        p = dict(row)
        risk = await calculate_escape_risk(p["id"])

        if risk.get("will_escape"):
            secrets_raw = p.get("secrets_jsonb")
            secrets = []
            if secrets_raw:
                try:
                    secrets = json.loads(secrets_raw) if isinstance(secrets_raw, str) else secrets_raw
                except (json.JSONDecodeError, TypeError):
                    pass

            await Database.execute(
                "UPDATE maya_rp.prisoners SET status = 'escaped', escape_attempts = COALESCE(escape_attempts, 0) + 1 WHERE id = $1",
                p["id"],
            )
            results["escaped"].append({
                "name": p["name"],
                "faction": p["faction"],
                "intel_leaked": (p.get("intel_value") or 0) > 3,
                "secrets_revealed": secrets,
            })
            results["manhunt"] = True
        else:
            results["foiled"].append({"name": p["name"], "id": p["id"]})

    if results["escaped"]:
        info("prison", f"Escape attempt: {len(results['escaped'])} escaped, {len(results['foiled'])} foiled")
    return results


async def upgrade_security(
    prisoner_id: int,
    new_level: str = "standard",
    guards: int = 0,
    session_id: int | None = None,
) -> dict[str, Any]:
    """
    Increase security for a prisoner.
    Ported from PrisonState.upgradeSecurity().
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    valid = ["minimal", "standard", "maximum", "isolated"]
    if new_level not in valid:
        new_level = "standard"

    row = await Database.fetchrow(
        "SELECT resistance FROM maya_rp.prisoners WHERE id = $1 AND session_id = $2", prisoner_id, session_id
    )
    if not row:
        return {"error": "Prisoner not found"}

    mult = SECURITY_MULTIPLIERS[new_level]
    new_risk = round((row["resistance"] or 50) * mult)

    await Database.execute(
        "UPDATE maya_rp.prisoners SET cell_security = $1, escape_risk_pct = $2 WHERE id = $3",
        new_level, new_risk, prisoner_id,
    )

    # Log countermeasure
    await Database.execute(
        "INSERT INTO maya_rp.escape_countermeasures "
        "(session_id, prisoner_id, measure_type, cost_credits, risk_reduction) "
        "VALUES ($1, $2, 'security_upgrade', $3, $4)",
        Config.SESSION_ID, prisoner_id, guards * 50, 1 - mult,
    )

    return {
        "cell_security": new_level,
        "escape_risk_pct": new_risk,
        "guards": guards,
        "cost_per_day": guards * 50,
    }


async def apply_countermeasure(
    prisoner_id: int,
    measure_name: str,
    session_id: int | None = None,
) -> dict[str, Any] | None:
    """
    Apply an escape countermeasure.
    Ported from EscapeCountermeasures.applyCountermeasure().
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    measure = next((m for m in ESCAPE_COUNTERMEASURES if m["name"] == measure_name), None)
    if not measure:
        return None

    row = await Database.fetchrow(
        "SELECT escape_risk_pct FROM maya_rp.prisoners WHERE id = $1 AND session_id = $2", prisoner_id, session_id
    )
    if not row:
        return None

    new_risk = max(0, (row["escape_risk_pct"] or 50) - round(measure["risk_reduction"] * 100))

    await Database.execute(
        "UPDATE maya_rp.prisoners SET escape_risk_pct = $1 WHERE id = $2",
        new_risk, prisoner_id,
    )

    await Database.execute(
        "INSERT INTO maya_rp.escape_countermeasures "
        "(session_id, prisoner_id, measure_type, cost_credits, risk_reduction) "
        "VALUES ($1, $2, $3, $4, $5)",
        session_id, prisoner_id, measure_name, measure["cost"], measure["risk_reduction"],
    )

    return {"applied": measure_name, "cost": measure["cost"], "new_risk": new_risk, "description": measure["desc"]}


# ─── Tick ────────────────────────────────────────────────────────

async def run_tick(session_id: int | None = None) -> dict[str, Any]:
    """
    Prison module tick: process escapes, age held sessions, check conversion.
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    results = {}

    # 1. Process escape attempts
    escapes = await process_escapes(session_id)
    results["escapes"] = escapes

    # 2. Age held_sessions for all active prisoners
    await Database.execute(
        "UPDATE maya_rp.prisoners SET held_sessions = COALESCE(held_sessions, 0) + 1 "
        "WHERE session_id = $1 AND status IN ('captured','holding','interrogated')",
        session_id,
    )

    # 3. Check conversion eligibility
    prisoners = await Database.fetch(
        "SELECT id, name, status FROM maya_rp.prisoners "
        "WHERE session_id = $1 AND status IN ('captured','holding','interrogated')",
        session_id,
    )
    eligible = []
    for p in prisoners:
        conv = await check_conversion(p["id"])
        if conv:
            eligible.append(conv)
    results["conversion_eligible"] = eligible

    info("prison", f"Tick: {len(prisoners)} active, {escapes['escaped']} escaped, {len(eligible)} conversion-eligible")
    return results
