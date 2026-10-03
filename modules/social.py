#!/usr/bin/env python3
"""
Social Module — Full port from JS rpg-social skill.
Sources: crew-relationships.js, loyalty-engine.js, morale-tracker.js, social-events.js
All 4 JS files fully ported.

Systems:
  - Crew relationships: bond tracking, shift, network detection, ringleader detection
  - Loyalty engine: score calculation, classification, mutiny risk assessment
  - Morale tracker: 5-tier morale (content→mutiny), event modifiers, tension narrative
  - Social events: 12 event types (banquet, funeral, trial, etc.), participant selection, dialogue scripts
"""

from __future__ import annotations
import random
import json
from typing import Any

from core.db import Database
from core.config import Config
from core.log import error, info
from core import ooc


# ─── Constants ───────────────────────────────────────────────────

LOYALTY_FLAG_LEVELS = {
    "loyal":    {"threshold": 0.7, "desc": "Would follow into the void. Unshakeable."},
    "neutral":  {"threshold": 0.3, "desc": "Does the job. No more, no less."},
    "wavering": {"threshold": 0.15,"desc": "Watching. Waiting. Calculating odds."},
    "disloyal": {"threshold": 0,    "desc": "Actively working against command. Dangerous."},
}

MUTINY_STAGES = {
    "whispers":     {"prob": 0.05, "desc": "Quiet talk in the lower decks."},
    "recruitment":  {"prob": 0.15, "desc": "Key officers approached. Sides being drawn."},
    "planning":     {"prob": 0.30, "desc": "A meeting you were not invited to. Weapons cached."},
    "imminent":     {"prob": 0.50, "desc": "It will happen within 48 hours. Choose your side now."},
    "active":       {"prob": 0.80, "desc": "The bridge door is barricaded. Alarms scream."},
}

MORALE_THRESHOLDS = {
    "content":   {"min": 70, "max": 100, "effects": ["bonus_production","spontaneous_celebration","loyalty_cemented"]},
    "stable":    {"min": 40, "max": 69,  "effects": ["normal_operations"]},
    "grumbling": {"min": 25, "max": 39,  "effects": ["efficiency_penalty","loyalty_tests","minor_arguments"]},
    "crisis":    {"min": 10, "max": 24,  "effects": ["open_fights","sabotage_risk","desertion_risk","mutiny_whispers"]},
    "mutiny":    {"min": 0,  "max": 9,   "effects": ["officers_challenged","ship_control_stake","civil_war_risk"]},
}

BASE_MORALE_MODIFIERS = {
    "battle_victory": 10, "battle_defeat": -15, "battle_retreat": -10, "enemy_routed": 8,
    "new_ship_commissioned": 5, "ship_lost": -25, "crew_death": -20, "crew_injury": -5,
    "supply_shortage": -10, "supply_surplus": 5, "good_speech": 15, "poor_speech": -5,
    "injustice_perceived": -20, "justice_served": 12, "companion_present": 5,
    "companion_absent": -2, "shore_leave": 8, "extended_deployment": -5,
    "famine": -15, "feast": 10, "betrayal_revealed": -30, "hero_recognized": 8,
    "promotion_ceremony": 10,
}

SOCIAL_EVENT_TYPES = {
    "banquet":         {"icon": "\U0001f37d\ufe0f", "mood": "celebratory",  "min": 10, "duration": "1-2 scenes"},
    "ceremony":        {"icon": "\U0001f396\ufe0f", "mood": "formal",       "min": 20, "duration": "1 scene"},
    "argument":        {"icon": "\U0001f4a2",       "mood": "tense",        "min": 2,  "duration": "1 scene"},
    "funeral":         {"icon": "\U0001f56f\ufe0f", "mood": "somber",       "min": 10, "duration": "2 scenes"},
    "rally":           {"icon": "\U0001f4e2",       "mood": "charged",      "min": 30, "duration": "1 scene"},
    "confrontation":   {"icon": "\u26a1",           "mood": "volatile",     "min": 3,  "duration": "1-2 scenes"},
    "reconciliation":  {"icon": "\U0001f91d",       "mood": "tender",       "min": 2,  "duration": "1 scene"},
    "celebration":     {"icon": "\U0001f389",       "mood": "joyful",       "min": 20, "duration": "1-2 scenes"},
    "mentorship":      {"icon": "\U0001f4da",       "mood": "gentle",       "min": 2,  "duration": "1 scene"},
    "gossip":          {"icon": "\U0001f5e3\ufe0f", "mood": "murmuring",    "min": 2,  "duration": "0.5 scene"},
    "confession":      {"icon": "\U0001f494",       "mood": "intimate",     "min": 2,  "duration": "1 scene"},
    "trial":           {"icon": "\u2696\ufe0f",     "mood": "grave",        "min": 15, "duration": "2-3 scenes"},
}

