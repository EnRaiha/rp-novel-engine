# RP Engine, full reference

Written 2026-10-10. Every claim here is readable off the code in this tree. Line numbers match the
tree at commit `6938a4e8`. Paths are repository-relative.

## 1. What this is

The RP Engine is the simulation behind a long-form roleplay campaign: an async Python engine
(3.11 or newer) that owns campaign state in PostgreSQL schema `maya_rp`, advances that state one
tick at a time through 31 ordered phases, and serves the result to a GM-facing CLI, a JSON bridge
and a map server. It is not the novel. The novel is prose written outside the engine, in the vault,
and the engine never generates it: it computes days, resources, fleets, relationships and events,
and it records what the prose declares. It is not the GM persona either. The GM (the System, the
overlord voice) lives in the harness prompt and in `core/persona.py`; the engine only audits prose
against the persona rules in `core/ooc.py` and keeps the deviation score those rules feed.

## 2. Layout

| Path | What belongs there |
|---|---|
| `core/` | Engine core, 42 modules and 10,298 lines. Session resolution, config, the pool, OOC, savegame, pacing, guard, campaign helpers. Two of these modules are ticked (`core/pacing.py`, `core/consequences.py`). |
| `modules/` | The 93 tick modules and pure libraries, 23,341 lines, plus `README.md` with the module contract. 80 export `async def run_tick(session_id)`. |
| `scripts/` | 84 modules and one data file (`eval_pairs.json`). Entry points (`cli.py`, `map_server.py`, `kilo_bridge.py`, `ooc_bridge.py`), the tick (`orchestrator.py`), the migration runner (`migrate.py`), seeding and one-shot repairs. |
| `migrations/` | 115 `.sql` files, numbered, plus two Python seeds (`seed_character_profiles.py`, `seed_galaxy_beauties.py`). DDL and data migrations. |
| `tests/` | 280 `test_*.py` files plus `conftest.py` and `__init__.py`, 57,421 lines. Runs against a live `maya_rp`. |
| `docs/` | Reports that outlive a session. This file is one of them. |
| `data/` | `roster.yaml`, the curated character reference for `char:query`. The database stays the truth. |
| `models/` | Four pickled decision trees (`event_importance_tree.pkl`, three pirate trees) loaded by `core/decision_models.py` and `modules/faction_ai.py`. |
| `systemd/` | `turn-watcher.service`, the unit that runs `scripts/turn_watcher.py --watch`. |
| `dist/` | Local source bundles built for upload to a notebook tool. Gitignored. |
| `logs/` | Tick logs written by `core/log.py`. Gitignored. |
| `graphify-out/` | Knowledge-graph artifacts for this directory. Tracked. |
| `.dsh/`, `.claude/` | Agent working state: loop briefs, prep notes, survey files. Gitignored except `.dsh/.gitignore`. |
| `.pytest_cache/`, `.ruff_cache/`, `.benchmarks/` | Tool caches. |
| Root files | `PLAN.md`, `pyproject.toml`, two QA reports, `tmp-l2.txt` (untracked scratch). |

## 3. Data model

Schema `maya_rp` holds 309 base tables and 13 views, 322 relations in total
(`information_schema.tables`), read 2026-10-10.

### 3.1 The session is the root

`sessions` is the root of the model. Its columns:

| Column | Type | Note |
|---|---|---|
| `id` | integer, PK, serial | The campaign id every other row names. |
| `name` | text, NOT NULL | |
| `status` | text, NOT NULL, default `active` | `core/guard.py` also treats `dead` and `executed` on characters, not here. |
| `summary` | text | |
| `created_at` | timestamptz | |
| `telegram_chat_id` | bigint | |
| `primary_partner_id` | integer, FK `characters(id)` | The one FK on `sessions`, and it does not scope the row. |
| `seed`, `seed_version` | bigint, integer | |
| `save_label` | varchar(100) | |
| `game_day` | integer | The tick counter the `.sav` header and `tick_summaries` read. |
| `king_present` | boolean | Read by `modules/ministry_ai.py`. |
| `dark_mode` | boolean | |
| `story_path` | text | |
| `novel_id` | text, NOT NULL, default `scratch`, FK `novels(novel_id)` | Set by migration 137. |

### 3.2 Novels

`novels` is a catalogue of four rows in the live database: two campaigns that hold rows, the
prequel one arc revamps, and `scratch`, the default an unbound session takes.

| Column | Type | Note |
|---|---|---|
| `novel_id` | text, PK | The slug. |
| `title` | text, NOT NULL | What `cli.py continue` resolves a title against. |
| `universe` | text, NOT NULL, default `TKG` | |
| `adventures_dir` | text | Directory holding the novel's text. Held as a relative path (`adventures/...`). |
| `status` | text, NOT NULL, default `active` | `active` while a session plays it, `superseded` when a later novel replaces it. |
| `supersedes` | text, FK `novels(novel_id)` | A revamp points at the novel it revamps. |
| `story_order` | integer | Reading order. A revamp shares its original's order. |
| `created_at` | timestamptz | |

### 3.3 The binding rule

`novel_id` lives on `sessions` alone. A table records its session, and the session records its
novel, so no row copies the novel and no copy can drift from the session that owns it.
`core/session.py:230` `novel_of(session_id)` is the single reader: it resolves the session through
`require_session`, reads `sessions.novel_id`, and raises `ValueError` when the row is absent or the
column is NULL.

### 3.4 How a table is classified

`core/binding.py` is the class registry. Every base table sits in exactly one of these classes.

| Class | Size | Meaning |
|---|---|---|
| carries `session_id` | 183 base tables | The row names its campaign directly. |
| `DERIVED` | 55 | No `session_id`. The row reaches a session through an FK to a bound or derived table. |
| `CATALOGUE` | 49 | Immutable reference rows, identical in every campaign: hull classes, weapon kinds, recipes, event templates. No FK points into a session-bound or derived table. |
| `SYSTEM` | 4 | `sessions`, `_migrations`, `migration_hashes`, `migration_versions`. Engine bookkeeping. |
| `PENDING_BINDING` | 18 | Campaign state with no binding yet. A debt list that must only shrink. |
| `AWAITING_SESSION_ID` | 8 | The tables migration 138 binds. A name that leaves this set the moment the table carries `session_id`. |
| `SHARED_ENTITIES` | 1 entry | Rows one campaign shares with another, keyed by table and row id. |

The registry is enforced, not documented. `tests/test_novel_binding.py:144`
`test_every_base_table_is_in_exactly_one_class` fails when a base table lands in no class, and again
when a table sits in two. Classifying a new table is the decision the test forces. Three more tests
hold the shape: a derived table must reach a session through a parent (`:182`), a catalogue table
must not be reachable from any session (`:192`), and `PENDING_BINDING` must not grow (`:207`).

The `SHARED_ENTITIES` exception exists because one faction row is canon in two novels: the row stays
where it is and the cross-session reference is allowed. Every other cross-session FK is a defect.

A table that needs its own rows in each campaign gets a `session_id`. A catalogue that reads the
same in every campaign keeps none.

## 4. Session resolution

`core/session.py` is the single resolver. `resolve_session(explicit)` answers in this order:

1. The explicit argument, when it is set and not zero.
2. `RP_SESSION` from the environment.
3. The active arc file, `ACTIVE_ARC` = `$RP_MAINT_DIR/active_arc`, default
   `~/.config/rp-engine/active_arc`.
4. Maintenance armed: return `None`. Cross-session edits are permitted and nothing is guessed.
5. Otherwise raise `RuntimeError` naming all three sources. The engine never guesses a session;
   guessing is what merged two arcs.

`unset()` treats absent, blank, and numeric zero as no value. The zero test is numeric, so `"00"`,
`"0.0"` and `False` all count as set.

`require_session(explicit)` wraps the resolver and refuses maintenance's `None` with a
`RuntimeError`. Readers that need one session fail loudly there instead of falling back to a stale
default.

`Config.SESSION_ID` resolves once, at import, through the same resolver; when the resolver fails the
process falls back to the legacy campaign and sets `SESSION_FALLBACK_USED`. `stale_process_default()`
compares that process default against a fresh resolve and returns a warning line when they differ; the
tick and the bridge both call it (`scripts/orchestrator.py:43`, `scripts/kilo_bridge.py:22`).

### 4.1 Frozen sessions

`frozen_sessions`, beside `active_arc`, lists reference-only campaigns, one id per line. A frozen
campaign stays readable and every writer refuses it with `core.ooc.FrozenSession` (a
`PermissionError`). `frozen()` reads the list; a missing file means nobody is frozen. Any other read
failure raises `FrozenListUnreadable`, and `is_frozen()` turns that into a refusal, so the guard fails
closed. Maintenance armed answers `False`: the operator repairs the list.

`core/ooc.py:150` `_refuse_frozen(sid)` is the check every writer calls. Modules document it as
`@raises core.ooc.FrozenSession`.

### 4.2 Operator control

`scripts/gm_maint.py` is the operator CLI. Verbs:

| Verb | Effect |
|---|---|
| `arm [--ttl S] [--force]` | Arm GM MAYA maintenance. Refuses while a play flag is live. |
| `disarm` | Stand down. |
| `status` | Print mode, arc, the arc's novel, the frozen list, maintenance state. |
| `mode` | Print `GM MAYA maintenance` or `play`. |
| `session [--session N]` | Resolve one session through `resolve_session`; print the refusal on failure. |
| `arc [N]` | Show or set the active arc, then name its novel. |
| `freeze [N ...]` | Show or replace the frozen list. |
| `play on [--pid N]` / `play off` | Raise or lower the play flag. `arm` refuses while it is live. |

