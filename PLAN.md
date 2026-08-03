# RP Engine — Complete Port to Python

**Scope:** 72 Rust modules (archive/rp-engine-rust/) + 10 JS skill modules (archive/rp-engine-js-skills/) → single Python engine.
**Current:** 14 Python modules exist. 41 Rust + 10 JS + integration layer remain.
**Target:** One engine, one config, one schema.

---

## How to Read This Plan

```
[✅]  Already ported to Python
[R→P]  Need to port from Rust source (archive/rp-engine-rust/src/)
[J→P]  Need to port from JS source (archive/rp-engine-js-skills/)
[🆕]   New Python build (no direct Rust/JS equivalent)
```

---

## Core Layer — `rp-engine-py/core/`

| File | Rust Source | JS Source | Status | Lines |
|------|------------|-----------|--------|-------|
| `config.py` | `config.rs` | — | ✅ Done | 120 |
| `db.py` | `db.rs` | — | ✅ Done (basic) | 78 |
| `state.py` | `snapshot.rs`, `backup.rs` | — | ✅ Done | 100 |
| `events.py` | `event_bus.rs` | `event-bus.js` | ✅ Done | 50 |
| `reputation.py` | `morality.rs`, `guardrail.rs` | `reputation-engine.js` | ✅ Done | 100 |
| `log.py` | — | — | ✅ Done | 70 |
| `utils.py` | `rng.rs` | `game-utils.js` | ✅ Done | 30 |
| `narrative_time.py` | — | `narrative-time.js` | [J→P] ~150 |
| `conflicts.py` | — | `cross-module-conflicts.js` | [J→P] ~150 |
| `schema.py` | `schema.rs` (1,212 lines!) | — | [R→P] 1,212 |
| `seed.py` | `seed.rs` | — | [R→P] ~200 |
| `migration.py` | `db.rs` (migration runner) | — | [R→P] ~200 |
| `metrics.py` | `metrics.rs`, `metrics_exporter.rs` | — | [R→P] ~100 |
| `interpreter.py` | `interpreter.rs` | — | [R→P] ~300 |
| `skill_health.py` | `skill_test.rs`, `skill_watch.rs` | — | [R→P] ~220 |

---

## Module Layer — `rp-engine-py/modules/`

### Already Ported (14 modules)

| File | Covers Rust | Lines | Status |
|------|-----------|-------|--------|
| `economy.py` | economy.rs, market.rs, trade.rs, population.rs | 80 | ✅ |
| `battle.py` | combat.rs, tactics.rs | 260 | ✅ |
| `diplomacy.py` | diplomacy.rs | 108 | ✅ |
| `research.py` | research.rs | 135 | ✅ |
| `narrative.py` | events.rs, narrator.rs (partial) | 110 | ✅ |
| `pirates.py` | — | 248 | ✅ |
| `slave_system.py` | — | 310 | ✅ |
| `megastructures_ports.py` | mega.rs, defense.rs (ports) | 385 | ✅ |
| `infrastructure.py` | colony.rs (buildings) | 225 | ✅ |
| `space_wonders.py` | galaxy.rs, explore.rs | 475 | ✅ |
| `space_horror.py` | horror.rs | 490 | ✅ |
| `victory.py` | victory.rs | 60 | ✅ |
| `characters.py` | char_events.rs, crew.rs, intimacy.rs | 82 | ✅ |
| `reputation.py` (core) | morality.rs, guardrail.rs | 100 | ✅ |

### Rust → Python (need full port)

