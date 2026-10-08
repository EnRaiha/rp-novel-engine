#!/usr/bin/env python3
"""
Council Module — Full port from JS rpg-council skill.
Sources: cabinet-manager.js, conspiracy-engine.js, counter-espionage.js,
         governance-events.js, influence-tracker.js, role-manager.js
All 6 JS files fully ported.

Systems:
  - Cabinet: seats, voting, cohesion, promotions, validation
  - Conspiracy: 7 plot types, phase execution, exposure checks
  - Counter-espionage: intel network, plot detection, thwart methods
  - Governance: meetings, decrees, crises, department dispatch
  - Influence: territory control, faction standing, shadow presence
  - Roles: wife modes, tier authority, task routing, emergency chain
"""

from __future__ import annotations
import hashlib
import random
import json
from datetime import datetime
from typing import Any

from core.db import Database
from core.log import error, info
from core import ooc
from core.session import require_session


# ═══════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════

VOTE_THRESHOLDS = {"standard": 0.5, "high": 0.67, "critical": 0.75, "war": 0.85, "treaty": 1.0}

SEAT_TEMPLATES = {
    "Grand Consul":       {"tier": 0, "portfolio": "sovereign", "max_fleet_power": 0, "is_wife": False},
    "Commander":          {"tier": 1, "portfolio": "intel",     "max_fleet_power": 0, "is_wife": True},
    "Military Minister":  {"tier": 2, "portfolio": "defense",   "max_fleet_power": 1200, "is_wife": True},
    "Intel Lead":         {"tier": 2, "portfolio": "intel",     "max_fleet_power": 200, "is_wife": True},
    "Education Minister": {"tier": 2, "portfolio": "education", "max_fleet_power": 0, "is_wife": True},
    "Finance Minister":   {"tier": 2, "portfolio": "economy",   "max_fleet_power": 0, "is_wife": False},
    "Diplomacy Minister": {"tier": 2, "portfolio": "diplomacy", "max_fleet_power": 0, "is_wife": False},
    "Archivist":          {"tier": 2, "portfolio": "lore",      "max_fleet_power": 0, "is_wife": False},
    "Warden":             {"tier": 2, "portfolio": "guardian",  "max_fleet_power": 0, "is_wife": False},
    "Scout Lead":         {"tier": 3, "portfolio": "recon",     "max_fleet_power": 100, "is_wife": False},
}

PLOT_TEMPLATES = {
    "assassination": {
        "type": "covert_operation", "difficulty": 7,
        "phases": ["target_identification","asset_placement","window_assessment","execution","cleanup"],
        "required_portfolios": ["intel"], "exposure_risk": 25, "moral_cost": 15,
    },
    "coup": {
        "type": "covert_operation", "difficulty": 9,
        "phases": ["loyalty_assessment","key_personnel_turned","positioning","trigger_event","power_transfer"],
        "required_portfolios": ["intel","defense"], "exposure_risk": 40, "moral_cost": 25,
    },
    "sabotage": {
        "type": "covert_operation", "difficulty": 5,
        "phases": ["target_recon","access_route","device_placement","detonation","blame_routing"],
        "required_portfolios": ["intel"], "exposure_risk": 15, "moral_cost": 10,
    },
    "information_war": {
        "type": "covert_operation", "difficulty": 6,
        "phases": ["intel_collection","narrative_crafting","dissemination","amplification","revelation"],
        "required_portfolios": ["intel","education"], "exposure_risk": 10, "moral_cost": 5,
    },
    "faction_subversion": {
        "type": "diplomatic_campaign", "difficulty": 6,
        "phases": ["asset_recruitment","influence_building","key_defection","leadership_change","realignment"],
        "required_portfolios": ["intel","economy"], "exposure_risk": 20, "moral_cost": 8,
    },
    "economic_destabilization": {
        "type": "covert_operation", "difficulty": 7,
        "phases": ["market_assessment","asset_positioning","trigger_event","cascade","acquisition"],
        "required_portfolios": ["economy","intel"], "exposure_risk": 15, "moral_cost": 12,
    },
    "false_flag": {
        "type": "military_buildup", "difficulty": 8,
        "phases": ["target_selection","disguised_assets","incident_staging","evidence_planting","casus_belli"],
        "required_portfolios": ["defense","intel"], "exposure_risk": 35, "moral_cost": 20,
    },
}

COVER_STORIES = {
    "assassination": ["Accident during routine maintenance", "Pirate attack on transport", "Medical complication"],
    "coup": ["Cabinet reshuffle for efficiency", "Voluntary leadership transition", "Retirement with honors"],
    "sabotage": ["Technical malfunction", "Poor maintenance record", "Enemy espionage"],
    "economic_destabilization": ["Market correction", "Natural resource depletion", "Cyclical downturn"],
    "false_flag": ["Unprovoked enemy aggression", "Border skirmish escalation", "Terrorist attack"],
}

CRISIS_TEMPLATES = {
    "faction_defection": {
        "triggers": ["faction standing drops to hostile", "failed diplomacy", "cabinet overreach"],
        "immediate": "Faction withdraws support. Territory may flip. Assets compromised.",
        "response_portfolios": ["diplomacy", "intel"],
        "escalation_path": ["diplomatic_attempt","economic_pressure","military_threat","war"],
    },
    "economic_collapse": {
        "triggers": ["resources depleted", "trade route severed", "hyperinflation"],
        "immediate": "Production stalls. Crew morale drops. Colony growth stops.",
        "response_portfolios": ["economy", "defense"],
        "escalation_path": ["austerity_measures","trade_negotiation","emergency_funding","martial_law"],
    },
    "colony_rebellion": {
        "triggers": ["high taxes", "low cabinet_control", "famine", "hostile propaganda"],
        "immediate": "Protests. Production halts. Governor asks for military support.",
        "response_portfolios": ["defense", "education"],
        "escalation_path": ["dialogue","concessions","police_action","military_suppression"],
    },
    "cabinet_leak": {
        "triggers": ["low cohesion", "disloyal minister", "shadow_presence too high"],
        "immediate": "Shadow cabinet existence rumored. Public governor under scrutiny.",
        "response_portfolios": ["intel", "education"],
        "escalation_path": ["information_control","scapegoat","limited_disclosure","purge"],
    },
    "invasion": {
        "triggers": ["hostile fleet detected", "territory contested", "war declaration"],
        "immediate": "Fleet mobilized. Colonies on alert. Economy shifts to war footing.",
        "response_portfolios": ["defense", "intel", "economy"],
        "escalation_path": ["defensive_stand","counter_attack","total_war"],
    },
}

