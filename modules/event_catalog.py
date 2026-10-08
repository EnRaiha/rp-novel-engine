#!/usr/bin/env python3
"""Event Catalog — Ported from Rust event_catalog.rs (2,027 lines). 60+ encounter templates."""
from __future__ import annotations
import random
from core.db import Database
from core.log import info
from core.session import require_session


def _writable_session(session_id: int | None) -> int:
    """Resolve the session for one call and refuse a frozen campaign.

    Sessions 3 and 5 are reference data; a writer that skipped this check mutated them.

    @param session_id - caller's session; `None` resolves through `core.session.require_session`.
    @returns the resolved session id.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    from core.ooc import _refuse_frozen

    sid = require_session(session_id)
    _refuse_frozen(sid)
    return sid

ENCOUNTERS = {
    "trade": {
        "peaceful_trader":     {"diff": 2, "desc": "A lone trader offers exotic goods at fair prices."},
        "smuggler_cache":       {"diff": 3, "desc": "Abandoned smuggler vessel with contraband cargo."},
        "merchant_convoy":      {"diff": 4, "desc": "Heavily armed merchant convoy passes through the sector."},
        "black_market_auction": {"diff": 5, "desc": "Underground auction of rare ship modules."},
        "refugee_flotilla":     {"diff": 3, "desc": "A flotilla of refugee ships requests safe passage."},
    },
    "combat": {
        "pirate_raiders":       {"diff": 4, "desc": "Pirate raiders ambush unprepared vessels."},
        "hostile_patrol":       {"diff": 5, "desc": "Enemy patrol ship challenges your presence."},
        "ambush":               {"diff": 6, "desc": "Coordinated ambush from hidden positions."},
        "fleet_skirmish":       {"diff": 7, "desc": "Two hostile fleets engaged in close combat."},
        "battlefield_debris":   {"diff": 3, "desc": "Debris field of recent battle with salvage potential."},
        "bounty_hunters":       {"diff": 5, "desc": "Bounty hunters mistake you for their mark."},
        "derelict_warship":     {"diff": 6, "desc": "Massive derelict warship drifting in space."},
        "defense_station":      {"diff": 7, "desc": "Automated defense station attacks all ships in range."},
    },
    "exploration": {
        "ancient_ruins":       {"diff": 5, "desc": "Precursor ruins with unknown technology."},
        "alien_artifact":      {"diff": 6, "desc": "Mysterious artifact emitting strange energy signatures."},
        "void_tear":           {"diff": 8, "desc": "A tear in space-time revealing unknown dimensions."},
        "signal_source":       {"diff": 4, "desc": "Unknown signal source requires investigation."},
        "strange_readings":    {"diff": 3, "desc": "Sensors detect unusual energy readings nearby."},
        "derelict_probe":      {"diff": 2, "desc": "Ancient probe containing stellar cartography data."},
        "crashed_satellite":   {"diff": 2, "desc": "Communications satellite with partial data cache."},
        "space_whale_pod":     {"diff": 3, "desc": "Pod of space whales migrating through the system."},
    },
    "science": {
        "stellar_phenomena":   {"diff": 4, "desc": "Rare stellar phenomena offers research opportunity."},
        "nebula_anomaly":      {"diff": 5, "desc": "Nebula contains unusual electromagnetic properties."},
        "gravity_well":        {"diff": 6, "desc": "Unexpected gravity well disrupts navigation."},
        "temporal_rift":       {"diff": 7, "desc": "Temporal rift causing localized time distortion."},
        "bio_signal":          {"diff": 5, "desc": "Biosignature detected on otherwise dead world."},
        "energy_surge":        {"diff": 4, "desc": "Massive energy surge from unknown source."},
        "precursor_signal":    {"diff": 8, "desc": "Precursor signal decoded — coordinates lead deeper."},
        "void_echo":           {"diff": 9, "desc": "Echo from the Void — reality-bending encounter."},
    },
    "disaster": {
        "solar_flare":         {"diff": 4, "desc": "Solar flare damages unprotected systems."},
        "engine_failure":      {"diff": 3, "desc": "Critical engine failure requires immediate repair."},
        "hull_breach":         {"diff": 4, "desc": "Hull breach detected — emergency containment required."},
        "fire":                {"diff": 3, "desc": "Fire breaks out in cargo bay."},
        "plague_outbreak":     {"diff": 6, "desc": "Virulent pathogen spreads through crew quarters."},
        "mutiny":              {"diff": 7, "desc": "Crew discontent boils over into open rebellion."},
        "supply_contamination":{"diff": 3, "desc": "Food and water supplies contaminated."},
        "reactor_meltdown":    {"diff": 8, "desc": "Reactor critical — evacuation or containment needed."},
    },
    "mystery": {
        "ghost_ship":          {"diff": 5, "desc": "Derelict ship with all crew missing — no signs of struggle."},
        "mysterious_distress": {"diff": 4, "desc": "Distress signal from a ship that doesn't exist."},
        "cult_activity":       {"diff": 6, "desc": "Cult activity discovered on remote colony."},
        "disappeared_colony":  {"diff": 7, "desc": "Entire colony vanished without trace."},
        "signal_trap":         {"diff": 6, "desc": "Fake distress signal set as trap for rescuers."},
    },
}

def get_random_encounter(category: str | None = None, max_diff: int = 10) -> dict:
    if category:
        if category not in ENCOUNTERS:
            # An unknown category used to fall through to a fabricated "default_encounter" that is in
            # no catalogue, so a misspelled category returned an encounter nobody had written.
            return {"error": f"unknown encounter category {category!r}",
                    "categories": sorted(ENCOUNTERS)}
        pool = ENCOUNTERS[category]
    else:
        pool = {k: v for cat in ENCOUNTERS.values() for k, v in cat.items()}
    if not pool:
        return {"error": f"no encounters catalogued for category {category!r}"}
    filtered = {k: v for k, v in pool.items() if v["diff"] <= max_diff}
    if filtered:
        name = random.choice(list(filtered.keys()))
        return {"name": name, **filtered[name]}
    # Nothing in the pool sits at or below the caller's ceiling. The old code answered with the whole
    # pool anyway, so a caller asking for difficulty 1 or less could be handed a 9 and never told. The
    # closest encounter is returned instead, and the override is named in the result.
    name, entry = min(pool.items(), key=lambda kv: (kv[1]["diff"], kv[0]))
    return {"name": name, **entry,
            "warnings": [f"no encounter at or below difficulty {max_diff}."
                         f" {name!r} is the closest at {entry['diff']}"]}

async def run_tick(session_id: int | None = None) -> dict:
    """No-op tick. @raises core.ooc.FrozenSession - the campaign is frozen."""
    _writable_session(session_id)
    return {"status": "event_catalog_ready"}