PERSONALITY_VOICES = {
    "veteran":     {"cadence": "measured",   "lines": ["Seen worse. Fought worse.", "Orders, Captain?"]},
    "optimist":    {"cadence": "bright",     "lines": ["Told you we would make it!", "Nothing a hot meal cannot fix."]},
    "cynic":       {"cadence": "dry",        "lines": ["Another brilliant plan.", "I will believe it when I see it."]},
    "devoted":     {"cadence": "earnest",    "lines": ["Where you go, I go.", "Always, Captain."]},
    "traumatized": {"cadence": "quiet",      "lines": ["...I still see them.", "Some nights I do not sleep."]},
    "ambitious":   {"cadence": "sharp",      "lines": ["Opportunity knocks once.", "Interesting times."]},
    "stoic":       {"cadence": "flat",       "lines": ["Understood.", "Reporting as ordered."]},
    "hotheaded":   {"cadence": "rapid",      "lines": ["We hit them NOW!", "You want to wait?!"]},
}

EVENT_TRIGGER_KEYWORDS = {
    "banquet":        ["banquet", "feast", "dinner", "gather the crew for a meal", "celebrate together"],
    "ceremony":       ["ceremony", "promotion", "award", "commissioning", "medal"],
    "argument":       ["argument", "fight", "dispute", "yelling", "shouting match"],
    "funeral":        ["funeral", "burial", "memorial", "honor the dead", "goodbye", "lost"],
    "rally":          ["rally", "speech", "address", "inspire", "motivate", "gather everyone"],
    "confrontation":  ["confront", "challenge", "face off", "stand up to"],
    "reconciliation": ["forgive", "apologize", "reconcile", "make peace", "bury the hatchet"],
    "celebration":    ["celebrate", "victory party", "cheers", "success"],
    "mentorship":     ["mentor", "teach", "train", "apprentice", "show them how"],
    "gossip":         ["gossip", "rumor", "heard something", "talk among the crew"],
    "confession":     ["confess", "secret", "truth is", "never told anyone", "admit"],
    "trial":          ["trial", "court martial", "judge", "sentence", "verdict"],
}

EVENT_OPENINGS = {
    "banquet":        "The mess hall transforms. Someone found tablecloths. Someone else found wine.",
    "funeral":        "The hangar bay falls silent. The empty boots at the center speak louder than any eulogy.",
    "rally":          "The fleet channel crackles. Every screen shows the bridge. They are waiting.",
    "argument":       "Voices rise. Nearby crew members find reasons to be elsewhere.",
    "trial":          "The command deck becomes a courtroom. A table, two chairs, and the weight of judgment.",
    "confession":     "The door closes. What is said in this room stays in this room.",
    "celebration":    "Corks pop. Someone programmed the PA to play victory anthems.",
    "ceremony":       "Dress uniforms. Polished boots. The pride is real.",
    "reconciliation": "Two crew members who have not spoken in months sit across from each other.",
    "mentorship":     'The old hand pulls up a chair. "Alright, kid. Pay attention."',
    "gossip":         "Two crew members huddle near the cargo bay. Their voices drop when footsteps approach.",
    "confrontation":  "The air crackles. No one wants to be between these two right now.",
}

EVENT_CHOICES = {
    "banquet":        ["Raise a toast", "Make a speech", "Quiet observation"],
    "funeral":        ["Deliver the eulogy", "Stand in silence", "Private moment"],
    "rally":          ["Rallying cry", "Sober truth", "Personal connection"],
    "argument":       ["Mediate", "Take a side", "Shut it down"],
    "trial":          ["Prosecute", "Defend", "Judge"],
    "confession":     ["Accept", "Reject", "Stay silent"],
    "celebration":    ["Join the party", "Quiet toast", "Watch from above"],
    "ceremony":       ["Pin the medal", "Formal speech", "Personal word"],
    "reconciliation": ["Facilitate", "Comfort both", "Stay neutral"],
    "mentorship":     ["Observe", "Join in", "Promote the mentor"],
    "gossip":         ["Listen silently", "Confront", "Redirect"],
    "confrontation":  ["De-escalate", "Assert authority", "Let it play"],
}