The state lives in `$RP_MAINT_DIR`, default `~/.config/rp-engine/`: `active_arc`, `frozen_sessions`,
`maintenance.json`, `play.lock`. Both writers (`set_active_arc`, `set_frozen`, `maintenance._write`)
replace the file atomically through a uniquely named temp file in the same directory.

`scripts/orchestrator.py:108` `guard_session()` runs the brakes in order for every tick and every
single-module run: maintenance armed stops the run, then the session resolves per call, then a frozen
session stops the run.

## 5. The tick

`scripts/orchestrator.py` runs the whole cycle. `run_full_tick()` resolves the session through
`guard_session`, takes an asyncio lock, opens the pool, snapshots `pg_stat_user_tables`, then calls
each phase in the order below. Every phase is a header line and a list of module calls; each module
call goes through `tick(name, mod, session_id)`, which calls `mod.run_tick(session_id)`, catches
every exception, and returns `True` for a module that ran or was skipped by its config flag, `False`
for one that crashed or returned an error dict.

A phase writes only what its modules write. Outside the phases the orchestrator does three things:
the events housekeeping (one `UPDATE maya_rp.roll_history` and one move from `events` into
`events_archive`), one `tick_summaries` row, and the auto-export `.sav` file. Nothing else in the
tick issues SQL.

The session every phase runs on is the one `guard_session` returned. Each module re-resolves it with
`require_session(session_id)`; an explicit id wins over `RP_SESSION` and the active arc, so the tick
cannot drift mid-run.

| Phase | Modules, in call order | What it advances, and principal writes |
|---|---|---|
| 1/31 Economy | `economy`, `market`, `crew_system` | Tax and population, commodity prices, crew production. `resources`, `events`, `price_history`, `commodities`, `crew_production_log`, `crew_roster`. |
| 2/31 Prison & Security | `prison` | Prisoner state, interrogation, escape counters. `prisoners`, `interrogation_log`, `escape_countermeasures`, `clues`, `crew_roster`, `resources`. |
| 3/31 Social & Morale | `social` | Crew relationships, loyalty, morale history. `character_relationships`, `morale_history`, `social_events`, `crew_roster`. |
| 4/31 Romance & Bonds | `romance`, `pregnancy`, `voyage`, `population_sentiment`, `ministry_ai` | Bonds and intimacy, trimesters and births, booked transit days, public sentiment, ministry proposals. `romance_arcs`, `intimacy_events`, `jealousy_states`, `pregnancies`, `voyages`, `population_sentiment`, `adjutant_prompts`, `governor_applicants`. |
| 5/31 Council & Governance | `council` | Cabinet, decrees, conspiracies, counter-espionage. `cabinet_decrees`, `conspiracies`, `intel_network`, `territory`, `events`. |
| 6/31 Research | `research` | Queue progress, unlocks, resource inventory. `research_queue`, `research_projects`, `resource_inventory`, `global_modifiers`, `ship_tech_bonuses`. |
| 7/31 Diplomacy & AI | `diplomacy` | Treaties, envoys, faction AI actions. `treaties`, `envoys`, `factions`. |
| 8/31 Narrative & Encounters | `narrative`, `events` (`modules/encounters.py`) | Story hooks, ambient events, consequence seeds. `narrative_hooks`, `story_log`, `events`, `consequence_seeds`. |
| 9/31 Galaxy & Investigations | `celestial`, `mystery` | Systems, lanes, fog of war, case progress. `territory`, `investigations`, `clues`, `investigation_log`. |
| 10/31 Combat Readiness | `tactics`, `fleet_economy` | Formations read, burn and caravan events. `events`. |
| 11/31 Pirates & Intel | `pirates`, `espionage`, `darkops`, `stealth` | Raids, bounties, spy networks, deniable operations, cloaking. `pirate_raids`, `pirate_bases`, `pirate_bounties`, `pirate_alerts`, `espionage_missions`, `dark_ops`, `stealth_units`, `anti_cloak_grids`, `resources`. |
| 12/31 Military Operations | `defense`, `siege`, `disasters`, `battle` | Installations, sieges, disasters, battle resolution. `defense_installations`, `sieges`, `active_disasters`, `combat_results`, `battle_phases`, `battle_log_entries`, `character_injuries`, `ships`, `wars`. |
| 13/31 Population | `slave_system` | Acquisition, assignment, training, revolts, births. `slaves`, `slave_market`, `slave_revolts`, `slave_training`, `slave_births`, `crew_roster`. |
| 14/31 Science & Technology | `tech_tree`, `manufacturing`, `auto_queue`, `exoscience`, `academy`, `university` | Labs, production lines, standing orders, missions, training, graduation. `research_labs`, `technologies`, `production_lines`, `material_stockpiles`, `production_queue`, `science_missions`, `academy_campuses`, `university_campuses`, `enrolled_crew`, `certifications`. |
| 15/31 Magic & Discovery | `alchemy`, `archaeology`, `artifacts` | Recipes, dig sites, relic histories. `material_stockpiles`, `dig_sites`, `artifacts`, `artifact_history`. |
| 16/31 Faction Behavior | `faction_ai`, `event_catalog` | Faction decisions from the trained trees, and a catalogue read. `factions`. |
| 17/31 Narrative & Media | `narrator`, `news`, `quest`, `epilogue`, `image_gen`, `adventures` | Prose prompts, articles, quests, epilogue framing, image prompts. `news_articles`, `quests`, `image_prompts`, `population_sentiment`. |
| 18/31 Integration & Safety | `guardrails` | Content checks. Writes nothing. |
| 19/31 Character Events | `characters` | Presence, arcs, character events. `characters`, `character_arcs`, `events`. |
| 20/31 Victory | `victory` | Victory progress. `victory_tracking`. |
| 21/31 Space Wonders | `space_wonders` | Planets, animals, anomalies, discoveries. `planets`, `animal_encounters`, `discoveries`, `story_log`. |
| 22/31 Megastructures & Infrastructure | `megastructures_ports`, `infrastructure` | Construction, ports, mining, refineries, factories. `megastructure_construction`, `ports`, `port_upgrades`, `infrastructure_instances`, `infrastructure_production`, `story_log`. |
| 23/31 Space Horror | `space_horror` | Infestation spread, containment, eradication. `infestation_instances`, `eradication_campaigns`, `crisis_events`. |
| 24/31 Calendar & Consequences | `calendar` (`modules/calendar_tkg.py`), `consequences` (`core/consequences.py`), `narrative_seeds` | The game calendar, delayed cascades from earlier ticks, planted seeds. `sessions`, `events`, `consequence_seeds`, `narrative_seeds`. |
| 25/31 War & Memories | `war`, `memories` | Strategic wars and character memory rows. `wars`, `factions`, `character_memories`, `events`. |
| 26/31 Locations & Scenes | `locations` | Where characters stand, who is present. `characters`, `character_presence_log`, `player_context`. |
| 27/31 Geopolitics & Logistics | `geopolitics`, `logistics`, `crew_career`, `corporations` | Off-screen faction conflict, cargo in space, crew XP and retirement, corporate income. `wars`, `incoming_raids`, `cargo`, `transport_missions`, `crew_roster`, `crew_skills`, `crew_xp_log`, `corporations`, `corporate_contracts`. |
| 28/31 Living Universe | `pacing`, `objectives`, `npc_autonomy`, `secrets`, `world_react`, `physical_state`, `chekhov`, `themes`, `environment` | Scene mode, objectives, off-screen NPC life, secrets, world reactions, injuries, unpaid guns, themes. `narrative_pacing`, `narrative_hooks`, `npc_internal_state`, `npc_offscreen_interactions`, `secrets`, `world_reactions`, `character_injuries`, `chekhov_elements`, `theme_state`. |
| 29/31 Endgame Watch | `collapse` | Collapse triggers and forced arcs. `story_arcs`, `events`. |
| 30/31 Ideology & Progress | `ideology` | Society stance from recorded player actions. `ideology_state`. |
| 31/31 Ship Operations | `ship_generation`, `ship_building`, `fleet`, `refit`, `weapon_design` | Stat rolling, builds, fleet membership, refits, weapon blueprints. `ships`, `ship_modules`, `ship_armaments`, `fleet_members`, `fleets`, `weapon_blueprints`, `weapon_upgrades`, `weapons`, `combat_stats`, `material_stockpiles`, `resources`, `events`. |

`pacing` is the only phase that calls a class rather than a module: `run_full_tick` passes
`PacingDirector` and `core/pacing.py:164` defines `run_tick` as a `@staticmethod`.

### 5.1 After the phases

Three steps run in this order, outside the phase numbering:

1. **Events retention.** `archive_old_events(session_id)` moves this session's `events` rows older
   than 180 days into `events_archive`, but only when the session holds more than
   `EVENTS_ARCHIVE_MIN_ROWS` (5000) rows. A `roll_history.context_event_id` that names a moved event
   is released first, inside the same transaction, because that FK is NO ACTION and not deferrable.
2. **Tick summary.** One row into `tick_summaries` with `tick_number` = the session's `game_day`,
   `categories` = `{modules_ok, modules_failed, duration_ms}` as jsonb, and `alerts_count` =
   `modules_failed`.
3. **Auto-save.** `core.savegame.export_sav(session_id)` writes a `.sav`, then a glob keeps the last
   12 files for that session by name.

The tick prints one line from `core/tick_writes.report()`: how many tables moved, how many rows, and
how many tables have never been written. The measurement is a diff of two
`pg_stat_user_tables` snapshots. When the view is unreadable, the report says so rather than
reporting zero writes, because the two look identical in a number.

### 5.2 Flags and counters