| Module | Rust Source | Lines | Est. Days | System |
|--------|-----------|-------|-----------|--------|
| `ship_generation.py` | `ship_gen.rs` | 314 | 1.5 | Random ship stats, class → parameters |
| `ship_building.py` | `build.rs`, `build_auto.rs` | 350+ | 1.5 | Build queue, resource deduction, auto-build |
| `refit.py` | `refit.rs` | 161 | 1 | Install modules, upgrade ships |
| `fleet.py` | `fleet.rs`, `fleet_ai.rs` | 300+ | 2 | Fleet formation, AI movement, assignments |
| `weapon_design.py` | `weapon_design.rs` | 183 | 1 | Design blueprints, produce weapons, upgrades |
| `tech_tree.py` | `tech_tree.rs` | 300 | 2 | Tech tree view/unlock, lab management |
| `manufacturing.py` | `manufacturing.rs` | 364 | 1.5 | Factory management, recipes, production |
| `academy.py` | `academy.rs` | 391 | 1.5 | Crew training, programs, graduation |
| `university.py` | `university.rs` | 460 | 2 | Research projects, faculty, publications |
| `alchemy.py` | `alchemy.rs` | 484 | 2 | Transmutation, labs, infusions, catalysts |
| `exoscience.py` | `exoscience.rs` | 756 | 3 | Science missions, anomaly analysis, theories |
| `archaeology.py` | `archaeology.rs` | 338 | 1.5 | Dig sites, survey, excavation |
| `artifacts.py` | `artifacts.rs` | ~150 | 1 | Artifact management, equipping, examination |
| `espionage.py` | `espionage.rs` | 102 | 1 | Spy missions, intel operations |
| `darkops.py` | `darkops.rs` | 106 | 1 | Black ops, deniable operations |
| `stealth.py` | `stealth.rs` | 93 | 1 | Stealth units, anti-cloak, spy lanes |
| `disasters.py` | `disasters.rs` | 287 | 1.5 | Disaster generation, response, recovery |
| `adventures.py` | `adventure.rs` | 202 | 1 | Random encounters, exploration events |
| `epilogue.py` | `epilogue.rs` | 106 | 1 | End-game narrative, victory wrap-up |
| `narrator.py` | `narrator.rs` | 105 | 1 | Narrative prose generation |
| `news.py` | `news.rs` | 406 | 2 | News articles, public opinion, propaganda |
| `quest.py` | `quest.rs` | 120 | 1 | Quest generation, acceptance, completion |
| `image_gen.py` | `image_gen.rs` | 148 | 1 | AI image prompt generation |
| `agnes.py` | `agnes.rs` | 221 | 1 | Agnes AI integration (Sapiens gateway) |
| `event_catalog.py` | `event_catalog.rs` | 2,027 | 5 | Full event catalog (60+ encounter types) |
| `defense.py` | `defense.rs` | ~150 | 1 | Defense installations, upgrades |
| `faction_ai.py` | `faction_ai.rs` | 458 | 2 | Faction AI economy, ship building, diplomacy |
| `siege.py` | `siege.rs` | 173 | 1 | Siege mechanics, advancement |
| `guardrails.py` | `guardrail.rs` | 408 | 1.5 | Content guardrails, safety checks |

### JS → Python (need full port)

| Module | JS Source Files | Lines | Est. Days | System |
|--------|----------------|-------|-----------|--------|
| `prison.py` | capture-engine, interrogation-ops, prisoner-conversion, prisoner-intimacy, prison-state | 869 | 1.5 | Capture, 3-tier interrogation, conversion, escape |
| `romance.py` | romance-engine, romance-state, scene-generator, healing-tracker, indulgence-tracker | 1,036 | 2 | Bond thresholds, jealousy, voices, scenes |
| `social.py` | crew-relationships, loyalty-engine, morale-tracker, social-events | 816 | 1.5 | Crew bonds, ringleader detection, mutiny |
| `mystery.py` | clue-chain, interrogation-engine, investigation-log, red-herring-engine | 826 | 1.5 | Clue graphs, deduction, skill XP |
| `council.py` | cabinet-manager, conspiracy-engine, counter-espionage, governance-events, influence-tracker, role-manager | 1,284 | 2 | Voting, cohesion, plots, decrees |
| `celestial.py` | celestial-index, faction-state, fog-of-war, nav-planner, planet-catalog, route-mapper, system-registry | 1,091 | 1.5 | Dijkstra routes, visibility, faction shifts |
| `fleet_economy.py` | resource-burn, caravan-events, production-queue, trade-deals | 426 | 1 | Fuel/food burn, caravan scheduling |
| `tactics.py` | combat-system, military-ops, tactical-positioning | 494 | 1 | Damage types, 7 ops, 6×6×5 grid |
| `events_extend.py` | consequence-chain, encounter-scaler, encounter-tables, event-generator | 612 | 1 | 60+ encounter templates, cooldowns |

---

## Infrastructure Layer

These are Rust binaries/services that need Python equivalents.

| System | Rust File | Lines | Python Target | Est. Days |
|--------|----------|-------|--------------|-----------|
| **Web API server** | `web.rs` | 886 | `server/app.py` (FastAPI) | 3 |
| **Telegram bot** | `telegram.rs` | 971 | `modules/telegram_bot.py` (Pyrogram) | 3 |
| **Health endpoint** | `health.rs` | ~80 | `server/health.py` | 0.5 |
| **Daemon mode** | `daemon.rs` | 482 | `scripts/daemon.py` | 2 |
| **CLI dispatch** | `cli.rs`, `main.rs` | ~500 | `scripts/cli.py` (extend) | 2 |

---

## Phase Order (Recommended)

### Wave 1 — Core + High Narrative Impact (Week 1-2)
```
core/schema.py         — Data models (1,212 lines from schema.rs)
modules/prison.py      — Prison system [J→P] 869 lines
modules/romance.py     — Romance engine [J→P] 1,036 lines
modules/social.py      — Social dynamics [J→P] 816 lines
modules/council.py     — Council/governance [J→P] 1,284 lines
core/narrative_time.py — Game day tracking [J→P] ~150 lines
core/conflicts.py      — Conflict resolver [J→P] ~150 lines
```