DEMAND_POOL = [
    "Better rations and living conditions",
    "Removal of a specific officer",
    "Share of recent spoils/credits",
    "Change in fleet direction/mission",
    "Release of imprisoned crew",
    "Recognition and promotion",
    "Return to home port",
    "New captain \u2014 you or your replacement",
]

TENSION_NARRATIVES = {
    "content":   "The crew hums with purpose. Songs in the corridors. Full bellies, steady hands.",
    "stable":    "Routine holds. Repairs on schedule. Nothing to report \u2014 which is good.",
    "grumbling": "Quiet corners fill with whispers. Someone painted a warning on bulkhead C-7.",
    "crisis":    "Two crewmen brawled in the mess. Officers sleep with sidearms. Trust is a fading memory.",
    "mutiny":    "The bridge door locks from the inside now. Someone you trust will not meet your eyes.",
}

# ─── Observer suspicion (§6.1) — one-way read of the OOC meter ───
# A high-suspicion observer probes instead of sharing. The engine owns the
# value; this module only colours the scene by its band, and never writes it.
SUSPICION_PROBE_LINES = {
    "watchful": "I will keep my own counsel on that.",
    "probing": "You have been different lately. What are you not telling me?",
    "certain": "I know. Tell me the truth. Now.",
}


# ─── Relationship Helpers ────────────────────────────────────────

def _normalize_ids(a: int, b: int) -> tuple[int, int]:
    """Normalize IDs so smaller ID is always first."""
    return (a, b) if a < b else (b, a)


async def get_relationship(session_id: int, char_a: int, char_b: int) -> dict | None:
    """Get relationship between two characters. Ported from CrewRelationships.getRelationship()."""
    a, b = _normalize_ids(char_a, char_b)
    row = await Database.fetchrow(
        "SELECT * FROM maya_rp.character_relationships "
        "WHERE session_id = $1 AND char_a_id = $2 AND char_b_id = $3",
        session_id, a, b,
    )
    return dict(row) if row else None


async def shift_bond(
    session_id: int, char_a: int, char_b: int,
    delta: int, reason: str = "",
) -> dict[str, Any] | None:
    """
    Shift bond between two crew members.
    Ported from CrewRelationships.shiftBond().
    """
    a, b = _normalize_ids(char_a, char_b)
    try:
        # UPSERT
        row = await Database.fetchrow(
            "INSERT INTO maya_rp.character_relationships "
            "(session_id, char_a_id, char_b_id, score, relationship_type, last_interaction) "
            "VALUES ($1, $2, $3, $4, 'neutral', NOW()) "
            "ON CONFLICT (session_id, char_a_id, char_b_id) DO UPDATE SET "
            "  score = GREATEST(-50, LEAST(50, maya_rp.character_relationships.score + $4)), "
            "  last_interaction = NOW() "
            "RETURNING *",
            session_id, a, b, delta,
        )
        if not row:
            return None
        row = dict(row)
        bond = row["score"]
        rtype = "neutral"
        if bond > 20: rtype = "ally"
        elif bond > 5: rtype = "friend"
        elif bond < -20: rtype = "enemy"
        elif bond < -5: rtype = "rival"

        await Database.execute(
            "UPDATE maya_rp.character_relationships SET relationship_type = $1 "
            "WHERE session_id = $4 AND char_a_id = $2 AND char_b_id = $3",
            rtype, a, b, session_id,
        )
        return {"relationship": row, "type": rtype, "bond": bond}
    except Exception as e:
        error("social", f"shiftBond failed for {a}/{b}: {e}")
        return None


async def get_crew_network(session_id: int, crew_id: int) -> list[dict]:
    """Get all relationships for a crew member. Ported from CrewRelationships.getCrewNetwork()."""
    rows = await Database.fetch(
        "SELECT * FROM maya_rp.character_relationships "
        "WHERE session_id = $1 AND (char_a_id = $2 OR char_b_id = $2) "
        "ORDER BY ABS(score) DESC",
        session_id, crew_id,
    )
    return [dict(r) for r in rows]


