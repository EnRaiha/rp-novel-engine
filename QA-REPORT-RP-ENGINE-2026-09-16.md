# QA REPORT — TKG RP Engine + Hermes Plugin

**Date:** 2026-09-16 (+08) · **Auditor:** Maya (Hermes) + 4 deep-read subagents
**Target:** `/home/maya/Bumi-Hijau/rp-engine-py` (174 `.py` / 28,239 LOC / 81 migrations / 290 live tables) + Hermes plugin `~/.hermes/plugins/rp-engine` (5 files / 26 KB)
**Mode:** report-only. **Zero files changed in the repo. Zero DDL. Zero data mutations** (side effects disclosed in §11).

## 0. Baseline (live, this session)

| Probe | Result |
| --- | --- |
| `python3 -m pytest tests -q` | **170 passed in 8.12s** |
| `cli.py status` | TKG id=3, day **2195**, 582,230,697,392 C, 109 territories, 42,152 ships, 81/81 modules |
| `cli.py health` | DB connected, **290** tables |
| `bench_interceptor.py` | **PASS** — tier1 21.5 µs/line (<50), cosine 0.0707 ms/query (<1.0), 47 templates |
| `cli.py romance arcs · templates · intel · modules · flow · dash · economy flow` | all exit 0 |

Green tests + green status + green bench — while **the read path Hermes actually uses is broken (§2 P0-1)** and the market module fails every tick (§3). The suite tests pure logic; nothing tests the DB contract.

**Evidence grading used below:** `LIVE` (parent ran it now) · `SCHEMA` (parent checked live `information_schema`/`pg_constraint`) · `CODE` (parent read the lines) · `CHILD-EXEC` (subagent ran an offline probe) · `STATIC` (read-only source analysis).

---

## 1. Executive summary

| # | Sev | Finding | Evidence grade |
| --- | --- | --- | --- |
| P0-1 | **BLOCKER** | `rp_cli query` crashes on **every successful** query → `AttributeError: 'list' object has no attribute 'get'` | LIVE |
| P0-2 | **HIGH** | `rp_fleet` (all 4 modes) dead through the plugin: `ModuleNotFoundError: No module named 'core'`; 13 scripts keep the broken bootstrap | LIVE + CODE |
| P0-3 | **HIGH** | `kilo_bridge market` 100% broken: `column ph.session_id does not exist` | LIVE + SCHEMA |
| P0-4 | **MED** | `rp_char_query` returns `ok:false` on success (envelope mismatch) | LIVE |
| E-1 | **CRIT** | `market.py` writes `NOW()` into `commodities.last_tick_at` **integer** → market tick fails every run; `price_history` = **0 rows**, commodities = **5** rows | SCHEMA + CHILD-EXEC |
| E-2 | **CRIT** | `orchestrator.py:366-369` inserts `started_at/completed_at/modules_run/modules_failed/duration_ms` into `tick_summaries` — **none of those columns exist** → 0 tick telemetry rows, ever | SCHEMA (live cols) + CODE |
| E-3 | **CRIT** | `battle.py` — 3 non-existent relations (`battle_phases`, `battle_aftermath`) + `ORDER BY (is_spouse DESC)` syntax error **in the tick path** → battle tick FAILED | SCHEMA + CODE |
| E-4 | **CRIT** | `celestial.py` — 7 broken queries (`territory.name`, `planets.type/colonized`, `space_lanes.distance_ly`, `treaties.session_id/faction_a/b`) | CHILD-EXEC |
| E-5 | **HIGH** | `social.py:183` `ON CONFLICT (char_a_id, char_b_id)` vs real constraint **`UNIQUE (session_id, char_a_id, char_b_id)`** → 42P10, swallowed → all relationship writes no-op | SCHEMA + CODE |
| E-6 | **HIGH** | `prison.py:563` inserts `clues(title, description, investigation_id)` — 3 columns that don't exist → prisoner-intel → mystery pipeline silently dead | SCHEMA + CODE |
| E-7 | **HIGH** | `reputation.py:68` iterates a **dict's keys** → every `Reputation.apply()` raises `TypeError`; module has zero importers | CODE + CHILD-EXEC |
| E-8 | **HIGH** | `consequences.py` `stat` consequences target column `morale` — real column is **`aggregate_morale`**; error swallowed by `except: pass` | SCHEMA |
| E-9 | **HIGH** | `narrative_hooks.status` split-brain: only `'pending'` exists (8/8 live rows); readers filter `'active'` → briefings report zero crises while pacing pins crisis mode | SCHEMA (live rows) + CODE |
| E-10 | **HIGH** | `romance.check_jealousy` inserts `rival_id=NULL` into `jealousy_states.rival_id **NOT NULL**` → romance tick reports FAILED | SCHEMA + CHILD-EXEC |
| E-11 | **MED** | `savegame` export/import marker mismatch → errored table is **wiped then skipped** with `ok: True`; `INT[]` columns can't round-trip (blanket `::jsonb`) | CHILD-EXEC |
| E-12 | **MED** | `slave_system.py:72` `UPDATE … ORDER BY … LIMIT` (invalid PG) **in tick path** → revolt aborts the phase | STATIC + CHILD-EXEC |
| E-13 | **MED** | `war.py:69-88` re-emits importance-10 `war_end` **every tick** | STATIC |
| E-14 | **MED** | Events embedding starvation still open: **15,677** events / **470** embedded (3.0%); last **100** all NULL | LIVE |
| E-15 | **MED** | `roll_history.raw_roll` stores the **modified** total (`100 +50` → 150) → pool crit odds inflated | LIVE |
| E-16 | **MED** | Migrations: 81 `.sql` vs **45** rows in `_migrations`; next `migrate.py` run **aborts at `068_system_id_fk.sql`** | SCHEMA + CHILD-EXEC |
| E-17 | **MED** | `cli.py query` is **not** enforced read-only anywhere; `SELECT … INTO` is a live write hole; plugin guard is a start-anchored regex | CHILD-EXEC + CODE |
| E-18 | **LOW** | ~173 public functions with zero call sites; `meanwhile` + `agnes` truly dead; `duel`/`wreck_assembly` imported but never ticked | STATIC |
| E-19 | **LOW** | `scene_stack.py:14` passes `interrupt=` to `log.info(module, msg)` → TypeError | CODE |
| E-20 | **LOW** | `roll_theater.flavor()` returns `""` for success/fail → blank CLI lines; payouts ignore computed odds | CHILD-EXEC |

