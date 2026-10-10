"""Which table belongs to which campaign: the class registry for `maya_rp`.

Every base table sits in exactly one class. A table either carries `session_id`, or it reaches a
session through an FK chain (`DERIVED`), or it is immutable reference data (`CATALOGUE`), or it is
engine bookkeeping (`SYSTEM`), or it is campaign state that has no binding yet (`PENDING_BINDING`).

The classes come from `survey-novel.md` section 2, read 2026-10-10. The counts there: 175 bound,
55 derived, 48 catalogue, 4 system, 26 unbound. Migration 138 binds eight of the 26, so
`PENDING_BINDING` holds 18 and `AWAITING_SESSION_ID` holds the other eight.

Two rules hold this file together:

- `PENDING_BINDING` is a debt list. It must only shrink: a table leaves it when a migration gives it
  a binding, never by editing the set to hide the gap.
- A new table that lands in no class fails `tests/test_novel_binding.py`. Classifying the table is
  the decision the test forces, and this file is where the decision is written down.

The sets are `frozenset`, so a reader cannot mutate the registry by accident. `SHARED_ENTITIES` is
the one exception: it names rows, not tables, and grows by owner decision.

`novel_id` lives on `sessions` alone. A table records its session, and the session records its
novel, so a row that copies the novel can never drift from the session it belongs to.
"""

from __future__ import annotations

#: Tables with no `session_id` whose rows reach a session through a parent table. Each entry has an
#: FK to another table in this set or to a session-bound table. `sessions` itself is not derived: it
#: is the root, and its one FK (`primary_partner_id`) does not scope it.
DERIVED: frozenset[str] = frozenset({
    "active_events", "ai_decisions", "ai_tactics_history", "artifact_history",
    "battle_aftermath", "battle_log_entries", "battle_phases",
    "character_quirks", "character_species", "character_traits", "colonization_projects",
    "combat_rounds", "combat_stats", "corporate_assets", "counter_intel_ops", "crew_factions",
    "diplomatic_actions", "economic_crises", "envoys", "espionage_operations",
    "fleet_members", "image_generations", "infrastructure_production", "intel_reports",
    "leader_events", "leaders", "military_expenditure",
    "pirate_activities", "pirate_bases", "pirate_bounties", "pirate_extortion", "pirate_raids",
    "political_factions", "port_upgrades", "price_history", "prisoner_intel_pipeline",
    "raid_log", "reputation_events", "score_history", "sector_resources",
    "ship_armaments", "ship_modules", "slave_births", "slave_training", "spy_networks",
    "supply_depots", "supply_lines", "tax_history", "terraforming_projects",
    "territory_modifiers", "territory_resources", "trade_log", "treaties",
    "victory_tracking", "yard_capacity",
})

#: Immutable reference rows: hull classes, weapon kinds, world types, recipe and event catalogues.
#: A catalogue is the same text in every campaign, so binding it would copy one row per session and
#: leave the copies free to disagree. No table here has an FK into a session-bound or derived table.
CATALOGUE: frozenset[str] = frozenset({
    "alchemy_recipes", "battle_terrain", "bug_tech_tree", "bug_war_assets", "build_templates",
    "containment_measures", "difficulty_tiers", "disaster_templates", "event_templates",
    "fleet_formations", "infrastructure_types", "infestation_stages", "location_catalog",
    "materials", "megastructure_types", "mystery_templates", "modules", "novels",
    "pirate_artifacts",
    "pirate_fleet_templates", "pirate_loot_tables", "pirate_salvage_templates",
    "pirate_ship_classes", "planet_features", "planet_types_catalog", "player_action_catalog",
    "policy_registry", "port_types", "production_requirements", "recipes", "roll_outcome_tiers",
    "roll_types", "romance_tiers", "ship_classes", "ship_roles", "ship_sub_classes",
    "ship_types", "social_templates", "space_animals", "space_anomalies", "species_catalog",
    "stealth_unit_types", "strategic_resources", "tactics_catalog", "talent_catalog",
    "tension_thresholds", "training_programs", "trait_catalog", "weapon_kinds",
})

#: Engine bookkeeping. `sessions` is the root every other class resolves through, and the three
#: migration tables record which files ran. None of them belongs to a campaign.
SYSTEM: frozenset[str] = frozenset({
    "_migrations", "migration_hashes", "migration_versions", "sessions",
})

#: Campaign state with no binding yet. Phase 2 of the novel work: `research_projects`,
#: `resource_inventory`, `stock_prices` and `global_settings` need a per-session table or a split,
#: the eight empty tables have engine writers and no rows, and the weapons family is an owner call.
#:
#: `enrolled_crew` is here with them. It is empty, `crew_id` has no FK to `crew_roster`, and
#: `138_bind_state.sql` does not name it, so it waits rather than taking a guessed default.
PENDING_BINDING: frozenset[str] = frozenset({
    "character_arcs", "character_presence_log", "damage_resistances", "enrolled_crew",
    "global_modifiers", "global_settings", "guardrail_log", "production_consumption_log",
    "research_projects", "resource_inventory", "scientist_assignments", "ship_tech_bonuses",
    "stock_prices", "stream_templates", "war_exhaustion_effects", "weapon_blueprints",
    "weapon_upgrades", "weapons",
})

#: The tables `migrations/138_bind_state.sql` binds. The name is a record, not a class: the test
#: subtracts every table that already carries `session_id`, so a table leaves this set the moment the
#: apply lands and the set stays accurate before and after it. Keep the names after the apply: the
#: gated tests read them to know which columns to expect.
AWAITING_SESSION_ID: frozenset[str] = frozenset({
    "academy_campuses", "pirate_zones", "pool_bets", "production_lines",
    "research_labs", "resource_production", "trait_assignments", "university_campuses",
})

#: Rows one campaign shares with another, keyed by table. Faction id 3, Iron Concord, is canon in
#: both novels: session 5 owns the faction row, and 2,743 session-3 ships name it. Copying the row
#: would split one faction into two, so it stays where it is and the cross-session reference is
#: allowed. Every other cross-session FK is a defect that a later card repairs, not a shared entity.
SHARED_ENTITIES: dict[str, set[int]] = {"factions": {3}}