async def get_ringleaders(session_id: int, crew_list: list[dict]) -> list[dict]:
    """
    Detect mutiny ringleaders (high centrality + low loyalty).
    Ported from CrewRelationships.getRingleaders().
    """
    all_data = []
    for member in crew_list:
        network = await get_crew_network(session_id, member.get("id", member.get("crew_id", 0)))
        all_data.append({
            "crew_id": member.get("id", member.get("crew_id")),
            "network_size": len(network),
            "loyalty": member.get("loyalty_flag", "neutral"),
        })

    max_network = max(1, max((r["network_size"] for r in all_data), default=1))
    # A crew with no relationships recorded yet has a largest network of zero, and the old
    # `max(..., default=1)` still returned 0 because the sequence was not empty. Every member then
    # divided by zero, so `calculate_mutiny_risk` crashed on exactly the fleet that had nothing to
    # plot: a session whose relationship table is empty.
    return [
        {"crew_id": r["crew_id"], "risk": round((r["network_size"] / max_network) * 100)}
        for r in all_data
        if r["network_size"] / max_network > 0.5 and r["loyalty"] in ("disloyal", "wavering")
    ]


# ─── Loyalty Engine ──────────────────────────────────────────────

def calculate_loyalty(
    crew_member: dict,
    fleet_morale: int = 50,
    recent_events: list[dict] | None = None,
) -> float:
    """
    Calculate crew member loyalty score (0-1).
    Ported from LoyaltyEngine.calculateLoyalty().
    """
    if recent_events is None:
        recent_events = []
    score = 0.5

    lf = crew_member.get("loyalty_flag", "neutral")
    if lf == "loyal": score += 0.3
    elif lf == "wavering": score -= 0.15
    elif lf == "disloyal": score -= 0.3

    score += (crew_member.get("morale", 50) - 50) * 0.002
    score += (fleet_morale - 50) * 0.001

    traits = _traits_list(crew_member.get("personality_traits"))
    if "devoted" in traits: score += 0.2
    if "ambitious" in traits: score -= 0.1
    if "traumatized" in traits: score -= 0.05
    if "cynic" in traits: score -= 0.05

    for ev in recent_events:
        # `test_crew_loyalty` feeds rows straight out of `social_events`, whose column is
        # `event_type`, while a caller passing a JS-shaped dict uses `type`. Reading only `type`
        # meant no event modifier ever applied to a live event.
        et = ev.get("type") or ev.get("event_type", "")
        if et == "injustice": score -= 0.1
        if et == "hero_recognized" and ev.get("target") == crew_member.get("name"): score += 0.15
        if et == "betrayal_revealed": score -= 0.15
        if et == "good_speech": score += 0.05

    return max(0.0, min(1.0, score))




def _traits_list(traits):
    """Personality traits as a list — safe against malformed JSON strings."""
    if isinstance(traits, list):
        return traits
    if isinstance(traits, str):
        try:
            return json.loads(traits)
        except (ValueError, TypeError):
            return []
    return []


def classify_loyalty(score: float) -> str:
    """Classify loyalty flag from score. Ported from LoyaltyEngine.classifyLoyalty().

    Read from `LOYALTY_FLAG_LEVELS` rather than restating its four thresholds, so the table and the
    classifier cannot disagree.
    """
    for flag, cfg in sorted(LOYALTY_FLAG_LEVELS.items(), key=lambda kv: -kv[1]["threshold"]):
        if score >= cfg["threshold"]:
            return flag
    return "disloyal"