`Config.MODULES` holds 82 entries, 81 of them `True` and `agnes` `False`.
`Config.is_module_active(name)` gates every call, so `False` means SKIPPED and a skipped module is not
a failure. `MODULE_MAP` names 81 keys for `run_single`, which backs `cli.py run <module>`. Three keys
in `MODULE_MAP` are never called by the full tick (`conversation_log`, `duel`, `wreck_assembly`), and
one of those has no `run_tick` at all. Section 14 lists both.

## 6. Subsystem catalogue

One row per module under `modules/`, grouped by domain. `Reads` and `Writes` name the principal
tables, not every table a query touches. `Tick` names the phase in section 5, `map only` for a module
reachable through `MODULE_MAP` but not the full tick, `library` for a module with no `run_tick`, and
`not called` for a module with a `run_tick` that neither the tick nor `MODULE_MAP` names.

### 6.1 State, resources, economy

| Module | Owns | Reads | Writes | Tick |
|---|---|---|---|---|
| `economy.py` | Tax, trade income, gate tolls, territory revenue. | `resources`, `territory`, `factions`, `faction_relations`, `faction_trade_deals`, `ideology_state` | `resources`, `events` | phase 1 |
| `_economy.py` | Resource arithmetic in one place: `_check_afford`, `_deduct_resources`, `stochastic_round`, `InsufficientResources`. Replaces three byte-identical copies. | `resources` | `resources` through callers | library |
| `market.py` | The 13-commodity price model and the per-day price tick. | `resources`, `sessions` | `commodities`, `price_history` | phase 1 |
| `auto_queue.py` | Yard standing orders and corporate tick. | `auto_queue`, `corporate_assets`, `production_queue` | `production_queue`, `material_stockpiles`, `corporations`, `commodities` | phase 14 |
| `corporations.py` | Charters, CEOs, passive income and events. | `corporations`, `research_projects`, `sessions` | `corporations`, `corporate_contracts`, `resources`, `factions`, `events` | phase 27 |
| `manufacturing.py` | Production lines and recipes. | `recipes`, `colonies` | `production_lines`, `material_stockpiles` | phase 14 |
| `infrastructure.py` | Mining, refineries, stations, factories, farms, defense, logistics, arcane. | `infrastructure_types`, `territory`, `sectors`, `infrastructure_overview` (view) | `infrastructure_instances`, `infrastructure_production`, `story_log`, `resources` | phase 22 |
| `megastructures_ports.py` | Endgame constructions and port infrastructure. | `megastructure_types`, `port_types`, `sectors`, `megastructure_status` (view), `port_overview` (view) | `megastructure_construction`, `ports`, `port_upgrades`, `territory`, `story_log`, `resources` | phase 22 |
| `logistics.py` | Cargo in space, blockades, transport missions. | `sessions` | `cargo`, `transport_missions` | phase 27 |
| `fleet_economy.py` | Resource burn per fleet, caravans, production queue. | `resources`, `ships`, `sessions` | `events` | phase 10 |
| `population_sentiment.py` | Per-system, per-faction public opinion. Resource-driven, faction-independent. | `territory`, `news_articles` | `population_sentiment` | phase 4 |
| `ministry_ai.py` | Setia ministries. They decide alone only while the King is away; otherwise the proposal goes to the adjutant. | `factions`, `build_queue` | `adjutant_prompts`, `governor_applicants`, `territory`, `events` | phase 4 |
| `ideology.py` | Which society the fleet is, from recorded actions. | `player_action_log` | `ideology_state` | phase 30 |

### 6.2 Science, technology, discovery

| Module | Owns | Reads | Writes | Tick |
|---|---|---|---|---|
| `research.py` | Research queue progress and unlocks. | `research_queue`, `resources`, `resource_inventory`, `strategic_resources`, `ships` | `research_queue`, `research_projects`, `resource_inventory`, `global_modifiers`, `ship_tech_bonuses`, `territory` | phase 6 |
| `tech_tree.py` | Tech view, labs, scientist assignment. `research_labs` carries `session_id` from migration 138. | `characters`, `colonies` | `research_labs`, `scientist_assignments`, `technologies`, `resources` | phase 14 |
| `exoscience.py` | Science missions, anomalies, theories. | `sectors` | `science_missions`, `anomalies_catalog`, `resources` | phase 14 |
| `academy.py` | Crew training, programs, certifications. | `training_programs` | `academy_campuses`, `certifications`, `enrolled_crew`, `crew_roster` | phase 14 |
| `university.py` | Campus graduation and the science-rate multiplier. | `university_campuses`, `research_labs`, `research_projects`, `sessions` | `events`, `resources` | phase 14 |
| `alchemy.py` | Recipes and material conversion. | `alchemy_recipes` | `material_stockpiles` | phase 15 |
| `archaeology.py` | Dig sites and excavation. | `sectors` | `dig_sites`, `artifacts` | phase 15 |
| `artifacts.py` | Relic ownership and history. | `artifacts` | `artifacts`, `artifact_history`, `events` | phase 15 |
| `space_wonders.py` | Planet types, space animals, anomalies, discoveries. | `planet_types_catalog`, `planet_features`, `sectors`, `space_animals`, `space_anomalies` | `planets`, `animal_encounters`, `discoveries`, `story_log`, `resources` | phase 21 |
| `mystery.py` | Investigations, clues, case logs. | `mystery_templates` | `investigations`, `clues`, `investigation_log` | phase 9 |

### 6.3 Military, conflict, security

| Module | Owns | Reads | Writes | Tick |
|---|---|---|---|---|
| `battle.py` | Terrain, tactics, formations, phases, commanders, aftermath. | `sessions`, `characters`, `faction_ships`, `fleet_formations` | `combat_results`, `battle_phases`, `battle_log_entries`, `battle_aftermath`, `character_injuries`, `ships`, `wars`, `events` | phase 12 |
| `tactics.py` | Tactical positioning and military options. | `fleets`, `fleet_members`, `ships` | none | phase 10 |
| `defense.py` | Defense installations per colony. | `colonies` | `defense_installations`, `resources` | phase 12 |
| `siege.py` | Sieges of a territory. | `factions` | `sieges`, `territory`, `ships`, `resources`, `events` | phase 12 |
| `disasters.py` | Disaster instances from templates. | `disaster_templates` | `active_disasters`, `territory`, `ships`, `resources` | phase 12 |
| `war.py` | Strategic wars: phases, objectives, resolution. | `sessions`, `ships`, `faction_ships` | `wars`, `factions`, `events` | phase 25 |
| `pirates.py` | Pirate factions, bases, bounties, raids, salvage, artifacts. | `characters` | `pirate_bases`, `pirate_raids`, `pirate_bounties`, `pirate_alerts`, `faction_ships`, `factions`, `resources` | phase 11 |
| `espionage.py` | Spy networks, missions, counter-intel. | `factions` | `espionage_missions`, `spy_networks`, `counter_intel_ops`, `intel_reports`, `resources` | phase 11 |
| `darkops.py` | Deniable operations. | `factions` | `dark_ops`, `resources` | phase 11 |
| `stealth.py` | Stealth units and anti-cloak grids. | `stealth_unit_types` | `stealth_units`, `anti_cloak_grids`, `space_lanes`, `resources` | phase 11 |
| `prison.py` | Capture, interrogation, conversion, prisoner intimacy, prison state. Ported from five JS source files. | `ships` | `prisoners`, `interrogation_log`, `prisoner_intel_pipeline`, `escape_countermeasures`, `clues`, `crew_roster`, `resources` | phase 2 |
| `guardrails.py` | Content safety checks and moral boundaries. | nothing | nothing | phase 18 |

### 6.4 People, crew, relationships

| Module | Owns | Reads | Writes | Tick |
|---|---|---|---|---|
| `crew_system.py` | The trained crew pool: production from academy and university, consumption by ships. | `sessions`, `academy_campuses`, `university_campuses` | `crew_roster`, `crew_production_log`, `crew_consumption_log`, `crew_allocation_log`, `ships`, `resources` | phase 1 |
| `crew_career.py` | Crew XP, levels, skills, retirement. | `ships` | `crew_roster`, `crew_skills`, `crew_xp_log`, `events` | phase 27 |
| `characters.py` | Character presence and the action-intent parser. | `characters` | `characters`, `character_arcs`, `events` | phase 19 |
| `character_profile.py` | Face, body, wardrobe, inventory; auto-dressing from the pacing mode. | `characters` | `characters` | not called |
| `social.py` | Crew relationships, loyalty, morale, social events. Ported from four JS source files. | `crew_roster`, `character_relationships` | `character_relationships`, `morale_history`, `social_events`, `crew_roster` | phase 3 |
| `npc_autonomy.py` | Crew internal lives and off-screen interactions. | `characters`, `sessions` | `npc_internal_state`, `npc_offscreen_interactions`, `events` | phase 28 |
| `secrets.py` | Secrets, lies, dramatic irony: what characters hide. | `characters`, `sessions` | `secrets` | phase 28 |
| `memories.py` | Persistent character memories. | `characters`, `sessions` | `character_memories` | phase 25 |
| `physical_state.py` | Scars, injuries, changes that carry history. | `sessions` | `character_injuries` | phase 28 |
| `pregnancy.py` | Royal pregnancies: trimesters, due dates, births. | `sessions` | `pregnancies`, `events` | phase 4 |
| `romance.py` | Bonds, intimacy, jealousy, romance arcs, healing and indulgence. Ported from five JS source files. | `sessions` | `romance_arcs`, `intimacy_events`, `jealousy_states`, `characters` | phase 4 |
| `slave_system.py` | Acquisition, assignment, training, revolts, breeding, market. | `slaves`, `slave_market`, `slave_revolts`, `slave_overview` (view), `territory` | `slaves`, `slave_market`, `slave_revolts`, `slave_training`, `slave_births`, `crew_roster`, `crew_skills` | phase 13 |