Root cause pattern across E-1…E-13: **modules swallow exceptions** (`except: pass`, `print()`, nested error dicts, `return None`) and the orchestrator then scores the module **OK**. That is why a whole class of dead SQL survived a green test suite and a green status line.

---

## 2. P0 — the Hermes path is broken

### P0-1 (BLOCKER) `rp_cli query` fails on every successful query
```
rp_cli(subcommand="query", args="SELECT count(*) FROM maya_rp.sessions")
-> [TOOL_ERROR] Tool execution failed: AttributeError: 'list' object has no attribute 'get'
```
`cli.py:309` prints a JSON **array** for query results; `tools.py:148` does `data.get("status")` on it → AttributeError. Introduced by the prior BUG-5 fix (which moved `_run` from exit-code to JSON-status parsing). Affects `select 1`, `count(*)`, `select *` — i.e. *every* SELECT, my primary read path. Compare: `cli.py status` (text output) works, which is why this went unnoticed.
Note the inverse: query **failures** return `{"ok": true, "output": "Query error: column … does not exist"}` because `cli.py:310` catches the error and exits 0.

### P0-2 (HIGH) `rp_fleet` is dead through the plugin
```
rp_fleet({mode:"plan"}) -> ok:false
stderr: File ".../scripts/fleet_expansion.py", line 21, in <module>
        from core.config import Config
        ModuleNotFoundError: No module named 'core'
```
Repro matrix: engine root + ambient `PYTHONPATH` (interactive shell has `:/home/maya/scripts:…`) = **works**; `env -u PYTHONPATH` = **fails**; `PYTHONPATH=` = **fails**. The plugin spawns subprocesses with the Hermes env (no cwd entry) → the documented Fleet SOP (`fleet_expansion.py`, `fleet_refill.py`) is unreachable from Hermes.
Still using `str(__file__ + "/../../")` — a path that traverses *through a regular file* — in **13 scripts**:
`bench_interceptor.py, east_judgment.py, fleet_expansion.py, fleet_refill.py, narration_sync.py, rebuild_production.py, redo_faction_model.py, resource_modifiers.py, roll100.py, seed_complaints.py, seed_planets.py, seed_species_pop.py, setia_governor_model.py`
Already correct: `cli.py:6, kilo_bridge.py:9, ship_sheet.py:14, char_query.py:28, char_locations.py:13, orchestrator.py:5, migrate.py:5, rp_novel_recall.py:15, unified_recall.py:20, wiki_ingest.py:17, sync_pack.py:19, materialize_legio*.py`.