async def test_crew_loyalty(
    session_id: int | None = None,
) -> list[dict]:
    """
    Test loyalty of all crew, update DB.
    Ported from LoyaltyEngine.testCrewLoyalty().
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    crew_rows = await Database.fetch(
        "SELECT id, name, role, morale, loyalty_flag, personality_traits, faction_alignment "
        "FROM maya_rp.crew_roster WHERE session_id = $1", session_id,
    )
    fleet_morale = await _get_fleet_morale(session_id)

    results = []
    # Recent events feed the loyalty calculation — event-based modifiers
    # (injustice, hero_recognized, betrayal, good_speech) now apply.
    recent_events = await Database.fetch(
        "SELECT event_type, title FROM maya_rp.social_events "
        "WHERE session_id=$1 ORDER BY id DESC LIMIT 20", session_id)
    for row in crew_rows:
        c = dict(row)
        score = calculate_loyalty(c, fleet_morale, [dict(e) for e in recent_events])
        new_flag = classify_loyalty(score)
        changed = c["loyalty_flag"] != new_flag

        if changed:
            await Database.execute(
                "UPDATE maya_rp.crew_roster SET loyalty_flag = $1 WHERE id = $2",
                new_flag, c["id"],
            )

        results.append({
            "id": c["id"], "name": c["name"],
            "loyalty_score": round(score, 2),
            "loyalty_flag": new_flag,
            "previous_flag": c["loyalty_flag"],
            "flag_changed": changed,
            "at_risk": score < 0.3,
        })
    return results


async def calculate_mutiny_risk(
    session_id: int | None = None,
) -> dict[str, Any]:
    """
    Calculate mutiny risk for the fleet.
    Ported from LoyaltyEngine.calculateMutinyRisk().
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    crew = await test_crew_loyalty(session_id)
    total = len(crew)
    if total == 0:
        # Every early return must carry the same keys, or a caller that reads the new field gets a
        # KeyError on exactly the session that has no crew, which is the session most likely to be
        # asked why nothing is happening.
        return {"risk_level": "none", "probability": 0, "stage": "none", "ringleaders": [],
                "network_ringleaders": []}

    disloyal = [c for c in crew if c["loyalty_flag"] == "disloyal"]
    wavering = [c for c in crew if c["loyalty_flag"] == "wavering"]
    at_risk = len(disloyal) + len(wavering) * 0.5
    ratio = at_risk / total

    ringleaders = [
        {"name": c["name"], "score": c["loyalty_score"]}
        for c in disloyal if c.get("loyalty_score", 1) < 0.3
    ]

    stage = "none"
    prob = 0
    for stage_name, cfg in MUTINY_STAGES.items():
        if ratio >= cfg["prob"]:
            stage = stage_name
            prob = ratio

    risk = "critical" if ratio > 0.5 else "high" if ratio > 0.3 else "moderate" if ratio > 0.15 else "low"

    # `get_ringleaders` ranks by crew network centrality rather than by loyalty score, so it finds the
    # influential malcontents the score list misses. It was unreachable; it is a second signal now.
    network_ringleaders = await get_ringleaders(session_id, crew)

    return {
        "risk_level": risk,
        "probability": round(prob * 100),
        "stage": stage,
        "ringleaders": ringleaders[:5],
        "network_ringleaders": network_ringleaders[:5],
        "disloyal_count": len(disloyal),
        "wavering_count": len(wavering),
        "loyal_count": total - len(disloyal) - len(wavering),
    }


def generate_mutiny_scene(ship_name: str, ringleaders: list[dict]) -> dict[str, Any]:
    """
    Generate mutiny scenario data.
    Ported from LoyaltyEngine.triggerMutiny() + generateDemands().
    """
    leader = ringleaders[0] if ringleaders else {"name": "Unknown", "score": 0}

    pool = list(DEMAND_POOL)
    random.shuffle(pool)
    demands = pool[:min(len(ringleaders) + 1, 3)]

    return {
        "ship": ship_name,
        "leader": leader.get("name", "Unknown"),
        "demands": demands,
        "options": [
            "Negotiate \u2014 hear their demands, find common ground",
            "Crush \u2014 overwhelming show of force, make an example",
            "Divide \u2014 appeal to neutrals, isolate the ringleaders",
            "Concede \u2014 meet their demands, risk appearing weak",
        ],
        "companion_advice": {
            "Nethara": "!Crushing mutiny is tactical. But it breeds the next one. Listen first.",
            "Melano": "...I have seen empires fall to whispers. Hear them.",
            "Valia": "*Every mutiny begins with a question no one answered. Ask it now.*",
        },
    }


# ─── Morale Tracker ──────────────────────────────────────────────

def get_morale_status(morale: int) -> dict[str, Any]:
    """Get morale threshold status. Ported from MoraleTracker.getMoraleStatus()."""
    score = max(0, min(100, morale))
    for key, r in MORALE_THRESHOLDS.items():
        if r["min"] <= score <= r["max"]:
            return {"status": key, "current": score, "effects": r["effects"], **r}
    return {"status": "stable", "current": score, "min": 40, "max": 69, "effects": ["normal_operations"]}