MEETING_TYPES = {
    "regular":     {"duration": "1 scene", "frequency": "per session", "formality": "standard"},
    "emergency":   {"duration": "1-2 scenes", "frequency": "on crisis", "formality": "urgent"},
    "war_council": {"duration": "extended", "frequency": "pre-campaign", "formality": "military"},
    "briefing":    {"duration": "short", "frequency": "per intel cycle", "formality": "informal"},
    "ceremony":    {"duration": "1 scene", "frequency": "appointment", "formality": "formal"},
}

CROSS_ENGINE_HITS = {
    "military":   {"engine": "tactics",     "method": "deployFleet"},
    "intel":      {"engine": "mystery",     "method": "openCase"},
    "diplomatic": {"engine": "social",      "method": "triggerEvent"},
    "economic":   {"engine": "economy",     "method": "adjustProduction"},
    "covert":     {"engine": "mystery",     "method": "secretCase"},
    "social":     {"engine": "social",      "method": "moraleEvent"},
    "education":  {"engine": "social",      "method": "trainingEvent"},
    "emergency":  {"engine": "tactics",     "method": "mobilizeFleet"},
}

MEETING_AGENDAS = {
    "regular": ["Territory status report","Faction standing review","Active project updates","Resource allocation","Any new business"],
    "emergency": ["Crisis assessment","Immediate response options","Resource emergency allocation","Fleet mobilization assessment"],
    "war_council": ["Enemy fleet assessment","Campaign objectives","Force composition","Rules of engagement","Contingency plans"],
    "briefing": ["Intelligence summary","Perimeter status","Anomaly reports","Agent field reports"],
    "ceremony": ["Opening formalities","Oath of office","Portfolio assignment","Celebration"],
}

#: `MEETING_AGENDAS` is the agenda table `convene_meeting` reads. `DEFAULT_AGENDAS` held a
#: byte-identical copy of it, so two edits could drift. One source, both names kept.
DEFAULT_AGENDAS = MEETING_AGENDAS

DECREE_TO_PORTFOLIO = {
    "military": "defense", "diplomatic": "diplomacy", "economic": "economy",
    "covert": "intel", "social": "education", "education": "education",
    "emergency": "defense", "directive": "intel",
}

PHASE_DESCRIPTIONS = {
    "assassination": {
        "target_identification": "Identify target routines, security, vulnerabilities.",
        "asset_placement": "Position asset within striking distance. Cover identity established.",
        "window_assessment": "Find the operational window when security is weakest.",
        "execution": "Execute the operation. No witnesses. No evidence.",
        "cleanup": "Remove assets, destroy records, establish alibi.",
    },
    "coup": {
        "loyalty_assessment": "Survey target leadership for disloyal elements.",
        "key_personnel_turned": "Turn key personnel to cabinet's side.",
        "positioning": "Position loyalists in power positions.",
        "trigger_event": "Manufacture the crisis that demands new leadership.",
        "power_transfer": "Install cabinet-aligned leader. Public justification prepared.",
    },
    "sabotage": {
        "target_recon": "Survey target for structural weaknesses.",
        "access_route": "Establish infiltration route.",
        "device_placement": "Place device. No traces.",
        "detonation": "Trigger. Ensure maximum effect with minimum attribution.",
        "blame_routing": "Plant evidence pointing elsewhere. Divert investigation.",
    },
    "false_flag": {
        "target_selection": "Select target that creates desired casus belli.",
        "disguised_assets": "Deploy assets disguised as another faction.",
        "incident_staging": "Stage the incident. Make it convincing.",
        "evidence_planting": "Leave a trail pointing to the patsy.",
        "casus_belli": "Present the incident to the galaxy. Demand response.",
    },
}

INFLUENCE_FACTORS = {
    "territory_control": 0.35, "fleet_presence": 0.25,
    "factions_standing": 0.20, "economic_output": 0.15, "shadow_operations": 0.05,
}

TERRITORY_WEIGHTS = {
    "controlled": {"base": 100, "income": 1.0},
    "contested":  {"base": 30,  "income": 0.3},
    "besieged":   {"base": 10,  "income": 0.1},
    "lost":       {"base": 0,   "income": 0.0},
    "abandoned":  {"base": 0,   "income": 0.0},
}

FACTION_STANDINGS = {"allied": 100, "friendly": 65, "neutral": 30, "hostile": 5, "enemy": 0}
STANDING_SCORES = {"allied": 4, "friendly": 3, "neutral": 2, "hostile": 1, "enemy": 0}
SCORE_TO_STANDING = {4: "allied", 3: "friendly", 2: "neutral", 1: "hostile", 0: "enemy"}

WIFE_MODES = {
    "LAID_BACK": "laid_back", "ADVISING": "advising",
    "EXECUTING": "executing", "EMERGENCY": "emergency",
}

TIER_LABELS = {0: "Grand Consul", 1: "Commander", 2: "Minister", 3: "Lead", 4: "Agent", 5: "Asset"}

TIER_BLOCKED_ACTIONS = {
    0: [], 1: ["war","treaty","dissolve_cabinet","appoint_minister","override_decree"],
    2: ["war","treaty","dissolve_cabinet","fleet_wide_mobilization"],
    3: ["campaign","decree","budget","treaty"],
    4: ["deploy","authorize","budget"], 5: ["command","deploy","authorize"],
}

PORTFOLIO_ACTIONS = {
    "sovereign": ["war","treaty","alliance","decree","appoint","dissolve","override"],
    "intel":     ["scout","recon","spy","asset_network","covert","witness","anomaly"],
    "defense":   ["deploy","patrol","defend","campaign","convoy","formation"],
    "education": ["train","teach","curriculum","welfare","mentor"],
    "economy":   ["trade","budget","mint","duties","tax","allocate"],
    "lore":      ["research","archive","seed_contact","ancient","translate"],
    "guardian":  ["defend","guard","mech","heavy_combat","protect"],
    "recon":     ["scout","survey","patrol","stealth","sensor"],
}

PORTFOLIO_KEYWORDS = {
    "defense":   ["fight","combat","attack","defend","deploy","patrol","campaign","convoy","military","strike","ambush","battle","war"],
    "intel":     ["scout","recon","spy","infiltrate","investigate","watch","monitor","scan","survey","trace","intel","anomaly","witness"],
    "economy":   ["trade","build","buy","sell","budget","tax","produce","mine","forge","craft","resource","allocate","credit"],
    "education": ["teach","train","school","learn","study","mentor","curriculum","welfare","care"],
    "lore":      ["research","ancient","history","archive","record","translate","decipher","seeder"],
    "guardian":  ["guard","protect","defend","heavy","mech","wall","shield"],
    "recon":     ["scout","survey","patrol","stealth","ghost","sensor"],
}