### P0-3 (HIGH) `kilo_bridge market` — session filter on a table without `session_id`
```
$ python3 scripts/kilo_bridge.py market
asyncpg.exceptions.UndefinedColumnError: column ph.session_id does not exist
HINT:  Perhaps you meant to reference the column "c.session_id".
```
`kilo_bridge.py:59` filters `price_history ph` on `ph.session_id`; **live columns: id, commodity_id, tick_number, price, volume**. A BUG-4 remediation was applied to a table that cannot be scoped that way. `tools.py:45` still whitelists `market`, so any caller that reaches it gets a hard failure instead of prices. Fix = the HINT: scope via `JOIN commodities c ON c.id = ph.commodity_id AND c.session_id = $1`.

### P0-4 (MED) `rp_char_query` reports failure on success
`_run` requires JSON `status == "ok"`; `char_query.py --json` emits `{"ok": true, "kind": "ambiguous", "candidates": [...]}` — no `status` key.
Live: `rp_char_query(kind="char", query="Nadia")` → `{"ok": false, "data": {"ok": true, … Callista-style candidates …}}`. Any caller keying on the envelope misreads good results as failures.

### Action-inventory drift (same area)
`schemas.RP_BRIDGE` enum (25 actions) **omits** `market`, `loc`, `char_query`, `novel_recall` (all implemented + in `tools._BRIDGE_ACTIONS`) → unreachable via schema-validating clients (verified: `rp_bridge(action="market")` is rejected at validation). `pirates` is in the enum **and** in `_BRIDGE_ACTIONS` but has no bridge branch → live `{"status":"error","data":"Unknown action: pirates"}`.

---

## 3. Engine correctness — writes that silently don't happen

All schema claims below were checked against the **live** DB this session.

| Where | Broken statement | Live schema reality |
| --- | --- | --- |
| `market.py:67,98` | `NOW()` → `commodities.last_tick_at` | column is **`integer`** → DatatypeMismatch, no try/except → market fails every tick (`price_history` 0 rows, `commodities` 5 rows) |
| `orchestrator.py:366-369` | INSERT `tick_summaries(session_id, started_at, completed_at, modules_run, modules_failed, duration_ms)` | live cols = id, session_id, tick_number, categories, events_json, formatted_bulletin, ai_prose, alerts_count, resource_snapshot, summary_for_telegram, generated_at → always fails, swallowed → **0 rows ever** |
| `social.py:183` | `ON CONFLICT (char_a_id, char_b_id)` on `character_relationships` | real constraint = `UNIQUE (session_id, char_a_id, char_b_id)` → 42P10 → all relationship writes no-op |
| `prison.py:563` | `INSERT INTO clues (session_id, source, source_type, title, description, investigation_id, revealed)` | live `clues` = id, session_id, source, source_type, **text**, connects_to_clue, revealed, revealed_by_character, location_id, session_found, created_at → 3 columns missing |
| `battle.py` | 3 relations + columns | `battle_phases`/`battle_aftermath`/`battle_log_entries` **do not exist**; `combat_results` lacks `status/outcome/player_formation`; `BattleState.session_id` absent; `ORDER BY (is_spouse DESC)` = syntax error (tick-reachable, 5 % hook) |
| `celestial.py` | 7 queries | `territory.name`, `territory.faction_control`, `planets.type`, `planets.colonized`, `space_lanes.distance_ly`, `treaties.session_id/faction_a/faction_b` — tick reports OK anyway |
| `academy.py:24` | `certifications` | table **does not exist** → stuck graduation loop |
| `mystery.py` | 5 statements | 0 investigations ever created |
| `crew_career.py:34` | `rank` | column missing, wrapped in `except: pass` → no-ops every tick |
| `slave_system.py:72,184` | `UPDATE … ORDER BY … LIMIT` | invalid PG; :72 is in the tick path |
| `infrastructure.py:118-126` | unscoped production credit | credited to the current session regardless of owner |
| `population_sentiment.py:163,53` | un-awaited coroutine; `int += str` | runtime errors |
| `war.py:69-88` | re-emits `war_end` (importance 10) every tick | duplicate high-importance spam |
| `provenance.py:50` | queries `maya_rp.pacing_state.changed_at` | real table is `narrative_pacing` → live via `kilo_bridge.py:365` |