def apply_morale_event(
    current_morale: int, event_type: str, multiplier: float = 1.0
) -> dict[str, Any]:
    """
    Apply a morale modifier event.
    Ported from MoraleTracker.applyEvent().

    An unknown event used to read as a zero-point event: the caller got a full result dict, morale
    did not move, and nothing named the typo.
    """
    base_delta = BASE_MORALE_MODIFIERS.get(event_type, 0)
    delta = round(base_delta * multiplier)
    old_status = get_morale_status(current_morale)
    new_morale = max(0, min(100, current_morale + delta))
    new_status = get_morale_status(new_morale)

    result = {
        "old_morale": current_morale,
        "new_morale": new_morale,
        "delta": delta,
        "old_status": old_status["status"],
        "new_status": new_status["status"],
        "threshold_crossed": old_status["status"] != new_status["status"],
        "descending": new_status["status"] in ("mutiny", "crisis"),
        "effects": new_status["effects"],
    }
    if event_type not in BASE_MORALE_MODIFIERS:
        result["applied"] = False
        result["error"] = f"unknown morale event '{event_type}'"
        result["available"] = sorted(BASE_MORALE_MODIFIERS)
    return result


def get_tension_narrative(morale: int) -> str:
    """Get descriptive tension text. Ported from MoraleTracker.getTensionNarrative()."""
    status = get_morale_status(morale)
    return TENSION_NARRATIVES.get(status["status"],
        "The crew endures. For now.")


def get_pending_events(morale: int) -> list[str]:
    """Check for morale-based event triggers. Ported from MoraleTracker.getPendingEvents()."""
    status = get_morale_status(morale)
    events = []
    if status["status"] == "grumbling": events.append("argument_possible")
    if status["status"] == "crisis": events.append("confrontation_imminent")
    if status["status"] == "mutiny": events.append("mutiny_warning")
    if morale <= 5: events.append("mutiny_now")
    return events


def _morale_value(value) -> int:
    """A crew member at morale 0 is at 0, not at the default.

    `value or 50` read the bottom of the scale as a missing row. `_get_fleet_morale` then averaged
    that member at 50, and `update_morale` *raised* them to 50 plus the delta, so the crew closest to
    mutiny was the one the tick quietly promoted.
    """
    return 50 if value is None else value


async def _get_fleet_morale(session_id: int) -> int:
    """Calculate fleet-wide average morale from crew_roster."""
    rows = await Database.fetch(
        "SELECT morale FROM maya_rp.crew_roster WHERE session_id = $1", session_id
    )
    if not rows:
        return 50
    return round(sum(_morale_value(r["morale"]) for r in rows) / len(rows))


async def update_morale(
    session_id: int,
    delta: int,
    reason: str = "",
) -> int:
    """
    Update fleet-wide morale.
    Ported from MoraleTracker.applyEvent() applied to all crew.
    """
    rows = await Database.fetch(
        "SELECT id, name, morale FROM maya_rp.crew_roster WHERE session_id = $1", session_id
    )
    before_sum = after_sum = 0
    for r in rows:
        before = _morale_value(r["morale"])
        new_morale = max(0, min(100, before + delta))
        before_sum += before
        after_sum += new_morale
        await Database.execute(
            "UPDATE maya_rp.crew_roster SET morale = $1 WHERE id = $2",
            new_morale, r["id"],
        )
    if rows:
        # morale_history is fleet/ship graded: (ship_id, fleet_wide,
        # morale_before, morale_after, cause). The old per-crew INSERT named
        # columns that do not exist (character_id/morale_level/reason) — it
        # failed on every call, and this one fleet-wide row also avoids writing
        # 4,000+ history rows per morale event.
        await Database.execute(
            "INSERT INTO maya_rp.morale_history (session_id, fleet_wide, morale_before, morale_after, cause) "
            "VALUES ($1, true, $2, $3, $4)",
            session_id, round(before_sum / len(rows)), round(after_sum / len(rows)), reason,
        )

    fleet = await _get_fleet_morale(session_id)
    info("social", f"Morale: {'+' if delta > 0 else ''}{delta} fleet={fleet}")
    return fleet


# ─── Social Events ───────────────────────────────────────────────

def detect_event_type(
    player_text: str,
    context: dict | None = None,
) -> str | None:
    """
    Detect event type from player text + context.
    Ported from SocialEvents.detectEventType().
    """
    if context is None:
        context = {}
    lower = player_text.lower()

    for event_type, keywords in EVENT_TRIGGER_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return event_type

    # Context-based fallback
    fm = context.get("fleet_morale", 100)
    if fm <= 10: return "confrontation"
    if context.get("recent_death"): return "funeral"
    if context.get("victory"): return "celebration"

    return None


def get_social_event_config(event_type: str) -> dict:
    """Get event template config. Ported from SocialEvents.getEventConfig().

    An unknown type was answered with the banquet template, so a typo produced a banquet that called
    itself whatever the caller had asked for.
    """
    if event_type not in SOCIAL_EVENT_TYPES:
        return {"error": f"unknown social event type '{event_type}'",
                "available": sorted(SOCIAL_EVENT_TYPES)}
    return SOCIAL_EVENT_TYPES[event_type]