### 6.5 Narrative, GM brain, media

| Module | Owns | Reads | Writes | Tick |
|---|---|---|---|---|
| `narrative.py` | Story generation, hooks, ambient events. | `factions`, `territory`, `resources` | `narrative_hooks`, `story_log`, `events` | phase 8 |
| `encounters.py` | Consequence chains, encounter scaling, event tables. Ported from four JS source files. Registered as `events`. | `sessions` | `events`, `consequence_seeds` | phase 8 |
| `narrative_seeds.py` | Foreshadowing and payoff. | `sessions` | `narrative_seeds`, `events` | phase 24 |
| `narrator.py` | Prose prompts from game events. | `events` | none | phase 17 |
| `news.py` | Articles, public opinion, propaganda. Dedup by headline and by normalized template. | `factions`, `territory`, `sessions` | `news_articles`, `population_sentiment` | phase 17 |
| `quest.py` | Quest lifecycle. | `quests` | `quests`, `resources` | phase 17 |
| `epilogue.py` | End-game narrative wrap-up. | `characters`, `events`, `factions`, `ships`, `victory_tracking` | none | phase 17 |
| `adventures.py` | Adventure arcs. | `territory` | `resources` | phase 17 |
| `event_catalog.py` | 60 or more encounter templates, ported from a 2,027-line Rust file. | nothing | nothing | phase 16 |
| `faction_ai.py` | ML faction decisioning: pirate groups classified, one policy per group. Reads the pickled trees in `models/`. | `factions` | `factions` | phase 16 |
| `calendar_tkg.py` | The game calendar: 12 months of 30 days plus 5 leftover days, holidays, seasons. | `sessions` | `sessions`, `events`, `crew_roster`, `resources` | phase 24 |
| `objectives.py` | Objectives aggregated from quests, wars, seeds, tasks. | `quests`, `wars`, `consequence_seeds`, `sessions` | `narrative_hooks`, `quarterly_tasks`, `resources` | phase 28 |
| `environment.py` | Environmental storytelling, state shown through place. | `sessions`, `crew_roster`, `narrative_pacing`, `combat_results` | none | phase 28 |
| `themes.py` | Thematic resonance across combat, romance, politics, exploration. | `events` | `theme_state` | phase 28 |
| `world_react.py` | World responses to player actions. | `sessions`, `territory` | `world_reactions` | phase 28 |
| `chekhov.py` | Chekhov's guns: introduced elements must pay off. | `sessions` | `chekhov_elements` | phase 28 |
| `locations.py` | Locations and scenes: where characters are, who is present. | `location_catalog` | `characters`, `character_presence_log`, `player_context` | phase 26 |
| `image_gen.py` | AI image prompts from game state. | `characters`, `ships`, `territory` | `image_prompts` | phase 17 |
| `conversation_log.py` | Topic dedup, so a conversation does not repeat. | `sessions` | `conversation_log` | map only, no `run_tick` |
| `meanwhile.py` | Multi-POV cuts. | `factions` | `incoming_raids` | library |
| `local_gen.py` | Prose generation through the DeepSeek client; pre-generates `stream_templates`. | none | `stream_templates` | library |
| `agnes.py` | Sapiens gateway stub. Returns `Agnes would process: ...` and a no-op tick. | nothing | nothing | not called (flag off) |

### 6.6 Ships, space, travel

| Module | Owns | Reads | Writes | Tick |
|---|---|---|---|---|
| `ship_generation.py` | Stat rolling, weapon and module assignment. | `modules`, `ship_classes`, `weapons` | none | phase 31 |
| `ship_building.py` | Build pipeline: resource check, material deduction, insertion. | `resources`, `material_stockpiles` | `ships`, `ship_modules`, `ship_armaments`, `combat_stats`, `crew_roster`, `material_stockpiles`, `resources`, `events` | phase 31 |
| `ship_modules.py` | Install and query ship modules. A void drive gates crossing between z-planes. | `ships`, `modules`, `ship_classes`, `fleets`, `fleet_members` | `ship_modules` | library |
| `fleet.py` | Fleet create, assign, list, battle. | `ships`, `fleets` | `fleets`, `fleet_members`, `ships`, `resources`, `events`, `yard_capacity` | phase 31 |
| `refit.py` | Module install, tier upgrade, config listing. | `modules`, `ship_classes` | `ships`, `ship_modules`, `resources`, `events` | phase 31 |
| `weapon_design.py` | Blueprints, production, upgrades. | `weapon_blueprints`, `weapons` | `weapon_blueprints`, `weapon_upgrades`, `weapons`, `resources` | phase 31 |
| `voyage.py` | Real travel-time accounting between systems. Two canonical rates: a grid lane at 24 hours per unit, and a slower crossing outside it. | `sectors`, `sector_connections`, `black_holes`, `white_holes`, `sessions` | `voyages`, `wormholes`, `resources`, `events` | phase 4 |
| `wreck_assembly.py` | Building a ship from wreck fragments. Numbers come from the database; a roll can fail. | `wreck_inventory`, `ships` | `ships`, `wreck_inventory`, `events` | map only |
| `duel.py` | Formal 1v1 ship duels with stakes. Win chance is the power ratio, not the plot. | `ships`, `duels` | `duels`, `ships`, `news_articles`, `resources`, `events` | map only |
| `celestial.py` | Systems, lanes, fog of war, nav planning, planet catalogue. Ported from seven JS source files. | `sectors`, `space_lanes`, `planets`, `colonies`, `factions`, `treaties` | `territory`, `location_catalog` | phase 9 |
| `space_horror.py` | Bug infestation containment, war, eradication. | `infestation_stages`, `infestation_threats`, `containment_measures`, `bug_war_assets`, `sectors`, `space_lanes`, `territory` | `infestation_instances`, `eradication_campaigns`, `crisis_events`, `story_log` | phase 23 |

### 6.7 Governance and endgame

| Module | Owns | Reads | Writes | Tick |
|---|---|---|---|---|
| `council.py` | Cabinet, conspiracies, counter-espionage, governance events, influence, roles. Ported from six JS source files. | `cabinet_hierarchy` | `cabinet_decrees`, `conspiracies`, `intel_network`, `territory`, `events` | phase 5 |
| `diplomacy.py` | Treaties, envoys, AI diplomatic actions. `treaties` and `envoys` reach their session through `factions`. | `factions` | `factions`, `treaties`, `envoys`, `diplomatic_actions` | phase 7 |
| `geopolitics.py` | Off-screen conflict and trade between factions. | `factions`, `faction_relations`, `territory`, `sessions` | `wars`, `incoming_raids`, `events` | phase 27 |
| `collapse.py` | The collapse matrix: a defeated campaign becomes a different story arc. | `resources`, `ships` | `story_arcs`, `events` | phase 29 |
| `victory.py` | Victory progress tracking. | `factions`, `territory`, `resources`, `research_projects` | `victory_tracking` | phase 20 |

### 6.8 Pure libraries, no tick

| Module | Owns | Reads | Writes | Tick |
|---|---|---|---|---|
| `economy_physics.py` | Deterministic economy physics: tiers, losses, transit. No database, no randomness, no clock. | nothing | nothing | library |
| `programme_cost.py` | Deterministic arithmetic for science programmes. | nothing | nothing | library |
| `unity.py` | Communications latency, the unity ceiling, stance drift by distance. Pure arithmetic. | nothing | nothing | library |
| `well_aegis.py` | Deterministic arithmetic for the Well and Aegis Sight. | nothing | nothing | library |
| `magic_cost.py` | What an act of magic costs the audit. `ACT_TABLE` holds the canon keys; `core/ooc.py` prices a declared act through it. | nothing | nothing | library |
| `roll_theater.py` | Outcome tiers, domain flavour, pool bets, blessings. Every roll becomes a story beat. | `sessions`, `characters`, `crew_roster`, `roll_history` | `roll_history`, `roll_pools`, `pool_bets`, `roll_blessings`, `roll_hall`, `events`, `resources` | library |
| `chrono_engine.py` | Multi-month time skips as one macro tick. | `events` | `sessions`, `resources`, `technologies`, `npc_internal_state`, `routine`, `time_skip_log` | library |
| `__init__.py` | Empty package marker. | nothing | nothing | library |

## 7. Entry points

### 7.1 CLI

`python3 scripts/cli.py <verb> [args]`. `__main__` pulls `--session N` and `--session=N` out of argv
first with `take_session_flag`, resolves the session, and rejects the call with exit code 2 when
nothing resolves.

The dispatcher holds 65 branches, so 65 primary verbs, and 117 accepted names including aliases.
Aliases share a branch: `flow` and `economy`, `dash` and `dashboard`, `bond` and `romance`,
`check`, `object` and `coord`, `mega` and `megastructure`, `port` and `ports`, `horror`,
`infestation` and `swarm`.