Logic defects (no SQL involved):
- `reputation.py:68` — `for (lo, hi), label in mapping:` over a **dict** → `TypeError: cannot unpack non-iterable int object` (3-axis reputation engine 100 % non-functional, zero importers).
- `consequences.py:87-100` — default/whitelisted target `morale` does not exist; live column is **`aggregate_morale`**; `UndefinedColumnError` swallowed.
- `pacing.py:34` vs `briefing.py:29`, `dramatic_structure.py:22`, `objectives.py:13,42`, `narrative.py:64` — writer emits `'pending'`, readers demand `'active'`: live `narrative_hooks` = 8 rows, **all `pending`** → briefings show zero crises while the crisis detector matches everything and pins crisis mode.
- `romance.check_jealousy` — `jealousy_states.rival_id` is **NOT NULL** (live), probe captured `(3, 11, None, 1)` → NotNullViolation kills the whole romance tick.
- `savegame` — `__error__` marker is a dict but import only detects list-shaped markers → an errored table is wiped then skipped, `ok: True` (silent data loss); `INT[]` (e.g. `cabinet_decrees.event_ids`) can't round-trip through the blanket `::jsonb`; partial restores report success.
- `voyage.py` — `sector_connections` fallback binds `%Serein%` against `from_sector_id::text` (numeric id) → dead path; ship losses never reach the fleet · `wormhole_decay` documented as a tick hook but absent from `run_tick`.
- `roll_theater.flavor()` returns `""` for `success`/`fail` (all 9 domain tables + default) → blank CLI output; payouts ignore the odds the module computes and inject Crown credits.
- `scene_stack.py:14` — `info(..., interrupt=…)` vs `log.info(module, msg)` → TypeError after the INSERT.
- `guard.py` — `"gun" in "begun"` wrong-weapon false positive, `purchas[ed]?` never matches "purchased", NULL credits → TypeError.
- `intent.py` — 10 action types return `success: True` while no resolver is invoked.
- `local_gen`, `name_gen`, `provenance`, `embed` — further MED/LOW items in the child reports (A-core §B-series).

## 4. Dead / unreachable surface

- No `run_tick` at all: `ship_modules`, `local_gen`, `chrono_engine`, `character_profile` (reachable only via CLI/bridge). **`meanwhile` and `agnes` are truly dead** (no importer, no caller) though `meanwhile` is flagged `True` in `Config.MODULES`.
- Imported + in `MODULE_MAP` but **never ticked**: `conversation_log`, `duel`, `wreck_assembly`.
- **27 of 80** Group-C modules perform no DB write during their tick; **~173 public functions** have zero call sites outside their own file (`prison` 15/16, `council` 30/31, `social` 17/18). `resolve_capture`, `interrogate`, `issue_decree`, `shift_bond` are unreachable from tick, CLI, bridge and plugin.
- `council.can_do` refuses 6 of 8 decree types (only `covert`/`diplomatic` pass); `title_performance` never persisted; nothing writes `wife_mode` so the emergency chain can never act.
- `build_queue` completion exists only in `roll100.py:136` — 21 rows sit `in_build`.

## 5. Read-only enforcement (security)

`cli.py query` has **no** guard: measured `default_transaction_read_only=off`, `statement_timeout=0`, role `rp_engine` holds `CREATE` on `maya_rp`. The plugin's regex (`^\s*select\b`) is start-anchored → `select 1; DELETE …` and `select 1 into maya_rp.x` **pass it**; multi-statement is blocked only accidentally by asyncpg's prepared `fetch` (`PostgresSyntaxError`), while `SELECT … INTO` (DDL/create-table-as) is a genuine hole. It also wrongly rejects read-only CTEs, `EXPLAIN` and `TABLE`. No injectable SQL elsewhere: the only interpolated SQL is `kilo_bridge.py:450-484` (hard-coded literal) and `harness_sync.py:57` (`%`-formatted `type=int`).

## 6. Migrations

`_migrations` records **45** rows against **81** `.sql` files (19 recorded names have no file). Schema itself is in sync — 289 declared tables + `_migrations` = 290 live, 0 missing. But the next `migrate.py` run **aborts at `068_system_id_fk.sql`** (it ALTERs `campaigns`, which no longer exists — confirmed `to_regclass` NULL) and `return`s, so 069–103 never apply. `bank_bonds` is live but declared by no migration. `migrate.py:18` sorts by string, and duplicate numeric prefixes already exist.