EMERGENCY_CHAIN = ["Commander", "Military Minister", "Intel Lead"]

THWART_METHODS = {
    "arrest_asset":    {"success": 0.6, "exposure": 0.3, "moral": 0, "desc": "Arrest known conspirator assets"},
    "feed_misinfo":    {"success": 0.7, "exposure": 0.1, "moral": 0, "desc": "Feed false information to mislead plotters"},
    "turn_agent":      {"success": 0.4, "exposure": 0.5, "moral": 1, "desc": "Turn a conspirator into a double agent"},
    "expose_publicly": {"success": 0.9, "exposure": 0.8, "moral": 2, "desc": "Expose the plot publicly"},
}


# ═══════════════════════════════════════════════════════════════
# SESSION RESOLUTION
# ═══════════════════════════════════════════════════════════════

def _sid(session_id: int | None) -> int:
    """Resolve the session for one call.

    `Config.SESSION_ID` is fixed at import, so a long-lived tick kept writing to the session that was
    current at start. An explicit id (0 included) is used as given.

    @param session_id - caller's id, or None for the active arc.
    @returns the session id.
    @raises RuntimeError when nothing resolves.
    """
    return session_id if session_id is not None else require_session(None)


def _writable_sid(session_id: int | None) -> int:
    """Resolve the session and refuse a frozen one.

    Sessions 3 and 5 are reference data. Every council writer (decrees, thwarts, agents, title
    revocation, the tick) wrote into them with no check, the door `core.ooc` keeps shut for its own
    writers.

    @param session_id - caller's id, or None for the active arc.
    @returns the session id.
    @raises core.ooc.FrozenSession when the session is frozen and maintenance is not armed.
    """
    sid = _sid(session_id)
    ooc._refuse_frozen(sid)
    return sid


# ═══════════════════════════════════════════════════════════════
# CABINET MANAGER
# ═══════════════════════════════════════════════════════════════

async def get_cabinet_seats(session_id: int | None = None) -> list[dict]:
    session_id = _sid(session_id)
    rows = await Database.fetch(
        "SELECT * FROM maya_rp.cabinet_hierarchy WHERE session_id = $1 AND active = true ORDER BY tier, id",
        session_id,
    )
    return [dict(r) for r in rows]


def promote_seat(seat: dict, new_holder: str, options: dict | None = None) -> dict:
    """Promote a seat holder. Ported from CabinetManager.promote()."""
    opts = options or {}
    update = {"holder": new_holder}
    if "tier" in opts: update["tier"] = opts["tier"]
    if "portfolio" in opts: update["portfolio"] = opts["portfolio"]
    if "is_wife" in opts: update["is_wife"] = opts["is_wife"]
    if "max_fleet_power" in opts: update["max_fleet_power"] = opts["max_fleet_power"]
    return {**seat, **update}


def calculate_vote(seats: list[dict], votes: list[dict], decree_type: str = "standard") -> dict:
    """Calculate vote result. Ported from CabinetManager.calculateVote()."""
    active = [s for s in seats if s.get("active") and s.get("tier", 99) <= 3]
    if not active:
        return {"passed": False, "tally": {"aye": 0, "nay": 0, "abstain": 0}, "percentage": 0, "reason": "No active seats"}

    tally = {"aye": 0, "nay": 0, "abstain": 0}
    for v in votes:
        p = v.get("position", "abstain")
        if p == "aye": tally["aye"] += 1
        elif p == "nay": tally["nay"] += 1
        else: tally["abstain"] += 1

    total_voting = tally["aye"] + tally["nay"]
    pct = tally["aye"] / total_voting if total_voting > 0 else 0
    threshold = VOTE_THRESHOLDS.get(decree_type, 0.5)

    return {
        "passed": total_voting > 0 and pct >= threshold,
        "tally": tally, "percentage": pct, "threshold": threshold,
        "active_voters": len(active),
        "reason": f"Vote {'passed' if pct >= threshold else 'failed'}. Needed {threshold*100:.0f}%, got {pct*100:.0f}%",
    }


def validate_cabinet(seats: list[dict]) -> dict:
    """Validate cabinet composition. Ported from CabinetManager.validateCabinet()."""
    required = ["Grand Consul", "Commander", "Military Minister", "Intel Lead"]
    active_titles = [s["title"] for s in seats if s.get("active")]
    missing = [r for r in required if r not in active_titles]
    warnings = []
    optional = ["Finance Minister", "Education Minister", "Archivist", "Warden", "Diplomacy Minister"]
    mo = [o for o in optional if o not in active_titles]
    if mo: warnings.append(f"Unfilled seats: {', '.join(mo)}")
    if len([s for s in seats if s.get("tier") == 0 and s.get("active")]) != 1:
        warnings.append("Must have exactly one Grand Consul")
    return {"valid": len(missing) == 0, "missing": missing, "warnings": warnings,
            "active_count": len([s for s in seats if s.get("active")]), "total_seats": len(seats)}


def get_cohesion(seats: list[dict]) -> int:
    """Get cabinet cohesion score 0-100. Ported from CabinetManager.getCohesion()."""
    if not seats: return 0
    weighted_sum = 0
    weight_total = 0
    for s in seats:
        if not s.get("active"): continue
        tw = max(1, 6 - s.get("tier", 5))
        loy = s.get("loyalty", 50)
        weighted_sum += loy * tw
        weight_total += tw
    return round(weighted_sum / weight_total) if weight_total > 0 else 0


def status_report(seats: list[dict]) -> str:
    """Generate cabinet status report. Ported from CabinetManager.statusReport()."""
    lines = ["CABINET STATUS"]
    tier_icons = {0: "\u265a", 1: "\u265b", 2: "\u265c", 3: "\u265d", 4: "\u265e", 5: "\u265f"}
    for s in sorted([s for s in seats if s.get("active")], key=lambda x: x["tier"]):
        mode = f" [{s.get('wife_mode','').upper()}]" if s.get("is_wife") else ""
        icon = tier_icons.get(s["tier"], "\u00b7")
        lines.append(f"{icon} {s['title']}: {s['holder']} ({s['portfolio']}){mode}")
    coh = get_cohesion(seats)
    lines.append(f"Cohesion: {coh}% | Active: {len([s for s in seats if s.get('active')])}")
    return "\n".join(lines)