def _observer_probe(reading: dict, participants: list[dict]) -> dict | None:
    """A probe beat when the watcher is in the scene and suspicious enough (§6.1).

    @param reading - `core.ooc.suspicion_reading` result.
    @param participants - scene participants.
    @returns the beat, or None when nobody in this scene is watching.
    """
    line = SUSPICION_PROBE_LINES.get(reading.get("band"))
    name = reading.get("name")
    if not line or not name:
        return None
    if not any(p.get("name") == name for p in participants):
        return None
    return {
        "type": "observer_probe",
        "speaker": name,
        "band": reading["band"],
        "suspicion": reading["suspicion"],
        "line": line,
    }


async def generate_social_event(
    session_id: int,
    event_type: str,
    companions: list[str] | None = None,
) -> dict[str, Any]:
    """
    Generate a social event with participants and dialogue script.
    Ported from SocialEvents.getParticipants() + getDialogueScript().
    """
    if companions is None:
        companions = []

    if event_type not in SOCIAL_EVENT_TYPES:
        # The banquet template answered for any unknown name, so `feast` gathered a banquet's
        # agenda and reported the caller's word back as the event type.
        return {"error": f"unknown social event type '{event_type}'",
                "available": sorted(SOCIAL_EVENT_TYPES)}

    crew = await Database.fetch(
        "SELECT id, name, role, loyalty_flag, personality_traits "
        "FROM maya_rp.crew_roster WHERE session_id = $1", session_id
    )
    config = SOCIAL_EVENT_TYPES[event_type]
    crew_list = [dict(r) for r in crew]
    participants = []

    # Add companions
    for comp_name in companions:
        participants.append({"name": comp_name, "role": "companion", "type": "companion"})

    # Select NPCs
    remaining = [c for c in crew_list if c["name"] not in companions]

    npc_participants = _select_event_npcs(event_type, remaining)
    # `config["min"]` is the event's own claim about attendance. It was read into `needed` and then
    # dropped, so a rally that asks for thirty crew gathered ten. The type-specific selection stands
    # and the scene is topped up to the minimum from the crew nobody has picked yet.
    if len(participants) + len(npc_participants) < config["min"]:
        chosen = {p["name"] for p in npc_participants}
        for c in remaining:
            if len(participants) + len(npc_participants) >= config["min"]:
                break
            if c["name"] in chosen:
                continue
            npc_participants.append({"name": c["name"], "role": "attendee", "type": "npc"})
            chosen.add(c["name"])
    participants.extend(npc_participants)

    # Companion voice line
    # companion_line is assigned only when a companion has a line, and c_name
    # only exists inside the loop — the check below used to read both unbound.
    companion_line = None
    c_name = None
    for c_name in companions:
        cl = companions if companions else []
        if c_name in ("Nethara", "Melano", "Valia"):
            companion_line = {
                "Nethara": "!This crew needs to see strength. Or compassion. Decide which.",
                "Melano": "...I remember the last time this happened. It did not end well.",
                "Valia": "*The emotional weight in this room... it bends the light.*",
            }.get(c_name)

    # Dialogue beats
    beats = [
        {"type": "opening", "speaker": "narrator", "line": EVENT_OPENINGS.get(event_type, "The crew gathers.")},
    ]
    if companion_line:
        marker = "!" if c_name == "Nethara" else "..." if c_name == "Melano" else "*"
        beats.append({"type": "companion_weigh_in", "speaker": c_name, "marker": marker, "line": companion_line})

    for npc in npc_participants[:3]:
        # `_traits_list` already owns "parse the JSON, fall back to nothing", and the inline copy here
        # used a bare `except:` that swallowed every error class including a KeyboardInterrupt.
        traits = _traits_list(npc.get("personality_traits")) or ["stoic"]
        personality = traits[0] if traits else "stoic"
        voice = PERSONALITY_VOICES.get(personality, PERSONALITY_VOICES["stoic"])
        beats.append({"type": "dialogue", "speaker": npc["name"], "role": npc.get("role", "crew"),
                       "line": random.choice(voice["lines"]), "personality": voice["cadence"]})

    beats.append({
        "type": "player_moment", "speaker": "system",
        "line": "Your turn to speak.",
        "choices": EVENT_CHOICES.get(event_type,
            ["Speak", "Act", "Stay silent", "Free action"]),
    })

    # §6.1 — read the OOC suspicion meter (never write it): an observer in this
    # scene who has grown suspicious shares less and probes instead.
    reading = await ooc.suspicion_reading(session_id)
    probe = _observer_probe(reading, participants)
    if probe:
        beats.insert(len(beats) - 1, probe)

    # Save to social_events
    await Database.execute(
        "INSERT INTO maya_rp.social_events "
        "(session_id, event_type, title, participants, outcome) "
        "VALUES ($1, $2, $3, $4::jsonb, 'pending')",
        session_id, event_type, f"Social: {event_type}",
        json.dumps(participants),
    )

    return {
        "event_type": event_type,
        "config": config,
        "participants": participants,
        "beats": beats,
        "morale_impact": BASE_MORALE_MODIFIERS.get(f"social_{event_type}", 0),
        "suspicion": reading,
    }