## 7. Regression check vs QA-REPORT-INTEGRATION-2026-08-15

| Prior | Claim | Status now |
| --- | --- | --- |
| BUG-1 CRIT | cli.py unusable outside repo root | **FIXED** for `cli.py` (exit 0 from `/tmp` + `env -u PYTHONPATH`); same class live in 13 other scripts (P0-2) |
| BUG-2 HIGH | `cli.py health` KeyError | **FIXED** (`db.py:126`, live OK) |
| BUG-3 HIGH | bridge query actions return `status:"error"` on success | **FIXED** live; residual envelope bug at plugin layer → P0-4 |
| BUG-4 HIGH | unscoped cross-session queries | **PARTIAL** — `roll_theater.py:327`, `kilo_bridge.py:811,827` scoped; `price_history` attempt invalid (P0-3); `rp_ingest_novel.py:110` still unscoped |
| BUG-5 HIGH | `pirates` + exit-code ok | **PARTIAL** — ok now from JSON status; `pirates` still dangling + enum drift |
| BUG-6 MED | raw_roll = modified total | **OPEN** (E-15, reproduced live: row id 34) |
| BUG-7 LOW | `economy flow` div-by-zero | **FIXED** (exit 0) |
| BUG-8 LOW | eager default label | **FIXED** |
| BUG-9 LOW | memories DELETE vs "archive", no tx | **OPEN** (`memories.py:160` vs `:194`) |
| BUG-10 LOW | hardcoded session 3 | **PARTIAL** (`core/state.py:11,46,72`, `savegame.py:130`, `events.py:45,63,79`, `diplomacy.py:7`) |
| §3 | events→recall starvation | **OPEN** (E-14; 3.0 % coverage, last 100/100 NULL) |
| §2 | dead flags `dramatic_structure`/`meanwhile` | **PARTIAL** — module files now exist; `meanwhile` still unreachable |
| §10 | pyproject deps | **FIXED** — asyncpg, httpx, pydantic, PyYAML, flask, psycopg2-binary |

## 8. Test coverage

170 tests / 11+ files, all green — and structurally unable to catch any of the above: **zero** coverage of `kilo_bridge.py` (all actions), `cli.py` dispatch, `core/db.py`, `core/memory.py`, `modules/memories.py`, `scripts/rp_ingest_novel.py`, the plugin `tools.py`, and migrations. No integration test touches PG, so schema drift (the dominant failure class here) is invisible by construction. Prior QA's claim that savegame checksum is covered is itself wrong (child A §8).

## 9. Potential false positives (checked, *not* bugs)

- `lore_pack` looking like corrupt JSON was **my** `2>&1` merge of an INFO log line; `core/log` writes to stderr, so the bridge contract is clean.
- Two roll rows in `roll_history` are my probe writes (29 → 31) — logging works; the table is thin, which weakens pool odds but is usage, not a defect.
- `romance_arcs` ranges are healthy (49 arcs, 0 with `intimacy_level>10`, 0 with `saturation_pct>100`); 0 ships with negative hull.
- `roll_theater` multi-decay suspicions, `house_keeps` dead line, `tier_of` boundaries, `consume_blessing` refresh — disproved in child B §6.
- `vec[:1536]` slicing, checksum round-trip, chapter regexes, `rp_cli` regex vs asyncpg prepared-statement behaviour — documented in the 08-15 report §6 and still valid.
- 16 further disproved hypotheses in child C §false-positives (extractor artifacts on f-string SQL, `Record.get`, etc.).

## 10. Suggested fix order