| Verb | What it does |
|---|---|
| `status` | Status headline for one session. |
| `continue` | Resolve a novel title to its session, point the arc at it, print the headline. |
| `tick` | Run one full tick. |
| `run <module>` | Run one module by `MODULE_MAP` key. |
| `save [label]` | Checkpoint into a story slot, then write a full `.sav`. |
| `load <file.sav>` | Restore from a `.sav`. Switches: `--keep-session`, `--allow-session-mismatch`, `--allow-novel-mismatch`, `--force`. |
| `export` | Print the markdown state snapshot. |
| `clear` | Dry run, or with `--yes` export a `.sav` then delete the nine play-state tables (`PLAY_STATE_TABLES`). |
| `query <sql>` | Run one SQL statement and print rows. |
| `health`, `modules`, `config` | Engine health, module flags, config summary. |
| `briefing`, `intel`, `flow`/`economy`, `dash`/`dashboard`, `tail`, `misc` | Read-only views. |
| `ooc <sub>` | The OOC console. 22 sub-verbs, below. |
| Domain verbs | `programme`, `assembly`, `duel`, `roll`, `voyage`, `check`, `sentiment`, `king`, `adjutant`, `decisions`, `lineage`, `templates`, `stream`, `memories`, `intimacy`, `intent`, `roll100`, `schema`, `sync-pack`, `character`, `mystery`, `science`, `cargo`, `build`, `mega`, `horror`, `wonders`, `social`, `prison`, `map`, `council`, `forge`, `spy`, `tech`, `fleet`, `career`, `shipyard`, `bond`, `artifact`, `world`, `inner`, `burn`, `op`, `craft`, `war`, `encounter`. |

`ooc` sub-verbs (`cmd_ooc`, `scripts/cli.py:3604`): `status`, `audit`, `rules`, `endings`, `lore`,
`note`, `snapshot save|load`, `spend`, `effects`, `know`, `persona`, `portrait`, `beats`, `milestone
list|add|done`, `exemption list|buy`, `suspicion`, `readiness`, `advance`, `mirror`, `stage`,
`events`, `prune`. `ooc audit --preview` answers the cost of the text and writes nothing.
`--session N` and `--session=N` both work; a bare positional is used by sub-verbs, not by the session
flag.

### 7.2 Kilo bridge

`scripts/kilo_bridge.py` is the strict JSON interface for editor commands: one action in, one JSON
object out, no SQL and no traceback on stdout. Invocation is
`python3 scripts/kilo_bridge.py <action> '<json params>'`. Every action is handled inside one
`try`, and a failure answers with `{"action": ..., "status": "error", "data": "<message>"}`.
Malformed params are refused before the action runs.

The dispatcher holds 33 top-level actions. Actions: `briefing`, `bonds`, `fleet`, `treasury`, `market`, `pirates`, `loc`, `char_query`,
`novel_recall`, `lore_pack`, `prisoners`, `scene`, `character`, `get_character_card`,
`get_interrogation_context`, `check`, `check_duplicate`, `memory`, `objectives`, `save`, `status`,
`time_skip`, `collapse_status`, `lineage`, `decisions`, `get_lore`, `write_lore`, `check_physics`,
`get_or_create_system_lore`, `get_ambient_lore`, `action_intent`, `manage_corp` (with sub-actions
`charter`, `directive`, `list`), `den_ops` (with `bases`, `raid`, `bounty`, `claim`).

The bridge calls `report_session_drift()` once per process, because the DSH worker imports the module
once and serves for hours: the bridge itself resolves the session per call, and the modules it
imports do not.

### 7.3 OOC bridge

`scripts/ooc_bridge.py` is the JSON stdin/stdout bridge for the harness. One request per line, one
JSON object out, non-zero exit on failure. `CALLS` holds nine calls:

| Call | Answers |
|---|---|
| `state` | The OOC state row: stage, deviation, points, debuff. |
| `turn` | Audit one turn of prose and fold it in. |
| `canon` | Companions, observer id, suspicion rows, milestones. |
| `portrait` | A character line for the portrait pipeline. |
| `context` | Story, persona block, context blocks, assembled text. |
| `persona` | The persona block and its boundary cases. |
| `inspect` | Inspect one character by name. |
| `direct` | Record a director note. Never audited as prose. |
| `slaves` | Paged slave rows. |

The bridge loads `~/.env` at import when the process carries no `OC_PG_HOST`. It takes only `OC_PG_*`
keys, never over an existing value: the same source the CLI uses, and no second source of truth. The
session stays per request, and an audit mirrors the harness state file.

### 7.4 Map server

`scripts/map_server.py` is a Flask app over the live database. It serves the galaxy map, the roster,
the play console and the character API, and it renders from the database with no embedded data.

| Route | Serves |
|---|---|
| `/` | The map page, rendered from `fetch`. |
| `/api/map` | Every map layer as JSON. |
| `/api/status` | Engine status. |
| `/roster`, `/play`, `/characters`, `/characters/<path:relpath>`, `/nav.js` | Pages and static assets. |
| `/api/roster`, `/api/play-url` | Roster and play-URL JSON. |
| `/api/characters`, `/api/characters/<id>` (GET) | Character list and one character. |
| `/api/characters/<id>` (POST), `/version` (POST), `/file` (POST) | Character edits, versioning, file writes. |
| `/api/ooc/context`, `/api/ooc/direct` (POST), `/api/ooc/trace` | OOC context, director notes, audit trace. |

Run with `--port 3460` (the documented default). `MAP_BIND` sets the listen address, default
`127.0.0.1`; a non-loopback address exits unless `MAP_PASS` is set. `MAP_DB_DSN` names a role for
this server, defaulting to `Config.DSN`; the session is read-only either way. Auth is HTTP basic
with `MAP_USER`/`MAP_PASS`, or `MAP_API_KEY`. `ooc_session()` resolves the engine views: an explicit
number wins, otherwise it follows the campaign whose OOC state was updated last.

## 8. Savegame

`core/savegame.py` writes and restores portable `.sav` files. A `.sav` is JSON with a `header` and a
`tables` object, one list of row objects per table.

Header fields: `format` (`tkg-sav`), `version` (`SAV_VERSION` = 2), `game_day`, `saved_at`,
`session_id`, `novel_id`, `partial_tables`, `unfiltered_tables`, `checksum`.

The checksum is the first 16 hex characters of the sha256 of the payload with `checksum` removed.
The file name is `save_<session>_day<game_day>_<timestamp>.sav` in `Config.BACKUP_DIR`.
`novel_id` comes from the session row. A session that does not exist raises `ValueError` instead of
writing a file that restores an empty campaign, and a table that fails to read raises
`SaveIncomplete` with nothing written.

### 8.1 What the snapshot covers

The table set is derived from the live schema, not a hand-written list. `_schema_inventory()` reads
the tables, which carry `session_id`, which hold vector columns, and the FK edges.
`classify_tables()` then splits what remains into session-scoped and global after removing
`EXCLUDED_TABLES`:

`_migrations`, `migration_versions`, `migration_hashes`, `savepoints`, `roll_history`,
`tick_summaries`, `price_history`, `narrator_cost_log`.

Vector tables are excluded as well, because a pgvector column cannot round-trip through JSON and the
RAG tables are re-ingestible. A table with no `session_id` is filtered through its FK parents when it
has one, and carried whole when it does not; above `MAX_IN_FILTER_IDS` (250,000) parent ids the child
is exported whole and named in `unfiltered_tables`. Tables carried only in part, or not at all, are
named in `partial_tables`.

### 8.2 What a save does not carry

- Excluded bookkeeping and telemetry (the eight tables above).
- Vector columns and the RAG tables.
- Anything in `partial_tables`: those tables are neither wiped nor restored, because the wipe deletes
  rows the file cannot put back.
- Tables the file carries whole are restored as they are, but a table the file omits is left alone
  rather than emptied.

A save file is a snapshot of one campaign. It is not a backup of the database, and it is not a
migration.

### 8.3 Restore

`import_sav(path, session_id=None, wipe=True, allow_session_mismatch=False, force=False,
allow_partial=False, allow_novel_mismatch=False)`.

Order of refusals:

1. The file is missing, or its `format` is not `tkg-sav`: `{"ok": False}`.
2. A table holds `{"__error__": ...}` instead of rows: `SaveIncomplete`. Older exports wrote that
   shape; a restore refuses rather than wipe a table it cannot refill.
3. The checksum does not match and the file writes anything: `{"ok": False}` unless `force` is set.
   A file with no checksum at all is restored with a warning.
4. The file names another session: `SessionMismatch`, unless `allow_session_mismatch`.
5. The file's novel differs from the target session's novel: `NovelMismatch`, a subclass of
   `SessionMismatch`, unless `allow_novel_mismatch`. A file written before the header carried a novel
   resolves its own session's `novel_id` instead, so older checkpoints still restore.
6. The wipe reaches another session's rows: `DetachRefused`, with nothing written.
7. Rows fail to restore: `RestoreIncomplete`, rolled back, unless `allow_partial`.

The wipe deletes the session's rows and the global tables in FK order from `pg_constraint` (children
first), not alphabetically, and never with `TRUNCATE ... CASCADE`. Where an FK cycle makes a
topological order impossible, the cycle's child columns are NULLed first. Tables left outside the
wipe that hold FKs into wiped tables are detached by a planned step, computed before any write.

`wipe=False` (`--keep-session`) loads without deleting first.

## 9. OOC

`core/ooc.py`, 1,810 lines, is the register engine: it audits the Host's prose for persona deviation
and keeps the running score. It sits beside `core/guard.py`, which checks factual contradictions.

The top half of the module is pure: rule compilation, layer splitting, matching, scoring. Only
`state`, `effective_rules` and `audit` touch the database.

### 9.1 Layers and kinds

`split_layers(text)` separates the prose surfaces: `LAYER_SOMATIC` (narration), `LAYER_DIALOGUE`
(quoted speech), `LAYER_BOTH`, and `LAYER_TOOL` for a tool argument. A rule declares which layer it
reads.

Rule kinds in `maya_rp.ooc_rules`: `somatic_lock`, `forbidden_lexicon`, `modern_phrasing`,
`knowledge`, `scripted_beat`. A knowledge rule's id names the fact (`fact:<key>`) and its pattern
matches prose that reveals it; `knowledge_findings()` checks who knows the fact before billing.
Scripted beats never bill deviation; they prove progress through `complete_milestone()`.