def _select_event_npcs(event_type: str, crew: list[dict]) -> list[dict]:
    """Select NPCs for event based on type."""
    participants = []

    if event_type == "argument":
        hot = next((c for c in crew if isinstance(c.get("personality_traits"), (list, str))
                    and ("hotheaded" in _traits_list(c.get("personality_traits")))), None)
        cold = next((c for c in crew if isinstance(c.get("personality_traits"), (list, str))
                     and any(t in _traits_list(c.get("personality_traits")) for t in ["cynic","stoic"])), None)
        if hot: participants.append({"name": hot["name"], "role": "instigator", "type": "npc"})
        if cold: participants.append({"name": cold["name"], "role": "opponent", "type": "npc"})

    elif event_type == "funeral":
        officers = [c for c in crew if c.get("role") in ("officer", "XO")]
        for o in officers[:3]:
            participants.append({"name": o["name"], "role": "speaker", "type": "npc"})

    elif event_type == "trial":
        accused = next((c for c in crew if c.get("loyalty_flag") == "disloyal"), crew[0] if crew else None)
        if accused: participants.append({"name": accused["name"], "role": "accused", "type": "npc"})
        judge = next((c for c in crew if c.get("role") == "officer" and c != accused), None)
        if judge: participants.append({"name": judge["name"], "role": "judge", "type": "npc"})

    elif event_type == "mentorship":
        vet = next((c for c in crew if isinstance(c.get("personality_traits"), (list, str))
                    and "veteran" in _traits_list(c.get("personality_traits"))), None)
        rookie = next((c for c in crew if c != vet), None)
        if vet: participants.append({"name": vet["name"], "role": "mentor", "type": "npc"})
        if rookie: participants.append({"name": rookie["name"], "role": "student", "type": "npc"})

    elif event_type == "confession":
        if crew: participants.append({"name": crew[0]["name"], "role": "confessor", "type": "npc"})

    else:
        for c in crew[:max(1, min(10, len(crew)))]:
            participants.append({"name": c["name"], "role": "attendee", "type": "npc"})

    return participants


# ─── Tick ────────────────────────────────────────────────────────

async def run_tick(session_id: int | None = None) -> dict[str, Any]:
    """
    Social module tick: test loyalty, calculate mutiny risk, log summary.
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    try:
        mutiny = await calculate_mutiny_risk(session_id)
        fleet_morale = await _get_fleet_morale(session_id)
        morale = get_morale_status(fleet_morale)
        # Two pure helpers the tick never called: they turn the number into the sentence a GM reads,
        # which is why they existed and why nothing showed them.
        tension = get_tension_narrative(fleet_morale)
        pending = get_pending_events(fleet_morale)
        # §6.1 — read-only: the OOC meter colours the tick, it is never written here.
        reading = await ooc.suspicion_reading(session_id)

        info("social", f"Tick: fleet_morale={fleet_morale} [{morale['status']}] mutiny={mutiny['risk_level']} ({mutiny['probability']}%)"
                       f" observer={reading['band']} ({reading['suspicion']})")
        return {
            "fleet_morale": fleet_morale,
            "morale_status": morale["status"],
            "tension": tension,
            "pending_events": pending,
            "mutiny_risk": mutiny["risk_level"],
            "mutiny_probability": mutiny["probability"],
            "mutiny_stage": mutiny["stage"],
            "ringleaders": len(mutiny["ringleaders"]),
            "observer_suspicion": reading,
        }
    except Exception as e:
        error("social", f"tick failed for session {session_id}: {e}")
        return {"error": str(e)}