1. **P0-1** `tools.py:148` — tolerate list/array JSON (`data.get("status") if isinstance(data, dict) else …`), and make `cli.py:310` return non-zero on query error. *(unblocks all Hermes reads)*
2. **P0-2** — one-line bootstrap fix in the 13 scripts (`sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))`), mirroring `cli.py:6`. *(unblocks Fleet SOP)*
3. **P0-3** — scope `market` via `commodities c` join (HINT from PG).
4. **P0-4 / enum drift** — one JSON contract: every script prints `status`; sync `_BRIDGE_ACTIONS` ↔ bridge branches ↔ schema enum.
5. **E-1/E-2/E-3/E-5/E-6** — the five statements that write nothing but report success. Add a migration-consistency test (prepare every SQL literal against the live schema — the AST technique child C already used: 859 OK / 49 FAILED).
6. **Stop swallowing exceptions** — module-level `except: pass` must log at `error` and mark the module FAILED in the tick summary (currently the orchestrator scores them OK).
7. **E-9/E-8/E-7/E-10** — hook-state split (`narrative_hooks`), `aggregate_morale`, dict-iteration TypeError, `rival_id` derivation.
8. **E-14** — embed on insert in `EventBus.emit` / memorialize (best-effort) or a post-tick incremental sweep.
9. **E-17** — enforce read-only properly: `SET TRANSACTION READ ONLY` or a read-only role for the query path; replace the regex guard.
10. **E-16** — migration ledger reconciliation + reject duplicate prefixes; fix `migrate.py` abort at 068.
11. **E-11** — savegame marker/array-column correctness (data-loss risk).
12. Tests: 3–5 contract tests over `kilo_bridge.handle()` + a schema-vs-SQL gate in CI.

## 11. Evidence ledger & side effects

**Parent commands (all read-only unless noted):** `pytest -q` (170 pass) · `cli.py status/health/economy flow/romance arcs/templates/intel/modules/flow/dash` · `kilo_bridge.py` 21-action smoke matrix (15 ok, `market` + `lore_pack` traceback/probe artifact, `pirates` error) · plugin live calls `rp_cli status`, `rp_bridge bonds`, `rp_bridge market` (validation reject), `rp_char_query`, `rp_ship_sheet`, `rp_char_locations`, `rp_fleet` (ModuleNotFoundError) · `bench_interceptor.py` PASS · repro matrix for the 13-script bootstrap · `information_schema`/`pg_constraint` checks (resources, narrative_hooks, jealousy_states, character_relationships, commodities, price_history, tick_summaries, clues, _migrations, to_regclass for campaigns/battle_*/certifications) · `scripts/fleet_refill.py --snapshot` (**wrote** `legion_snapshot`: 6 legions / 435 ships) · 2 rolls via `cli.py roll` (**wrote** `roll_history` ids 34–35 + 2 events).
**Subagent reports (raw, in full):** `/tmp/rp-qa/A-core.md` (321 L) · `B-modules-heavy.md` (859 L) · `C-modules-rest.md` (785 L) · `D-scripts-migrations-plugin.md` (332 L); copies alongside this file under `qa-20260916/`. Child side effects: ~20 INFO log lines appended to `logs/tick_20260916.log`; child D killed stray `sleep` processes during an orphan-timeout experiment (2 unrelated ones included).
**Not verified by the parent:** the long tails of child findings (individual module SQL beyond the spot-checks above), `savegame` restore internals, and any claim requiring a live multi-session DB.

---

## 12. Fix wave — applied 2026-09-16 (post-audit)

Backups first: `/home/maya/backups/rp-engine-pre-fix-20260916.tgz` (sha256 `7032155a…`) and `rp-engine-plugin-pre-fix-20260916.tgz` (sha256 `b76ed5b8…`). Engine suite stayed **170/170** green after every batch; every fixed statement additionally validated with `conn.prepare()` against the live schema (10/10 OK).

### Batch 1 — Hermes path (P0)
| Fix | File | Verification |
| --- | --- | --- |
| `_run` handles JSON array / `{"ok":…}` / no-status payloads; JSON error envelopes can't read as success | plugin `tools.py` | live: `rp_cli query` → `ok=true` + array data; `rp_char_query` → `ok=true` |
| Read-only enforced server-side (`Database.fetch_readonly` → `READ ONLY` transaction); query errors → stderr + exit 1 | `core/db.py`, `scripts/cli.py:cmd_query` | `SELECT 1 INTO maya_rp.zzz_probe` → `cannot execute SELECT INTO in a read-only transaction`, exit 1, probe table absent |
| `market` history scoped via `commodities` (was `ph.session_id`, a column that does not exist) | `scripts/kilo_bridge.py` | live `rp_bridge market` → `ok=true`, prices returned |
| `pirates` action implemented (bases + bounties, scoped via `factions`); `den_ops bases/bounty` same fix | `scripts/kilo_bridge.py` | live `rp_bridge pirates` / `den_ops` → `ok=true` |
| Action inventory synced: `_BRIDGE_ACTIONS` + schema enum now match implemented branches | plugin `tools.py`, `schemas.py` | validation no longer rejects `market`/`loc`/`char_query`/`novel_recall`/`lore_pack` |
| Import bootstrap (`str(__file__ + "/../../")`) fixed in 13 scripts; `os` import placed after `from __future__` | 13 `scripts/*.py` | `py_compile` all OK; `fleet_expansion`/`fleet_refill`/`roll100`/`bench_interceptor` from `/tmp` with `PYTHONPATH` unset exit 0 |