def consul_override(consul_seat: dict | None) -> dict:
    """Check if Consul can override. Ported from CabinetManager.consulOverride()."""
    if not consul_seat or consul_seat.get("tier") != 0:
        return {"can_override": False, "reason": "Only Grand Consul can override"}
    return {"can_override": True, "reason": "Consular override \u2014 no limits"}


# ═══════════════════════════════════════════════════════════════
# CONSPIRACY ENGINE
# ═══════════════════════════════════════════════════════════════

def generate_plot(plot_type: str, target: dict | None = None, cabinet: list | None = None) -> dict:
    """Generate a covert plot. Ported from ConspiracyEngine.generatePlot()."""
    if target is None: target = {}
    if cabinet is None: cabinet = []
    template = PLOT_TEMPLATES.get(plot_type)
    if not template:
        return {"error": f"Unknown plot type: {plot_type}"}

    avail = [s["portfolio"] for s in cabinet if s.get("active")]
    missing = [p for p in template["required_portfolios"] if p not in avail]

    cover = COVER_STORIES.get(plot_type, ["Routine cabinet operation"])
    cover_story = random.choice(cover)

    def phase_desc(ptype, phase, tgt):
        descs = PHASE_DESCRIPTIONS.get(ptype, {})
        if phase in descs:
            return descs[phase].replace("target", tgt.get("name", "target"))
        return f"{phase.replace('_', ' ')} \u2014 execute covertly."

    return {
        "plot_type": plot_type, "target": target,
        "difficulty": template["difficulty"],
        "phases": [{"name": p, "order": i+1, "complete": False,
                     "description": phase_desc(plot_type, p, target)}
                   for i, p in enumerate(template["phases"])],
        "required_portfolios": template["required_portfolios"],
        "missing_portfolios": missing, "cover_story": cover_story,
        "exposure_risk": template["exposure_risk"],
        "moral_cost": template["moral_cost"],
        "executable": len(missing) == 0, "current_phase": 0,
    }


def execute_phase(plot: dict, phase_index: int, asset: dict | None = None) -> dict:
    """Execute a plot phase. Ported from ConspiracyEngine.executePhase()."""
    if asset is None: asset = {}
    if phase_index >= len(plot.get("phases", [])):
        return {"success": True, "complete": True, "narrative": "All phases complete."}

    phase = plot["phases"][phase_index]
    skill = asset.get("skill", 50)
    diff_mod = (10 - plot["difficulty"]) * 10
    roll = random.randint(0, 99) + skill + diff_mod

    if roll > 120:
        outcome = {"success": True, "critical": True, "narrative": "Phase executed flawlessly."}
    elif roll > 90:
        outcome = {"success": True, "critical": False, "narrative": "Phase completed. Cover holds."}
    elif roll > 60:
        outcome = {"success": True, "critical": False, "narrative": "Phase completed with minor complications."}
        plot["exposure_risk"] += 5
    elif roll > 40:
        outcome = {"success": False, "critical": False, "narrative": "Phase stalled. Asset needs extraction."}
    else:
        outcome = {"success": False, "critical": True, "narrative": "Phase failed. Cover compromised."}
        plot["exposure_risk"] += 15

    if outcome["success"]:
        plot["current_phase"] = phase_index + 1
        plot["phases"][phase_index]["complete"] = True

    return {**outcome, "roll": roll, "phase": phase["name"], "phase_index": phase_index, "exposure_risk": plot["exposure_risk"]}


def check_exposure(plot: dict) -> dict:
    """Check if plot is exposed. Ported from ConspiracyEngine.checkExposure()."""
    roll = random.randint(0, 99)
    if roll < plot["exposure_risk"]:
        if roll < plot["exposure_risk"] / 3:
            return {"exposed": True, "severity": "full", "narrative": "Plot fully exposed. Cover blown."}
        elif roll < plot["exposure_risk"] * 0.66:
            return {"exposed": True, "severity": "partial", "narrative": "Evidence surfaces. Investigators circling."}
        else:
            return {"exposed": True, "severity": "rumor", "narrative": "Whispers reach wrong ears. Suspicion grows."}
    return {"exposed": False, "severity": "none", "narrative": "Cover holds."}


def generate_mystery_hooks(territories: list[dict] | None = None) -> list[dict]:
    """Generate intel hooks from territory. Ported from ConspiracyEngine.generateMysteryHooks()."""
    if territories is None: territories = []
    hooks = []
    for t in territories:
        if t.get("cabinet_control", 100) < 30:
            hooks.append({
                "system": t["system_name"], "type": "resource",
                "hook": f"Unusual resource shipments from {t['system_name']} suggest a hidden backer.",
                "clues": 3, "difficulty": 5,
            })
        if t.get("contested_by"):
            hooks.append({
                "system": t["system_name"], "type": "conspiracy",
                "hook": f"{t['contested_by']} agents spotted in {t['system_name']}.",
                "clues": 4, "difficulty": 6,
            })
    return hooks


# ═══════════════════════════════════════════════════════════════
# COUNTER-ESPIONAGE
# ═══════════════════════════════════════════════════════════════

async def scan_for_plots(session_id: int | None = None, network_quality: int = 0) -> list[dict]:
    """Scan for active conspiracies. Ported from CounterEspionage.scanForPlots()."""
    session_id = _sid(session_id)
    rows = await Database.fetch(
        "SELECT id, plot_type, target, current_phase, difficulty, details "
        "FROM maya_rp.conspiracies WHERE session_id = $1 AND status = 'active'",
        session_id,
    )
    detected = []
    for row in rows:
        p = dict(row)
        # A network of quality 0 caught a plot 10% of the time and quality 1 caught it 0.3%, so
        # staffing the first agent made the cabinet blinder. The 10% floor now holds at every quality
        # and the network adds its share of the remaining 90%, scaled down by plot difficulty.
        quality = max(0, min(100, network_quality))
        detect = 0.1 + 0.9 * (quality / 100) * (1 - min(10, p["difficulty"]) / 10)
        # `random.random()` decided this, so scanning the same state twice gave two different answers
        # and the novel could not reproduce a scan. A digest of the conspiracy keeps the uncertainty
        # while making the same state always report the same way. The network quality stays out of the
        # digest: a better network must catch every plot a worse one caught, and a roll that moved
        # with quality let a stronger network miss a plot a weaker one found.
        roll = (int.from_bytes(hashlib.blake2s(
            f"{session_id}|{p['id']}|{p['current_phase']}".encode(),
            digest_size=4).digest(), "big") % 10_000) / 10_000
        if roll < detect:
            detected.append({
                "conspiracy_id": p["id"], "plot_type": p["plot_type"],
                "target": p["target"], "phase": p["current_phase"],
                "difficulty": p["difficulty"],
                "description": f"Detected {p['plot_type']} plot" + (f" targeting {p['target']}" if p.get("target") else ""),
            })
    return detected