### Wave 2 — Economy & Combat (Week 2-3)
```
modules/ship_generation.py  — Ship stats [R→P] 314 lines
modules/ship_building.py    — Build queue [R→P] ~350 lines
modules/refit.py            — Refit/upgrade [R→P] 161 lines
modules/fleet.py            — Fleet AI [R→P] ~300 lines
modules/weapon_design.py    — Weapons [R→P] 183 lines
modules/tactics.py          — Combat ops [J→P] 494 lines
modules/fleet_economy.py    — Resupply [J→P] 426 lines
modules/events_extend.py    — Encounters [J→P] 612 lines
```

### Wave 3 — Science & Discovery (Week 3-4)
```
modules/exoscience.py     — Science missions [R→P] 756 lines
modules/tech_tree.py      — Tech tree [R→P] 300 lines
modules/alchemy.py        — Transmutation [R→P] 484 lines
modules/academy.py        — Crew training [R→P] 391 lines
modules/university.py     — Research [R→P] 460 lines
modules/archaeology.py    — Dig sites [R→P] 338 lines
modules/artifacts.py      — Artifacts [R→P] ~150 lines
modules/celestial.py      — Galaxy/FOW [J→P] 1,091 lines
modules/adventures.py     — Encounters [R→P] 202 lines
modules/mystery.py        — Investigation [J→P] 826 lines
```

### Wave 4 — Intel & Operations (Week 4-5)
```
modules/espionage.py    — Spy ops [R→P] 102 lines
modules/darkops.py      — Black ops [R→P] 106 lines
modules/stealth.py      — Stealth [R→P] 93 lines
modules/disasters.py    — Disasters [R→P] 287 lines
modules/manufacturing.py — Factories [R→P] 364 lines
modules/defense.py      — Defense [R→P] ~150 lines
modules/siege.py        — Sieges [R→P] 173 lines
modules/faction_ai.py   — AI factions [R→P] 458 lines
```

### Wave 5 — Narrative & Media (Week 5-6)
```
modules/narrator.py     — Prose gen [R→P] 105 lines
modules/news.py         — News/opinion [R→P] 406 lines
modules/quest.py        — Quests [R→P] 120 lines
modules/epilogue.py     — Epilogue [R→P] 106 lines
modules/image_gen.py    — Image prompts [R→P] 148 lines
modules/agnes.py        — Agnes AI [R→P] 221 lines
modules/event_catalog.py — Events [R→P] 2,027 lines
core/seed.py            — Seeded RNG [R→P] ~200 lines
core/migration.py       — Migration runner [R→P] ~200 lines
```

### Wave 6 — Infrastructure (Week 6-7)
```
server/app.py           — FastAPI [R→P] 886 lines
server/health.py        — Health check [R→P] ~80 lines
modules/telegram_bot.py — Telegram [R→P] 971 lines
scripts/daemon.py       — Daemon [R→P] 482 lines
scripts/cli.py          — CLI extend [R→P] ~500 lines
core/interpreter.py     — Command parser [R→P] 294 lines
core/metrics.py         — Metrics [R→P] ~100 lines
core/skill_health.py    — Skill testing [R→P] ~220 lines
modules/guardrails.py   — Guardrails [R→P] 408 lines
core/schema.py          — Complete data models
```

---

## Total Effort

| Category | Modules | Lines | Est. Days |
|----------|---------|-------|-----------|
| Core infrastructure | 10 core files | ~2,500 | 5 |
| Rust→Python modules | 28 modules | ~11,000 | 35 |
| JS→Python modules | 9 modules | ~6,750 | 13 |
| Infrastructure | 6 systems | ~3,000 | 11 |
| **Total** | **53 deliverables** | **~23,250 lines** | **~64 days** |

---

## Commands to Port Each Module

```bash
# For each Rust module to port:
cat /home/maya/archive/rp-engine-rust/src/<module>.rs

# For each JS module to port:
cat /home/maya/archive/rp-engine-js-skills/<module>/<file>.js

# Create Python file:
touch /home/maya/Bumi-Hijau/rp-engine-py/modules/<name>.py

# Test module:
cd /home/maya/Bumi-Hijau/rp-engine-py
python3 -c "from core.config import Config; print(Config.summary())"
```

## Success Criteria

- All 72 Rust modules → Python equivalents in `rp-engine-py/modules/`
- All 10 JS modules → Python equivalents
- `core/config.py` controls everything (single file)
- `python3 scripts/cli.py tick` runs all 50+ modules in dependency order
- `python3 scripts/cli.py status` shows complete game state
- FastAPI server at `:8080` replaces Rust `web.rs`
- Pyrogram bot replaces Rust `telegram.rs`
- Zero Rust, zero JS active code — everything archived