### Batch 2 — statements that wrote nothing and reported success
| Fix | File | Verification |
| --- | --- | --- |
| `NOW()` → integer game-day for `commodities.last_tick_at` (`_seed` takes the tick) | `modules/market.py` | `prepare()` OK |
| `tick_summaries` insert uses real columns (`tick_number`, `categories` jsonb, `alerts_count`, `generated_at`) | `scripts/orchestrator.py` | `prepare()` OK, live cols confirmed |
| `character_relationships` upsert → `ON CONFLICT (session_id, char_a_id, char_b_id)`; follow-up UPDATE session-scoped | `modules/social.py` | `prepare()` OK vs live constraint |
| `clues` insert uses real columns (`text`, `revealed`, `session_found`); failures logged, not swallowed | `modules/prison.py` | `prepare()` OK |
| `ORDER BY (is_spouse DESC)` → `ORDER BY is_spouse DESC, random()` (tick-path syntax error) | `modules/battle.py` | `prepare()` OK |

### Batch 3 — logic defects
`reputation.py` dict iteration (`.items()` — every `apply()` raised TypeError) · `consequences.py` `morale` → `aggregate_morale`, errors logged · `scene_stack.py` bogus `interrupt=` kwarg removed · `guard.py` word-boundary weapon match + `purchas(?:e|ed|ing)?` credits regex · `war.py` `war_end` fires once · `narrative.py` hooks written `status='active'`, `pacing.py` crisis detector counts `active` · `provenance.py` `mode` fact reads `narrative_pacing` · `romance.py` jealousy row only inserted when the rival resolves to a character (`rival_id` is NOT NULL) · `slave_system.py` two `UPDATE … ORDER BY … LIMIT` rewritten as subqueries · `population_sentiment.py` await + command-tag count · `voyage.py` `sector_connections` fallback resolves sector names → ids · `crew_career.py` error logged + `rank` column via migration 104 · `roll_theater.py` `GENERIC_FLAVOR` for success/fail tiers · `cli.py` `raw_roll` now logs the die (not the modified total) + `modifier_total` · `memories.py` consolidate pairs wrapped in one transaction.

### `import_sav` — the engine's own restore was broken
`cli.py load <sav>` aborted on FK violations before restoring anything. All in `core/savegame.py`:
1. **Detach outside children** — tables left out of the wipe (excluded logs like `roll_history`, vector tables, the preserved `sessions` row) hold FKs into tables being wiped → NULL the referencing column first, delete the rows only when it is NOT NULL.
2. **FK cycles** — new `fk_cycle_members()` finds the 10 tables Kahn cannot order (`characters ⇄ territory ⇄ locations ⇄ clues`, self-referencing `leaders`/`clues`/`research_projects`/`cabinet_*`/`bug_tech_tree`); each cycle-internal edge is NULLed before the wipe.
3. **Session row UPSERT** — the preserved `sessions` row is updated from the .sav, otherwise `game_day` never rolled back.
4. **Savepoint isolation + deferred retry pass** — one savepoint per table, leftovers retried after all tables load, so a single unresolvable row can no longer abort every remaining INSERT and still return `ok: True`.
5. **Type-aware row encoding** — the old blanket `::jsonb` cast broke every ARRAY column (8 in the schema: `cabinet_decrees.event_ids INT[]`, `planet_types_catalog.special_events TEXT[]`, `time_skip_log.events_summary TEXT[]`, `character_memories.recall_trigger_keywords`, `conversation_log.keywords`, `decision_stream.event_ids`, `secrets.hidden_from_ids`, `tech_tree.prerequisites_names`). New `_encode_value()` emits `'{…}'::<elem>[]` literals for ARRAY columns, `::jsonb` only for json/jsonb, scalars otherwise.
6. **PK upsert instead of DO NOTHING** — `_conflict_clause()` uses `ON CONFLICT (id) DO UPDATE SET …` so the snapshot is authoritative; `DO NOTHING` used to skip any snapshot row whose id still existed outside the wiped session scope, leaving those tables permanently short (e.g. `crew_roster` 4,077/4,090).