`compile_rule()` refuses a hostile pattern: a nested quantifier, a repeat count at or above
`_COUNT_CAP` (100), or a pattern longer than `MAX_PATTERN_CHARS` (400). A rule that will not compile
is reported once and stays inert. Text past `MAX_AUDIT_CHARS` (20,000) is not audited, and the count
of skipped characters comes back as `truncated_chars`.

### 9.2 Stages and deviation

Stages: `lockdown`, `selective`, `confrontation`. Each holds warn, critical and execution thresholds
and a per-turn decay lambda.

| Stage | Warn | Critical | Execution | Decay per turn |
|---|---|---|---|---|
| `lockdown` | 25 | 50 | 75 | 0 |
| `selective` | 40 | 75 | 100 | 2 |
| `confrontation` | 50 | 80 | 100 | 5 |

Deviation sits in `ooc_system_state.deviation`, 0 to 100. An audit sums the findings' deltas, adds
any priced magic, subtracts the stage decay when the turn carries no finding, and clamps. The debuff
ladder is read from the top: `execution` gives System Reclamation, `critical` gives Meridian Lock,
`warning` gives Neural Tremor.

### 9.3 One audit

`audit(text, session_id, ...)`:

1. Refuse a frozen campaign unless the call is a preview.
2. Read the state and the effective rules for the session, its traits and its stage.
3. Drop `scripted_beat` and `knowledge` rules from the prose pass, so nothing bills twice.
4. Match the prose, then add knowledge findings for present characters who cannot know a fact.
5. Complete any scripted beat the prose proved. Preview and tool turns write nothing.
6. Remove findings whose rule has a live exemption.
7. Price declared magic through `modules/magic_cost.py`. Undeclared magic costs nothing.
8. Compute the new deviation, the debuff, and the roleplay-point award.
9. In one transaction: update `ooc_system_state`, insert one `ooc_audit_events` row, and move
   `ooc_suspicion` for every observer the turn moved.
10. Mirror the harness state file.

Raw matched prose is never stored. The provenance row keeps a sha256 fingerprint of the matches and
their total length. `rule_id` on the event row names the one rule that fired, or none when several
fired, because the column has an FK into `ooc_rules`.

### 9.4 Rules, exemptions, beats, suspicion

- `effective_rules(session, traits, stage)` reads the campaign-scope and trait-scope rules and
  filters by stage.
- An exemption is bought with roleplay points and silences one rule, optionally under a condition or
  for a time to live.
- A milestone is a scripted beat with a stage, a trait, a reward, and an optional pattern or latch.
  `beats_from_prose()` completes one on the turn the narrator writes it. A required beat past its
  window is reported by `overdue_milestones()` and never billed.
- Suspicion is per observer, in `ooc_suspicion`. A hidden micro-inconsistency adds
  `SUSPICION_MU` (5); a clean turn relaxes `SUSPICION_MU_DECAY` (1). Bands: `watchful` at 25,
  `probing` at 60, `certain` at 90. `modules/social.py` and `modules/council.py` read the band.

### 9.5 What the tick fails closed on

The OOC engine is not a tick phase; it runs on the prose path (the bridge's `turn`, the CLI's
`ooc audit`) and on the action path. What fails closed:

- A frozen campaign: every writer raises `FrozenSession` before any write, and the audit refuses.
- An unreadable frozen list with maintenance not armed: `FrozenListUnreadable` propagates and the
  write is refused.
- Maintenance armed: the register stands down. Deviation and decay both stay put, the audit row is
  still written and marked `skipped/maintenance`, and magic is not priced. The record shows why
  nothing moved instead of showing a gap.
- A broken regex: the rule is inert and reported once.
- A pattern or text past the caps: the rule is refused, or the tail is not audited and the count is
  reported.

### 9.6 OOC tables

`ooc_system_state` (one row per session: `session_id`, `arc_stage`, `deviation`,
`roleplay_points`, `audits`, `findings`, `debuff`, `updated_at`), `ooc_rules`, `ooc_audit_events`,
`ooc_suspicion`, `ooc_exemptions`, `ooc_milestones`, `ooc_endings`, `ooc_lorebook`,
`ooc_directives`.

## 10. Migrations

### 10.1 Numbering and files

`migrations/` holds 115 `.sql` files plus two Python seeds. Names start with a three-digit number
(`000` to `140`) and end with a description: `137_novels.sql`, `140_research_gate_names.sql`. Files
that carry a letter suffix (`068b`, `069b`, `069c`, `092b`) are follow-ups to their base number.
The three `seed_tkg_*.sql` files carry no number.

`_migrations` records what ran: 114 rows, all unique, newest `140_research_gate_names.sql`
(read 2026-10-10).

Two shapes in the directory need care:

- 17 numbers carry two or more files. Order inside a number falls to the alphabetical tail, so
  `083-crew-expansion.sql` runs before `083-events-ships-indexes.sql`, and a reader cannot tell the
  intended order from the number.
- 19 rows in `_migrations` hold a name without the `.sql` suffix, while the runner matches on
  `Path.name`. Eleven of those rows also exist with the suffix, and the other eight name a file no
  suffixed row names. The consequence is practical, not theoretical: `scripts/migrate.py` never
  matches a suffix-less file, so those eight files fall into the legacy set even though the table
  records them as applied.

### 10.2 The runner

`python3 scripts/migrate.py`:

1. Creates `maya_rp._migrations` if it is absent.
2. Reads the applied names and the newest recorded name.
3. Splits the files into pending and legacy. A file whose exact name is recorded is skipped. A file
   whose name sorts before the newest recorded name, and is not recorded, is **legacy**: reported,
   never executed, unless `MIGRATE_ALLOW_LEGACY=1`. Older files were applied by hand or recorded
   under another name, and replaying them is not safe. Measured 2026-10-10: 17 legacy files, 9 never
   recorded in any form and 8 recorded without the `.sql` suffix, 7 carrying a destructive statement.
4. Runs each pending file in name order, records it, and stops at the first failure.

Each file runs behind this runner's search path, in one statement string:

```
SET LOCAL search_path TO maya_rp;
<the file's text>
```

`SET LOCAL` ends with the transaction, so the path cannot outlive the file that set it. A pooled
connection handed to the next user keeps the DSN's path, never a migration's. A file that opens its
own `BEGIN` and `COMMIT` keeps the setting across its own statements too. `tests/test_novel_binding.py`
holds the two dry-run files to that shape: one `BEGIN;`, one `COMMIT;`, open before close, and one
`SET LOCAL search_path TO maya_rp;` line.

`seed_tkg_*.sql` sorts after `140_research_gate_names.sql`, so those three files classify as pending
and the runner will execute them. Read them before running the migration verb on a live database.

### 10.3 Owner versus role

Schema `maya_rp` is owned by role `maya`. The built-in DSN names `rp_engine`, and the test suite
connects as `rp_engine` too. `ALTER TABLE` needs the owner, so a test cannot execute a migration's
DDL against the live table. `tests/test_novel_binding.py` handles that by creating an empty `pg_temp`
copy of every table the file names, pointing the search path at the copy, running the file twice, and
rolling the whole transaction back. A live table is unreachable under that path, so the dry run
proves the file runs and re-runs without applying it.

### 10.4 Writing a migration that is safe to run twice

Every migration in this tree follows the same shape.

1. Open with a header comment: the number, what the file does, why it exists, what was read before
   writing it, and whether it is applied.
2. `BEGIN;` then `SET LOCAL search_path TO maya_rp;`.
3. Guard every object: `CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`,
   `CREATE INDEX IF NOT EXISTS`, `INSERT ... ON CONFLICT DO NOTHING`, `DO $$ ... IF NOT EXISTS $$`.
4. Guard every backfill so it matches only the rows it must move, and names the value it replaces
   (`WHERE novel_id = 'scratch'`), so a re-run cannot revert a later change.
5. Prove the precondition before the change. A file that assumes a state it cannot verify raises
   from a `DO` block and stops before altering anything.
6. `COMMIT;` and a rollback line: the exact statements that undo the file.
7. State `Safe to run twice` or the reason it is not.

Precedent files: `137_novels.sql` (guarded table, guarded column, `ON CONFLICT` insert, two guarded
updates), `138_bind_state.sql` (precondition checks in `DO` blocks, key swap compared before it is
applied, backfills that match only NULL), `140_research_gate_names.sql` (a value that already names
its project matches no slug).

## 11. Testing

`tests/` holds 280 test files plus `conftest.py`. The suite runs against the live `maya_rp` database
as role `rp_engine`, which owns none of the tables.

`pyproject.toml` sets `asyncio_mode = "auto"` and `testpaths = ["tests"]`, so an async test needs no
marker.

Commands:

| Purpose | Command |
|---|---|
| One file | `python3 -m pytest -q tests/test_session.py` |
| One test | `python3 -m pytest -q tests/test_x.py::test_y` |
| The suite | `python3 -m pytest -q` |
| Skip the suite lock | `RP_TEST_NO_LOCK=1 python3 -m pytest -q` |

The last recorded full run in the working tree (2026-10-10) reads `6 failed, 4545 passed, 2 skipped
in 572.03s`.

### 11.1 The suite lock

One pytest process runs at a time. `conftest.py:50` `_one_suite_at_a_time` is session-scoped and
autouse, and takes an exclusive `flock` on `RP_TEST_LOCK` (default
`/tmp/rp-engine-pytest.lock`). A second run waits and prints how long it waited. The kernel releases
the lock when the process exits, so there is no stale lock to clear.