async def assign_agent(session_id: int | None, crew_id: int, role: str) -> dict:
    """Assign counter-intel agent. Ported from CounterEspionage.assignAgent().

    @param session_id - session owning the network; None resolves the active arc.
    @param crew_id - assigned crew member.
    @param role - watcher, networker or interrogator.
    @returns {"assigned": True, ...} or {"error": ...}.
    @raises core.ooc.FrozenSession when the session is frozen.
    """
    session_id = _writable_sid(session_id)
    valid = ["watcher", "networker", "interrogator"]
    if role not in valid:
        return {"error": f"Invalid role '{role}'", "available": valid}
    try:
        quality_boost = {"networker": 5, "watcher": 3, "interrogator": 2}.get(role, 0)
        # intel_network is a per-session singleton (created on first assignment —
        # the module used to UPDATE a `game_id` column on a table that did not
        # exist, so every assignment failed).
        await Database.execute(
            "INSERT INTO maya_rp.intel_network (session_id, agents_assigned, quality, last_scan) "
            "VALUES ($1, $2::jsonb, LEAST(100, $3), NOW()) "
            "ON CONFLICT (session_id) DO UPDATE SET "
            "agents_assigned = COALESCE(maya_rp.intel_network.agents_assigned, '[]'::jsonb) || EXCLUDED.agents_assigned, "
            "quality = LEAST(100, COALESCE(maya_rp.intel_network.quality, 0) + $3), "
            "last_scan = NOW()",
            session_id, json.dumps([{"crew_id": crew_id, "role": role}]), quality_boost,
        )
        return {"assigned": True, "role": role, "quality_boost": quality_boost}
    except Exception as e:
        return {"error": str(e)}


async def thwart_plot(conspiracy_id: int, method: str, session_id: int | None = None) -> dict:
    """Thwart a detected plot. Ported from CounterEspionage.thwartPlot().

    The update ran by id alone, so any campaign could attempt to thwart another campaign's plot, and
    a conspiracy id that does not exist was answered with a success roll against nothing.

    Only an `active` plot can be thwarted. The update set `status = 'active'` on a failed roll with no
    status guard, so a failed second attempt re-activated a plot the first attempt had thwarted. A
    failed roll now writes nothing, and the success write is guarded on `status = 'active'`.

    @param conspiracy_id - plot to thwart.
    @param method - key of THWART_METHODS.
    @param session_id - session owning the plot; None resolves the active arc.
    @returns the roll result, or {"success": False, "error": ...} for an unknown, foreign or resolved plot.
    @raises core.ooc.FrozenSession when the session is frozen.
    """
    session_id = _writable_sid(session_id)
    m = THWART_METHODS.get(method)
    if not m:
        return {"error": f"Invalid method '{method}'", "available": sorted(THWART_METHODS)}
    try:
        row = await Database.fetchrow(
            "SELECT id, status FROM maya_rp.conspiracies WHERE id = $1 AND session_id = $2",
            conspiracy_id, session_id,
        )
        if not row:
            return {"success": False,
                    "error": f"conspiracy {conspiracy_id} not found in session {session_id}"}
        if row["status"] != "active":
            return {"success": False,
                    "error": f"conspiracy {conspiracy_id} is {row['status']}, not active"}
        success = random.random() < m["success"]
        if success:
            claimed = await Database.fetchval(
                "UPDATE maya_rp.conspiracies SET status = 'thwarted', "
                "details = jsonb_set(coalesce(details, '{}'), '{thwarted_by}', $1::jsonb) "
                "WHERE id = $2 AND session_id = $3 AND status = 'active' RETURNING id",
                json.dumps({"method": method}), conspiracy_id, session_id,
            )
            if claimed is None:
                return {"success": False,
                        "error": f"conspiracy {conspiracy_id} was resolved by another call"}
        return {
            "success": success, "exposure_risk": m["exposure"], "moral_cost": m["moral"],
            "narrative": f"Plot {'successfully disrupted' if success else f'failed. {method} ineffective.'}",
        }
    except Exception as e:
        error("council", f"thwart_plot failed on conspiracy {conspiracy_id}: {e}")
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# GOVERNANCE EVENTS
# ═══════════════════════════════════════════════════════════════

def convene_meeting(meeting_type: str = "regular", context: dict | None = None) -> dict:
    """Generate cabinet meeting. Ported from GovernanceEvents.conveneMeeting().

    An unknown meeting type used to be answered with a regular meeting, so a typo convened the wrong
    agenda and the caller had no way to tell.
    """
    if context is None: context = {}
    if meeting_type not in MEETING_TYPES:
        return {"error": f"Unknown meeting type: {meeting_type}",
                "available": sorted(MEETING_TYPES)}
    t = MEETING_TYPES[meeting_type]
    return {
        "type": meeting_type, "duration": t["duration"], "formality": t["formality"],
        "convened_by": context.get("convened_by", "Grand Consul"),
        "attendees": context.get("attendees", []),
        "agenda": context.get("agenda", MEETING_AGENDAS.get(meeting_type, ["Status reports"])),
    }