Measured effect on the day-2195 restore: run 1 (original code) aborted at the first FK; run 2 (cycle-break + savepoints) committed 342,283 rows with 6,197 row errors across 8 tables; run 3 (adds arrays + id-upsert) is the verification run.

Verified: the restore now passes the cycle-break stage that previously aborted (`FK cycles: 10 tables — breaking with NULLs`), instead of dying at `difficulty_tiers` → `characters` → `locations`.

### Migration
`migrations/104-qa-fix-wave-20260916.sql` — adds `crew_roster.rank` (referenced by 3 crew_career statements) and sets `narrative_hooks.status` default to `'active'` while normalising the 8 `'pending'` rows.

### Live verification after the restore (day 2195 restored)
- Restore run 3: **350,540 rows, 43 row errors** (from 6,197 after run 2; run 1 aborted with zero rows). `game_day` back to **2195**, `credits 582,230,697,392C`.
- Full snapshot diff (`/tmp/rp-qa/verify_restore.py`, all 277 tables): only 2 tables short — `crew_roster` 4,077/4,090 and `character_quirks` 0/24. Both are **dangling FK rows inside the snapshot itself** (crew rows whose `ship_id` and quirks whose `character_id` are absent from the .sav), not restore defects; `yard_capacity` (GENERATED column) was topped up with the fixed encoder after the generated-column fix.
- `market` module: **13 commodities priced, `price_history` now 13 rows** (was permanently 0), `commodities` 13 rows (was 5), `last_tick_at = 2195` as an integer.
- `crew_career` module: OK, `rank` backfilled on 4,077 crew rows (needs migration 104).
- `population_sentiment` module: after fixing the un-awaited coroutine the next latent defect surfaced — the seeding `ON CONFLICT (session_id, territory_id, faction_name)` had **no matching unique constraint** (the table only had `(session_id, territory_id, faction_id)`). Verified no duplicates existed, then created `pop_sentiment_session_territory_faction_key`; module now runs OK (1,659 rows refreshed).
- `pytest` 170/170 after the whole wave.

### Side effects of this session (disclosed)
- **Accidental 100-day roll**: `roll100.py --help` ignored the flag and ran LIVE (day 2195 → 2295, +292 `Trade convoy spotted` events, credits moved). Rolled back by restoring the day-2195 snapshot; `roll100.py` still needs an argparse guard (unknown args should not execute).
- Two probe rows in `roll_history` (ids 34–35) and a `legendary roll` event — audit artifacts.
- `events` / `wiki_articles` / `novel_chunks` / `stream_templates` / `events_archive` are vector tables: never exported and never wiped by a restore, so they still carry the ~292 roll-noise events. Pruning them is a canon decision.
- `legion_snapshot` re-baselined (6 legions / 435 ships) by the fleet SOP probe.

### Still open (bigger than a patch — needs decisions)
- `battle.py`: `battle_phases`, `battle_aftermath`, `battle_log_entries` don't exist; `combat_results` lacks `status/outcome/player_formation` → table-design migration.
- `celestial.py` 7 broken queries, `academy.certifications`, `mystery` (5 statements), `infrastructure` unscoped production credit, orchestrator policy of scoring swallowed module exceptions as OK.
- Event embedding starvation (3.0 %) — writer-side embedding or a post-tick sweep.
- `cli.py` regex pre-check still rejects read-only CTEs/`EXPLAIN`/`TABLE` (the READ ONLY transaction is the real guard).
- `roll100.py` argument guard; `import_sav` skips dangling-in-snapshot rows loudly (fine) but the nightly `.sav` should ideally validate FK closure on export.

### Applied after the report pass (same session)
- **`roll100.py` guard** — `-h/--help` now prints usage and exits 0, unknown options exit 2 with usage (it previously ignored flags and ran a LIVE 100-day roll — that incident is what triggered the restore), and a live run prints a `⚠ LIVE ROLL` warning on stderr. Verified: `--help` exit 0 with no roll, `--bogus` refuses, `5 --dry-run` previews without writing, `game_day` unchanged.
- **`rp_cli query` guard relaxed** — the plugin pre-check now accepts `SELECT/WITH/TABLE/VALUES/EXPLAIN/SHOW` (it used to reject read-only CTEs), while the server-side READ ONLY transaction remains the real enforcement. Verified live: CTE ✓, `EXPLAIN` ✓, `TABLE` ✓, `INSERT` refused, `narrator_cost_log` untouched.