Concurrent runs against one database produced a different failure set each time, which teaches a team
to ignore failures.

### 11.2 Fixtures

| Fixture | What it gives a test |
|---|---|
| `scratch_session` | A session id in 900 to 999, computed as `900 + crc32(module name) % 100`, so one file gets one id and two runs agree. Teardown discovers every `maya_rp` table with a `session_id` column and deletes this session's rows from each. |
| `scratch_campaign` | `scratch_session` plus its `sessions` row, for tables whose FK points at `sessions`. Teardown clears the child rows first and removes the row last. |

`conftest.py` also sets `DEEPSEEK_API_KEY` to a placeholder when it is absent, so an unset key does
not read as a defect, and redirects `OOC_STATE_FILE` to a temp path so a scratch audit never mirrors
into the live state file.

### 11.3 The isolation guard

`conftest.py:169` documents and `:430` installs a guard that refuses a write into a live campaign
before it reaches the database. A statement trips when all three hold:

- it starts with `INSERT`, `UPDATE` or `DELETE`, after whitespace, comments and a writing `WITH`,
- it mentions `session_id` or targets `sessions`,
- a positional argument is a live campaign id, or the SQL carries a literal
  `session_id = <live id>` / `session_id IN (<live ids>)` / an insert of the same.

Reads pass. A trip raises `AssertionError` and is recorded, so a test whose code swallows the
exception still fails at teardown. `@pytest.mark.live_session_ok` opts a test out; use it only when
the test must write a live campaign.

The guard wraps three layers: `Database.execute`, `executemany`, `fetch`, `fetchrow` and `fetchval`;
the connection `Database.transaction()` yields; and the `asyncpg.Connection` class, so a test that
calls `pool.acquire()` is still covered.

### 11.4 Session set

| Kind | Ids |
|---|---|
| Scratch | 900 to 999, one slot per test file. A test writes here. |
| Live campaigns | Two ids, both in `LIVE_SESSIONS`. The isolation guard refuses writes to either. |
| Explicit | `RP_SESSION`, `--session`, or the active arc file. A read-only test can name one. |

### 11.5 Doctrine

A behaviour change carries three arms.

| Arm | Tree | Required result |
|---|---|---|
| base | Before the fix. | The test fails. A test that passes on the unfixed tree proves nothing. |
| fix | After the fix. | The test passes, and the suite stays green. |
| mutation | The fix, with the code under test removed or neutered. | The test still fails. This arm separates a test that discriminates a wrong implementation from one that only proves a symbol exists. |

Two more habits hold the suite honest. A migration file is written, never applied, by a test: the dry
run above is how a file proves it runs twice. And a failing suite is read, not rerun: concurrency,
stale state and a missing key all have specific fixes in this file.

## 12. Config and DSN

`core/config.py` is the single settings file. `class Config` is static; every value is a class
attribute.

### 12.1 DSN resolution

`_resolve_dsn()` answers in this order:

1. `RP_ENGINE_DSN` from the environment.
2. The host's own DSN file, `~/.config/rp-engine/dsn`, mode 600. It sits outside every repository, so
   the password travels with the host, not with the tree.
3. The built-in `_DEFAULT_DSN`: `postgres://rp_engine@<host>:5432/<database>?search_path=maya_rp,public`.
   It carries no password, because this file is published.

`RP_ENGINE_DB` then replaces the database name in whichever DSN applies, and a name that is not a
plain database name raises `RuntimeError` with no DSN in the message. `OC_PG_*` is deliberately not
read: on the engine host it names a superuser, and the engine must keep running as `rp_engine`.

`DSN_FALLBACK_USED` is true only when neither source named a DSN, and the pool warns once on that
path.

The `search_path` parameter is an asyncpg server setting. `psql` rejects it
(`invalid URI query parameter`), so an operator using the same DSN with `psql` strips the query
string.

### 12.2 Session

`Config.SESSION_ID` resolves once, at import, through `core.session.resolve_session`. When the
resolver fails, the process falls back to the legacy campaign, which is the frozen reference, and
sets `SESSION_FALLBACK_USED` so the fallback is announced. Entry points that must not guess
(`scripts/cli.py`, the bridges, the tick) resolve per call instead.

### 12.3 Knobs that matter

| Knob | Default | Effect |
|---|---|---|
| `DSN`, `DSN_FALLBACK_USED` | resolved at import | The pool's connection string and whether the built-in one was used. |
| `DB_MIN_SIZE` / `DB_MAX_SIZE` | 1 / 15 | Pool bounds. The upper bound covers a concurrent bridge and tick. |
| `DB_TIMEOUT` | 30 | Connection timeout, seconds. |
| `SESSION_ID` | resolved | The process default for anything that names no session. |
| `MODULES` | 82 entries, one `False` | `is_module_active(name)` gates every tick call. |
| `TIME_MULTIPLIER` | 4 | Game days per real day, read by `core.utils.calc_game_days`. |
| `RP_MODE_ACTIVE`, `RP_TONE`, `RP_UNIVERSE` | `True`, `English`, `TKG` | Narrative voice and universe. |
| `ROOT` | the engine directory | Base for `MIGRATIONS_DIR` and `LOG_DIR`. |
| `BACKUP_DIR`, `ARCHIVE_DIR` | host paths outside the repository | Where `.sav` files, checkpoints and archives land. |
| `MIGRATIONS_DIR`, `LOG_DIR` | `ROOT/migrations`, `ROOT/logs` | |
| `SENTRY_DSN`, `OPENAI_API_KEY`, `REPLICATE_API_KEY` | `None` | Optional telemetry, image and narration services. |

### 12.4 The time multiplier

`Config.TIME_MULTIPLIER` is 4: four game days per real day. `core/utils.calc_game_days(last_tick)`
multiplies elapsed real hours by it and divides by 24. The knob is read at call time, not copied at
import, so changing it changes what the tick advances. The clock the modules read is
`resources.last_tick_at`, one row per campaign.

## 13. Operations

### 13.1 Backups

Two mechanisms, both writing under `Config.BACKUP_DIR`.

| Mechanism | Trigger | Output | Coverage |
|---|---|---|---|
| `.sav` export | `export_sav()` after every tick, and `cli.py save` | `save_<session>_day<day>_<timestamp>.sav` | Full table dump, restorable, portable. |
| Story checkpoint | `cli.py save [label]` through `StateManager.save_checkpoint` | `checkpoint_<slot>_<timestamp>.md` plus a `story_checkpoints` row | Markdown summary: resources, territories, factions, recent story. Three slots per session. |

The tick keeps the last 12 `.sav` files per session. The rotation sorts file names, and the day
number is not zero padded, so the set it keeps is name-ordered, not newest-first. Section 14 records
it.

A `.sav` is the portable artifact. It does not replace a database backup: the excluded telemetry
tables, the vector tables and the partial tables are outside it.

### 13.2 Applying migrations

Two paths, and they differ in who they run as.

| Path | Role | Notes |
|---|---|---|
| `python3 scripts/migrate.py` | The configured role, which the built-in DSN names `rp_engine` | Applies pending files, records each, refuses legacy. Needs owner rights for DDL, so a migration that alters a table fails here unless the role holds them. |
| The operator script kept beside the pre-apply snapshot, outside the repository | `maya`, the owner | Verbs `backup`, `apply`, `verify`. `apply` snapshots first, then applies the named files with `ON_ERROR_STOP=1`, records each in `_migrations`, then runs the postconditions. |

The operator snapshot is per table: `\copy (SELECT * FROM maya_rp.<t>) TO '<t>.csv' WITH CSV HEADER`
plus `\d maya_rp.<t>` as text, for the tables the migrations touch, with `_migrations` listed
separately. It takes that shape because the client `pg_dump` version on the host is older than the
server, and `pg_dump` aborts on the version check while `psql` does not.

A migration written by a card is written, never applied, by the card. The apply is the operator's
step, and it is recorded in `_migrations` either way.

### 13.3 The public repository

This documentation ships in the public repository `EnRaiha/rp-novel-engine`. The engine tree itself
lives inside a private repository whose remote is a self-hosted forge on the tailnet; it has no
remote of its own. No script in `scripts/` builds a public snapshot, so a publication is assembled
outside the tree.

What never leaves the private side:

- The campaign database: every row in `maya_rp`, including session rows, character sheets and canon
  state. The public repository carries code, migrations and documentation only.
- The novel text and canon files under `adventures/`, which live in the vault above this directory.
- `.sav` files and story checkpoints.
- The host DSN file, the maintenance state files, and the play flag.
- Host paths, host names and backups for this machine.

Inside the tree, two helpers move private material the other way, from the engine into the private
vault, and never into the public repository: `scripts/sync_pack.py` copies canon files into the
vault's `rp-dev` wiki area and regenerates a single-file source bundle there; `scripts/harness_sync.py`
reads editor telemetry from `public.opencode_sessions` into `harness.budget`.

`dist/notebooklm/` is a local upload bundle. It is gitignored, and it is built outside the tree.

## 14. Known gaps

Each line names the file and what the code does. Nothing here is fixed by this document.

1. **`conversation_log` is mapped but cannot run.** `scripts/orchestrator.py:569` puts
   `conversation_log` in `MODULE_MAP`, and `modules/conversation_log.py` exports no `run_tick`, so
   `cli.py run conversation_log` reaches `mod.run_tick` and reports a crash.
2. **Module flags and one tick function reach nothing.** `core/config.py:173-174` enables
   `dramatic_structure` and `meanwhile`; neither is in `MODULE_MAP` nor called by the tick, and
   `core/dramatic_structure.py` exports no `run_tick`. `modules/agnes.py:20` answers every prompt with
   a stub, and its flag is `False` (`core/config.py:163`). `modules/character_profile.py` defines
   `run_tick` at `:397`, and neither the tick nor `MODULE_MAP` names it.