async def issue_decree(
    session_id: int | None, decree_type: str, details: dict | None = None, cabinet: list | None = None,
) -> dict:
    """Issue a decree to a minister. Ported from GovernanceEvents.issueDecree().

    The Grand Consul issues the decree, so the minister's `laid_back` mode and portfolio action list
    do not gate it. `can_do(minister, decree_type)` ran without the `consumer_decree` context and
    substring-matched the decree type against `PORTFOLIO_ACTIONS`, so every `laid_back` minister (the
    column default) refused every decree, and the types `military`, `economic`, `social`, `education`,
    `emergency` and `directive` matched no action word. Routing is exact instead: the decree type picks
    the portfolio through `DECREE_TO_PORTFOLIO`, or `details["target_portfolio"]` overrides it. Fleet
    power limits still apply through `can_do`.

    @param session_id - session issuing the decree; None resolves the active arc.
    @param decree_type - key of DECREE_TO_PORTFOLIO (the `cabinet_decrees.decree_type` CHECK values).
    @param details - optional title, description, priority, secrecy, target_portfolio, fleet_power.
    @param cabinet - seats; read from the session when None.
    @returns {"issued": True, ...} or {"issued": False, "reason": ...}.
    @raises core.ooc.FrozenSession when the session is frozen.
    """
    session_id = _writable_sid(session_id)
    if details is None: details = {}
    if cabinet is None:
        cabinet = await get_cabinet_seats(session_id)

    consul = next((s for s in cabinet if s["tier"] == 0 and s.get("active")), None)
    if not consul:
        return {"issued": False, "reason": "No active Grand Consul."}

    if decree_type not in DECREE_TO_PORTFOLIO:
        return {"issued": False,
                "reason": f"Unknown decree type '{decree_type}'.",
                "available": sorted(DECREE_TO_PORTFOLIO)}

    target = details.get("target_portfolio", DECREE_TO_PORTFOLIO[decree_type])
    minister = next((s for s in cabinet if s["portfolio"] == target and s.get("active")), None)
    if not minister:
        return {"issued": False, "reason": f"No active minister for '{target}'."}

    route_check = can_do(minister, decree_type, {
        "consumer_decree": True, "decree_type": decree_type,
        "fleet_power": details.get("fleet_power", 0)})
    if not route_check.get("allowed"):
        return {"issued": False, "reason": route_check.get("reason"), "suggestion": route_check.get("suggestion")}

    cross = CROSS_ENGINE_HITS.get(decree_type)

    await Database.execute(
        "INSERT INTO maya_rp.cabinet_decrees (session_id, issued_by, delegated_to, decree_type, title, description, status, priority, secrecy_level, cross_engine_hits) "
        "VALUES ($1, $2, $3, $4, $5, $6, 'pending', $7, $8, $9::jsonb)",
        session_id, consul["holder"], minister["id"], decree_type,
        details.get("title", f"{decree_type} Decree"),
        details.get("description", ""),
        details.get("priority", "standard"), details.get("secrecy", "shadow"),
        json.dumps([cross]) if cross else "[]",
    )

    info("council", f"Decree: {decree_type} from {consul['holder']} to {minister['holder']}")
    return {"issued": True, "decree_type": decree_type, "from": consul["holder"], "to": minister["holder"]}


def trigger_crisis(crisis_type: str) -> dict:
    """Trigger governance crisis. Ported from GovernanceEvents.triggerCrisis()."""
    t = CRISIS_TEMPLATES.get(crisis_type)
    if not t: return {"error": f"Unknown crisis: {crisis_type}"}
    return {
        "crisis": crisis_type, "triggers": t["triggers"],
        "immediate": t["immediate"],
        "response_portfolios": t["response_portfolios"],
        "escalation_path": t["escalation_path"],
        "current_stage": 0, "active": True,
        "narrative": f"CRISIS: {crisis_type.replace('_', ' ')}. {t['immediate']}",
    }


def escalate_crisis(crisis: dict, advance_by: int = 1) -> dict:
    """Advance crisis escalation. Ported from GovernanceEvents.escalateCrisis()."""
    path = crisis.get("escalation_path", [])
    crisis["current_stage"] = min(len(path) - 1, crisis.get("current_stage", 0) + advance_by)
    crisis["active"] = crisis["current_stage"] < len(path) - 1
    stage = path[crisis["current_stage"]] if path else "unknown"
    return {**crisis, "narrative": f"Crisis escalated to: {stage.replace('_', ' ')}"}


def situation_briefing(decrees: list | None = None, projects: list | None = None, crises: list | None = None) -> str:
    """Generate situation briefing. Ported from GovernanceEvents.situationBriefing()."""
    lines = ["CABINET BRIEFING"]
    if crises:
        lines.append("\nACTIVE CRISES:")
        for c in crises:
            path = c.get("escalation_path", [])
            lines.append(f"  {c.get('crisis','?')} \u2014 Stage {c.get('current_stage',0)+1}/{len(path)}")
    executing = [d for d in (decrees or []) if d.get("status") == "executing"]
    if executing:
        lines.append("\nEXECUTING:")
        for d in executing:
            lines.append(f"  {d.get('title','?')} ({d.get('delegated_to','?')})")
    active_projs = [p for p in (projects or []) if p.get("status") == "active"]
    if active_projs:
        lines.append("\nPROJECTS:")
        for p in active_projs:
            bar = "\u2588" * round(p.get("progress_pct", 0) / 10)
            lines.append(f"  {p.get('name','?')} [{bar}] {p.get('progress_pct',0)}%")
    pending = [d for d in (decrees or []) if d.get("status") == "pending"]
    if pending:
        lines.append("\nPENDING:")
        for d in pending:
            lines.append(f"  {d.get('title','?')} \u2014 awaiting activation")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# INFLUENCE TRACKER
# ═══════════════════════════════════════════════════════════════

def calculate_influence(faction: dict, territories: list | None = None, ships: list | None = None) -> int:
    """Calculate faction influence 0-100. Ported from InfluenceTracker.calculateInfluence()."""
    if territories is None: territories = []
    if ships is None: ships = []
    score = 0

    controlled = [t for t in territories if t.get("controlling_faction") == faction.get("name") and t.get("status") == "controlled"]
    score += len(controlled) * INFLUENCE_FACTORS["territory_control"] * 100

    fp = len([s for s in ships if s.get("faction") == faction.get("name")])
    score += min(fp * 5, 25) * INFLUENCE_FACTORS["fleet_presence"]

    sw = FACTION_STANDINGS.get(faction.get("standing", "neutral"), 30)
    score += sw * INFLUENCE_FACTORS["factions_standing"]

    score += min(faction.get("shadow_presence", 0), 20) * INFLUENCE_FACTORS["shadow_operations"]

    return max(0, min(100, round(score)))


def calculate_territory_control(territory: dict, cabinet_members: list | None = None) -> int:
    """Calculate cabinet control over territory. Ported from InfluenceTracker.calculateTerritoryControl()."""
    if cabinet_members is None: cabinet_members = []
    control = 0
    if territory.get("status") == "controlled":
        control += 50 if territory.get("controlling_faction") == "Federation" else 30
    elif territory.get("status") == "contested":
        control += 15
    if territory.get("governor_name"): control += 15
    fp = territory.get("fleet_presence", 0)
    if fp > 0: control += min(20, fp * 2)
    control += min(15, len(cabinet_members) * 3)
    return max(0, min(100, control))


def effective_standing(faction: dict) -> dict:
    """Calculate effective standing with shadow boost. Ported from InfluenceTracker.effectiveStanding()."""
    pub = faction.get("standing", "neutral")
    shadow = (faction.get("shadow_presence", 0)) / 20
    pub_score = STANDING_SCORES.get(pub, 2)
    eff = min(4, round(pub_score + shadow))
    return {"public_standing": pub, "shadow_boost": shadow,
            "effective_score": eff, "effective_standing": SCORE_TO_STANDING.get(eff, "neutral")}


def influence_contest(cabinet_influence: int, faction_influence: int, action: str = "policy") -> dict:
    """Roll for influence contest. Ported from InfluenceTracker.influenceContest()."""
    cab_roll = random.randint(0, 99) + cabinet_influence
    fac_roll = random.randint(0, 99) + faction_influence
    margin = cab_roll - fac_roll

    if margin > 40: narrative = f"Cabinet dominates. {action} executed unopposed."
    elif margin > 10: narrative = f"Cabinet wins with leverage. {action} pushed through."
    elif margin > -10: narrative = f"Close contest. Negotiation needed for {action}."
    elif margin > -40: narrative = f"Faction resists. {action} blocked."
    else: narrative = f"Humiliating loss. Cabinet stands drop."

    return {"success": margin > 0, "margin": margin, "cabinet_roll": cab_roll, "faction_roll": fac_roll, "narrative": narrative}


def shadow_exposure_risk(shadow_presence: int, cabinet_control: int) -> dict:
    """Calculate shadow exposure risk. Ported from InfluenceTracker.shadowExposureRisk()."""
    base = shadow_presence * 0.5
    cover = max(0, (100 - cabinet_control) / 100)
    chance = min(95, round(base * cover))
    if chance < 10: level = "minimal"
    elif chance < 25: level = "low"
    elif chance < 50: level = "moderate"
    elif chance < 75: level = "high"
    else: level = "critical"
    return {"risk_level": level, "exposure_chance": chance}


# ═══════════════════════════════════════════════════════════════
# ROLE MANAGER
# ═══════════════════════════════════════════════════════════════

def can_do(seat: dict, action: str, context: dict | None = None) -> dict:
    """Check if seat can perform action. Ported from RoleManager.canDo().

    `context["decree_type"]` marks `action` as a decree type rather than an action verb. The caller
    (`issue_decree`) has already routed the decree to the seat's portfolio by exact lookup, so the tier
    and portfolio word lists, which substring-match verbs like "war" and "scout", are skipped. Without
    it `"war" in "award"` blocked a Tier-2 award decree and `"military"` matched no portfolio verb.

    @param seat - cabinet seat row.
    @param action - action verb, or a decree type when `context["decree_type"]` is set.
    @param context - optional: consumer_decree, decree_type, scouting_below_tier, fleet_power.
    @returns {"allowed": bool, "reason": str, "suggestion": ...}.
    """
    if context is None: context = {}
    if not seat or not seat.get("active"):
        return {"allowed": False, "reason": "Seat inactive or not found", "suggestion": None}

    if seat.get("wife_mode") == WIFE_MODES["LAID_BACK"] and not context.get("consumer_decree"):
        return {"allowed": False, "reason": f"{seat['holder']} is laid back. Awaiting Consul direction.",
                "suggestion": "Issue decree from Grand Consul first"}

    if seat["tier"] == 0:
        if context.get("scouting_below_tier"):
            return {"allowed": False, "reason": "Consul commands battle group. Scouts scout.",
                    "suggestion": "delegate_to", "delegateTo": "Intel Lead"}
        return {"allowed": True, "reason": "Sovereign authority. No limits.", "suggestion": None}

    routed_decree = context.get("decree_type") is not None
    blocked = [] if routed_decree else TIER_BLOCKED_ACTIONS.get(seat["tier"], [])
    if any(a in action.lower() for a in blocked):
        return {"allowed": False, "reason": f"Action exceeds Tier {seat['tier']} ({TIER_LABELS.get(seat['tier'],'?')})",
                "suggestion": f"Route to tier {seat['tier']-1}+ seat"}

    portfolio_actions = PORTFOLIO_ACTIONS.get(seat.get("portfolio", ""), [])
    if portfolio_actions and not routed_decree and not any(a in action.lower() for a in portfolio_actions):
        return {"allowed": False, "reason": f"'{action}' not in {seat['holder']}'s portfolio ({seat.get('portfolio','?')})",
                "suggestion": _find_portfolio_match(action)}

    if seat.get("max_fleet_power", 0) > 0 and context.get("fleet_power", 0) > seat["max_fleet_power"]:
        return {"allowed": False, "reason": f"Fleet power exceeds {seat['holder']}'s max of {seat['max_fleet_power']}",
                "suggestion": "Request Consul override"}

    return {"allowed": True, "reason": "Within limits", "suggestion": None}


def get_wife_status(seat: dict, active_decrees: int = 0, unreachable_hours: int = 0) -> str:
    """Get wife operational mode. Ported from RoleManager.getWifeStatus()."""
    if not seat.get("is_wife"):
        return WIFE_MODES["EXECUTING"]
    if unreachable_hours >= 24: return WIFE_MODES["EMERGENCY"]
    if active_decrees > 0: return WIFE_MODES["EXECUTING"]
    if seat.get("wife_mode") == WIFE_MODES["ADVISING"]: return WIFE_MODES["ADVISING"]
    return WIFE_MODES["LAID_BACK"]


def route_task(cabinet: list[dict], task: str) -> dict:
    """Route task to correct seat. Ported from RoleManager.routeTask()."""
    lower = task.lower()
    best_portfolio, best_score = None, 0
    for portfolio, keywords in PORTFOLIO_KEYWORDS.items():
        score = sum(1 for k in keywords if k in lower)
        if score > best_score:
            best_score = score
            best_portfolio = portfolio

    if not best_portfolio:
        return {"routed": False, "seat": None, "reason": "No portfolio match found."}

    match = next((s for s in cabinet if s.get("portfolio") == best_portfolio and s.get("active")), None)
    if not match:
        return {"routed": False, "seat": None, "reason": f"No active seat for '{best_portfolio}'"}

    return {"routed": True, "seat": match.get("id"), "reason": f"Routed to {match['holder']} ({match['title']})"}