3. **Three tick calls drop their failure.** `scripts/orchestrator.py:235`, `:259` and `:261` call
   `tick()` for `economy`, `voyage` and `population_sentiment` without the `else` that increments
   `modules_failed`, so a failure in those modules prints as neither OK nor failed and
   `tick_summaries.alerts_count` misses it.
4. **The config summary reports a stale table count.** `core/config.py:221` prints
   `maya_rp (260 tables)`. The live schema holds 309 base tables and 13 views.
5. **The registry's own count is one behind.** `core/binding.py:9` documents 48 catalogue tables;
   the set holds 49.
6. **The map server holds two session resolvers.** `scripts/map_server.py:195`, `:200` and `:203`
   pin one campaign id inside `load_map_data`, while `ooc_session()` at `:152` resolves per request.
   The map layers and the panels can follow different campaigns.
7. **The CLI usage line undercounts.** `scripts/cli.py:3988` lists twelve verbs; the dispatcher holds
   65.
8. **Host paths are baked into module constants.** `core/config.py:121-122` set `BACKUP_DIR` and
   `ARCHIVE_DIR` to absolute host paths, `scripts/map_server.py:33` sets `ASSETS` to a vault path,
   and `scripts/sync_pack.py` writes to vault paths. A clone on another host edits these or fails.
9. **A credential sits in a script.** `scripts/harness_sync.py:19` hardcodes the `maya` role's
   password and a host address. Move it to the environment or the DSN file.
10. **Some recorded migrations cannot match their file.** 19 rows in `_migrations` lack the `.sql`
    suffix, and `scripts/migrate.py:97` compares against `Path.name`. Eight of those rows are the
    only record of their file; eleven duplicate a suffixed row.
11. **The seed files classify as pending migrations.** `migrations/seed_tkg_*.sql` sort after
    `140_research_gate_names.sql`, so `scripts/migrate.py` treats them as pending and runs them.
12. **Migration numbers collide.** 17 numbers carry two or more files, and the run order inside a
    number is alphabetical.
13. **`.sav` rotation is name-ordered.** `scripts/orchestrator.py:533-537` keeps the last 12 by
    sorted file name, and `core/savegame.py` writes the day unpadded, so day 9 sorts after day 100.
14. **Most of the schema has never been written.** `core/tick_writes.py:9` records nine of eighty
    tick modules with no write statement and 203 of 307 tables never written (2026-10-04). Measured
    on 2026-10-10: 7 of the 78 ticked modules carry no write statement, and 147 of 309 base tables have
    never received an insert or update. The counter resets with the statistics collector, so the
    table number is a reading, not a constant.
15. **The module contract has twelve exceptions.** `modules/README.md:3` requires every module in the
    directory to export `run_tick`; 12 do not (`_economy`, `chrono_engine`, `conversation_log`,
    `economy_physics`, `local_gen`, `magic_cost`, `meanwhile`, `programme_cost`, `roll_theater`,
    `ship_modules`, `unity`, `well_aegis`), and the package marker `__init__.py` is the thirteenth
    file.
16. **Two phases cannot move a table.** `modules/guardrails.py` and `modules/event_catalog.py`
    contain no SQL at all, so phases 18 and 16 return OK without writing.
17. **The checkpoint export is campaign-specific.** `core/state.py:35` filters territories by
    `controlling_faction='Setia Empire'`, so a campaign whose holder has another name exports an
    empty territory list.
18. **The built-in DSN does not work with `psql`.** `core/config.py:54` carries
    `?search_path=maya_rp,public`, which asyncpg accepts and libpq rejects with
    `invalid URI query parameter`.
19. **No publish path exists in the tree.** Nothing under `scripts/` builds the public snapshot named
    in section 13.3.

## 15. Related skills and references

### 15.1 DSH skills that touch this engine

DSH loads a skill from `~/.dsh/skills/<name>/SKILL.md` and `~/.opencode/skills/<name>/SKILL.md`. Load
one before the task it names, not after.

| Skill | Use it for |
|---|---|
| `rp-engine-dev` | This document's short form. Load before a code change: session rules, test doctrine, migration doctrine, asyncpg traps. |
| `rp-ooc-engine` | Play, not development. The GM interface and the deviation overseer: `rp save`, `rp tick`, `rp end`, OOC audits, arc stage. |
| `drill` | One issue, one worktree, one evidence chain: localize, blast radius, edge cases, red proof, green proof, review gate. |
| `orchestrate-loop` | A task that spans many files: stay in the orchestrator seat, delegate reading and writing, keep the expensive checks. |
| `prep` | One durable session-state file under `.dsh/prep/`, read after every compaction. |
| `claim-audit` | Before a push: label every claim, falsify a coverage claim by deleting the code under test, re-derive line numbers last. |
| `search-tools` | Which search to run: `rg`, `tgrep`, `ast-grep`, `rga`, `c2g`. |
| `c2g` | Symbol lookup, callers, callees, blast radius, diff impact, from the local code2graph index. |
| `dts` | The writing standard every comment, docstring and error string in this tree follows. |
| `pr-craft`, `issue-craft` | Reviewing a diff, writing a PR body, opening an issue that survives triage. |
| `maya-cortex` | Recall: past sessions, the graph, the capability map, where a decision was written down. |
| `comfyui-workflow` | The image pipeline behind character portraits. |
| `codetrack` | Snapshot before a risky change; recover code that was clobbered. |

The OpenCode tree (`~/.opencode/skills/`, 316 skills) adds the wider set: `humanizer` and `manusiawi`
for voice, `learn` / `review` / `coach` for spaced repetition, `rust-skills`, `ui-ux-pro-max`, and the
`bmad-*` family for spec, PRD and review workflows.

### 15.2 The card set that produced most of this code

Private vault, `wiki/rp-dev/dsh-tasks/`. One card is one commit. Read `README.md` there first: it
carries the binding rules and the asyncpg quirks.

| Path | What it holds |
|---|---|
| `wiki/rp-dev/dsh-tasks/README.md` | The rules, the tiers, the run order. |
| `wiki/rp-dev/dsh-tasks/T0-*.md` | Infrastructure: DSN override, test database, plugin bridge, OOC regex bounds. |
| `wiki/rp-dev/dsh-tasks/T2-*.md` | Modules the tick runs on the current arc, including `T2-research-gate-repair` and `T2-megastructure-wiring`. |
| `wiki/rp-dev/dsh-tasks/T3-*.md` | Dormant findings: `T3-novel-binding`, `T3-novel-binding-code`, `T3-rp-continue-novel`, and the per-subsystem cards. |
| `wiki/rp-dev/dsh-tasks/T4-*.md` | Behaviour changes, frozen guards, one-shot scripts. |
| `wiki/rp-dev/dsh-tasks/B-toll-semantics.md` | The gate toll question, answered: a flow per game day, bounded by the standing between the factions. |
| `wiki/rp-dev/PLAN-WIRING-RESEARCH-NOVEL-2026-10-10.md` | The wiring, research-gate and novel plan the recent work follows. |
| `wiki/rp-dev/MODULE-FIX-PLAN-2026-10-09.md`, `UNFIXED-2026-10-09.md`, `STATUS-2026-10-10.md` | What the fix pass covered, what it did not, where it stopped. |
| `wiki/rp-dev/HANDOFF-DSH-ooc-engine-20261009.md` | The handoff a later session resumes from. |

### 15.3 In-repo references

| Path | What it holds |
|---|---|
| `README.md` | What the engine is, how to run it, how the DSN resolves. |
| `PLAN.md`, `QA-REPORT-INTEGRATION-2026-08-15.md`, `QA-REPORT-RP-ENGINE-2026-09-16.md` | The plan the engine grew from and the two QA passes. |
| `docs/OOC-ENGINE-FULL-20260921.txt` | The OOC engine in full: layers, kinds, stages, deviation, enforcement. |
| `docs/OOC-FASA-REPORT-2026-09-21.md` | The phase report that followed it. |
| `docs/ENGINE-FULL-20261010.md` | This file. |

### 15.4 Working references outside the repo

| Path | What it holds |
|---|---|
| `main/reference/savegame-workflow.md` | The `.sav` contract, the header, the novel guard. |
| `main/reference/rp-loadout.md` | The lines `cli.py status` prints, and what each reads. |
| `main/rp-continue-session.md` | The `rp continue` ritual. |
| `wiki/rp-dev/LORE-PRECEDENCE-2026-10-05.md` | Which lore wins when two novels disagree. |
| `wiki/rp-dev/SESSION-MAINTENANCE-2026-10-02.md` | `core/session.py` as the single source, the frozen list, `gm_maint.py`. |
| `rp-engine-py/.dsh/loop/` | Briefs and reports of the card runs, gitignored. |
| `rp-engine-py/.dsh/prep/session-<date>.md` | The session state a compaction resumes from. |

### 15.5 Related systems

| System | Relation |
|---|---|
| NodeDB, `cortex_nodedb_*` and `cortex_codegraph_*` | The knowledge graph and the code graph. Read-only from the engine's side. |
| Ollama, `localhost:11434` | Embeddings per corpus: memory `bge-m3` (1024), code `qwen3-embedding:0.6b` (1024), skills `minilm_onnx` (384). Store rules: `~/Embed/RULES.md`. |
| `maya_rag.unified` | Session memory the recall tools query. Separate from `maya_rp`. |
| `rp-novel-engine` on GitHub | The public snapshot of this directory. Build it as section 13.3 describes. |