def get_emergency_authority(cabinet: list[dict], hours: int = 0) -> dict | None:
    """Get emergency chain successor. Ported from RoleManager.getEmergencyAuthority()."""
    if hours < 24: return None
    for title in EMERGENCY_CHAIN:
        seat = next((s for s in cabinet if s["title"] == title and s.get("active")), None)
        if seat:
            return {"seat": seat, "authority": "Limited. Tier -1. War/treaty blocked.", "tier": min(seat["tier"], 1)}
    return None


def _find_portfolio_match(action: str) -> str | None:
    lower = action.lower()
    for portfolio, actions in PORTFOLIO_ACTIONS.items():
        if any(a in lower for a in actions):
            return portfolio
    return None


# ═══════════════════════════════════════════════════════════════
# OBSERVER SUSPICION (§6.1) — narrative colour, one-way read
# ═══════════════════════════════════════════════════════════════

SUSPICION_NOTICES = {
    "watchful": "A minister has started keeping a private record of the Commander's decisions.",
    "probing": "The council chamber has gone quiet in the way that means questions are being asked.",
    "certain": "Whispers in the cabinet: the Commander is no longer trusted to speak plainly.",
}


def suspicion_notice(reading: dict) -> str | None:
    """Narrative colour when an observer's suspicion reaches a band (§6.1).

    @param reading - `core.ooc.suspicion_reading` result.
    @returns a councillor-notices line, or None when nobody is suspicious yet.
    """
    return SUSPICION_NOTICES.get(reading.get("band"))


# ═══════════════════════════════════════════════════════════════
# TICK
# ═══════════════════════════════════════════════════════════════

async def run_tick(session_id: int | None = None) -> dict[str, Any]:
    """Council module tick: validate cabinet, check cohesion, log summary.

    @param session_id - session to tick; None resolves the active arc.
    @raises core.ooc.FrozenSession when the session is frozen.
    """
    session_id = _writable_sid(session_id)
    try:
        seats = await get_cabinet_seats(session_id)
        valid = validate_cabinet(seats)
        cohesion = get_cohesion(seats)
        # §6.1 — read-only: the OOC meter colours the tick, never written here.
        reading = await ooc.suspicion_reading(session_id)
        notice = suspicion_notice(reading)
        info("council", f"Tick: {len(seats)} seats, cohesion={cohesion}%, valid={valid['valid']}"
                        + (f" · {notice}" if notice else ""))
        return {"seats": len(seats), "cohesion": cohesion, "valid": valid["valid"],
                "missing": valid["missing"], "observer_suspicion": reading, "notice": notice}
    except Exception as e:
        # A catch-all answered with a dict and an INFO line, so a malfunctioning tick read like a
        # quiet one. The answer stays the same shape; the fault is now logged as a fault.
        error("council", f"tick failed for session {session_id}: {e}")
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════
# NOVEL ADAPTATION — IMPERIAL TITLE PRESSURE (novel bab 7, 51)
# "Ruthless but fair": governor kena deliver, atau title ditarik.
# ═══════════════════════════════════════════════════════════════

async def check_title_revocation(session_id: int | None = None) -> dict:
    """Scan territories untuk revocation risk.
    Risk naik bila: crisis_level > 5, takde governor, development rendah.
    Risk turun bila: performance bagus (dev naik, crisis sifar).

    @param session_id - session to scan; None resolves the active arc.
    @raises core.ooc.FrozenSession when the session is frozen.
    """
    session_id = _writable_sid(session_id)
    territories = await Database.fetch(
        "SELECT id, system_name, crisis_level, development_level, governor_name, "
        "revocation_risk, title_performance FROM maya_rp.territory WHERE session_id=$1",
        session_id,
    )
    flagged = []
    for t in territories:
        risk = t["revocation_risk"] or 0
        perf = t["title_performance"] or 0
        crisis = t["crisis_level"] or 0

        # Faktor naik risiko
        if crisis > 5:
            risk += 3
        if not t["governor_name"]:
            risk += 2
        if (t["development_level"] or 0) <= 0:
            risk += 1

        # Faktor turun (performance)
        if crisis == 0 and t["governor_name"]:
            perf += 1
        if (t["development_level"] or 0) >= 3:
            perf += 1
        risk = max(0, risk - (perf // 3))

        if risk != (t["revocation_risk"] or 0) or perf != (t["title_performance"] or 0):
            # The gate watched `risk` alone while the update wrote `title_performance` too, so a tick
            # that only earned performance points wrote nothing and the points were lost. A territory
            # with a governor and no crisis could never accumulate past the first two.
            await Database.execute(
                "UPDATE maya_rp.territory SET revocation_risk=$1, title_performance=$2 WHERE id=$3",
                risk, perf, t["id"],
            )
        if risk >= 10:
            flagged.append({"system": t["system_name"], "risk": risk, "crisis": crisis})

    return {"checked": len(territories), "flagged": flagged,
            "revocation_ready": [f for f in flagged if f["risk"] >= 15]}


async def revoke_title(session_id: int | None, system_name: str, reason: str = "") -> dict:
    """Cabut title governor — Imperial authority. Kos reputasi moral (ruthless but fair).

    The governor removal and its event commit together, and the removal is claimed with
    `governor_name IS NOT NULL`, so two concurrent calls log one revocation, not two.

    @param session_id - session owning the territory; None resolves the active arc.
    @param system_name - exact territory name.
    @param reason - optional reason for the event text.
    @returns {"revoked", "governor", "reason"} or {"error": ...}.
    @raises core.ooc.FrozenSession when the session is frozen.
    """
    session_id = _writable_sid(session_id)
    async with Database.transaction() as conn:
        t = await conn.fetchrow(
            "SELECT id, system_name, governor_name FROM maya_rp.territory "
            "WHERE session_id=$1 AND system_name=$2 FOR UPDATE",
            session_id, system_name,
        )
        if not t or not t["governor_name"]:
            return {"error": "Territory tak wujud atau takde governor"}
        gov = t["governor_name"]
        await conn.execute(
            "UPDATE maya_rp.territory SET governor_name=NULL, revocation_risk=0, title_performance=0 WHERE id=$1",
            t["id"],
        )
        await conn.execute(
            "INSERT INTO maya_rp.events (session_id, event_type, title, description, importance) "
            "VALUES ($1, 'decree', $2, $3, 4)",
            session_id, f"TITLE REVOKED: {system_name}",
            f"Governor {gov} dibuang dari {system_name}. {'Alasan: ' + reason if reason else 'Gagal deliver performance.'} "
            f"Imperial authority ditegakkan — ruthless but fair.",
        )
    return {"revoked": system_name, "governor": gov, "reason": reason or "underperformance"}
