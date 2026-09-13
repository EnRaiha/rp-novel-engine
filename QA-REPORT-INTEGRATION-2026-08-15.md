# QA Report: rp-engine-py — Integration Readiness (external AI writing workbench)

**Date:** 2026-08-15 | **Auditor:** Hermes subagent (static analysis)
**Target:** `/home/maya/Bumi-Hijau/rp-engine-py` — TKG RP engine, 24,828 LOC Python, Postgres (maya_rp schema), Python 3.13 (conda), asyncpg, local Ollama (GTX 1060)
**Focus:** Integration-readiness with external desktop AI writing app (Writingway: PyQt5+langchain, 8 LLM providers, faiss RAG, JSON compendium)
**Method:** Tight-scope read-only analysis + import-behavior probes. **No pytest run. No manual PG queries.** (Two incidental read-only bridge calls executed by the scripts themselves during import probes; reported in ledger.)
**Previous QA (2026-08-14) already fixed:** savegame rewrite, dead-pool reconnect, roll_history persistence, migrations 083–093. Baseline: 103 tests passing.

---

## TL;DR — Top 10 findings by severity

| #   | Sev      | Finding                                                                                                                                                                                                                                                                                                                                                                                               | Evidence                                                                             |
| --- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| 1   | **CRIT** | `scripts/cli.py` entry point is CWD- AND environment-dependent: import hack `str(__file__ + "/../../")` (path through a _file_) only works when the ambient `PYTHONPATH` supplies an empty entry (=cwd). Fails from any other cwd AND with `PYTHONPATH` unset even from repo root.                                                                                                                    | cli.py:4; probes: `/tmp`→fail, `/home/maya`→fail, repo-root+`env -u PYTHONPATH`→fail |
| 2   | **HIGH** | `cli.py health` always crashes: `status['connected']` (cli.py:31) vs `Database.status()` which returns `{tables, session}` only (db.py:111–124).                                                                                                                                                                                                                                                      | cli.py:31; db.py:124                                                                 |
| 3   | **HIGH** | Bridge actions `loc`, `char_query`, `novel_recall` never set `result["status"]="ok"` — successful calls return `status:"error"` (default at kilo_bridge.py:17). Any caller keying on `status` misreads success as failure.                                                                                                                                                                            | kilo_bridge.py:50–74                                                                 |
| 4   | **HIGH** | Cross-session data leakage in bridge/roll queries: `price_history` (kilo_bridge.py:43–46 — no session filter, `sid` never bound), `roll_history` crit-rate (roll_theater.py:209–211), `pirate_bases`/`pirate_bounties` (kilo_bridge.py:533–552), `novel_chunks` delete (rp_ingest_novel.py:110). Latent in single-session deployment; wrong data in any shared/multi-session DB.                      | multiple                                                                             |
| 5   | **HIGH** | Plugin/bridge contract mismatch: tools.py whitelists `"pirates"` (tools.py:66) but kilo_bridge has no such action (→ `Unknown action: pirates`, kilo_bridge.py:562); `_run()` reports `ok` from **exit code** not JSON `status` (tools.py:139–145) → silent false-success. Reverse gap: bridge actions `market`/`loc`/`char_query`/`novel_recall` not whitelisted.                                    | tools.py:66,139–145; kilo_bridge.py:561–562                                          |
| 6   | **HIGH** | Events are **never embedded in normal operation**: `core.memory.store_event` has exactly one caller — `scripts/embed_all.py` (manual script). All event writers (`modules/narrative.py:14–16`, `modules/roll_theater.py:157–161`, `core/events.py:36–42`) insert rows with `embedding IS NULL` → `memory.recall` (bridge action `memory`) returns nothing until someone manually runs `embed_all.py`. | grep store_event; narrative.py:14; events.py:36                                      |
| 7   | **MED**  | Character memory system (`modules/memories.py`) is unwired on **both ends**: zero in-repo callers of `store()`; the only reader (`cmd_memory_surface`) is not in cli.py's dispatch; recall is LIKE-keyword only (no vectors).                                                                                                                                                                         | grep; memories.py:37,87; cli.py:892–949                                              |
| 8   | **MED**  | Hardcoded session/faction literals: `rp_ingest_novel.py:124` (`3` bypassing Config), `savegame.py:130` (`session_id: int = 3`), `core/events.py:39` (`data.get("session_id", 3)`), `kilo_bridge.py:555` (`claim_bounty(sid, 6)`).                                                                                                                                                                     | multiple                                                                             |
| 9   | **MED**  | Dead config flags: `"dramatic_structure": True`, `"meanwhile": True` (config.py:89–90) — no module file, not in `MODULE_MAP` (orchestrator.py:393–427), no imports anywhere. Claimed-enabled, never executed.                                                                                                                                                                                         | grep                                                                                 |
| 10  | **MED**  | `pyproject.toml` declares only `asyncpg` (pyproject.toml:10) — `httpx` (used by core/memory.py:25, modules/local_gen.py:43, memories.py:139) is undeclared → fresh `pip install -e .` breaks embedding/generation.                                                                                                                                                                                    | pyproject.toml; memory.py:25                                                         |

---

## 1. Confirmed bugs (file:line evidence)

### BUG-1 (CRIT) — `scripts/cli.py` import bootstrap is broken; works only via ambient PYTHONPATH

`scripts/cli.py:4`:

```python
sys.path.insert(0, str(__file__ + "/../../"))
```

`__file__` is the _file path_ (`scripts/cli.py`), so the entry is `scripts/cli.py/../../` — a path that traverses **through a regular file**. The kernel returns ENOTDIR; the import machinery silently skips the entry. Imports of `core.*`/`scripts.orchestrator` then succeed **only** because the ambient environment has `PYTHONPATH=:/home/maya/scripts:…` — a leading empty entry that resolves to CWD (verified: with `PYTHONPATH` unset the repo-root entry vanishes from `sys.path`).
**Empirical proof (three independent probes):**

- `python3 scripts/cli.py config` from repo root → **works** (exit 0)
- `python3 /home/maya/Bumi-Hijau/rp-engine-py/scripts/cli.py config` from `/tmp` → `ModuleNotFoundError: No module named 'core'`
- `cd /home/maya && python3 Bumi-Hijau/rp-engine-py/scripts/cli.py config` → `ModuleNotFoundError`
- `env -u PYTHONPATH python3 scripts/cli.py config` from repo root → `ModuleNotFoundError`
  Correct fix: `sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))` (exactly what kilo_bridge.py:7 does — and the bridge **works** from `/tmp` with absolute path, with and without PYTHONPATH; verified).

### BUG-2 (HIGH) — `cli.py health` always crashes with KeyError

`scripts/cli.py:31` reads `status['connected']`, but `core/db.py:111–124` `Database.status()` returns only `{"tables": …, "session": …}` — there is no `"connected"` key. `python3 scripts/cli.py health` (when reachable) raises `KeyError: 'connected'` → traceback → exit non-zero. Diagnostic command is broken.

### BUG-3 (HIGH) — bridge actions `loc`, `char_query`, `novel_recall` return `status:"error"` on success

`kilo_bridge.py:17` initializes `result = {"action":…, "status": "error", …}`. Every branch sets `result["status"] = "ok"` **except** the three query actions (lines 50–55, 57–68, 70–74), which set only `result["data"]`. Callers that gate on `status == "ok"` (the documented bridge contract, kilo_bridge.py:4) treat successful results as failures. Also: `import asyncio as _a` (line 53) is dead.

### BUG-4 (HIGH) — unscoped / cross-session queries (single-session-safe today, wrong in any shared DB)

- `kilo_bridge.py:43–46` (`market`): `SELECT … FROM maya_rp.price_history ph JOIN maya_rp.commodities c ON c.id=ph.commodity_id ORDER BY ph.id DESC LIMIT 13` — **no `session_id` filter and no `$` placeholder for `sid`**; returns the 13 most recent ticks across _all_ sessions, joined to commodities without session scoping.
- `modules/roll_theater.py:209–211` (`open_pool`): `SELECT raw_roll, dc FROM maya_rp.roll_history ORDER BY id DESC LIMIT 50` — no `WHERE session_id`; pool odds computed from every session's rolls.
- `kilo_bridge.py:533–537` (`den_ops bases`) and `:547–552` (`bounty`): no `session_id` filter.
- `scripts/rp_ingest_novel.py:110`: `DELETE FROM maya_rp.novel_chunks WHERE book=$1` — no session filter; re-ingesting book N in any session wipes book N's chunks for all sessions.

### BUG-5 (MED) — plugin bridge contract: `pirates` whitelisted but unimplemented; success keyed on exit code

`~/.hermes/plugins/rp-engine/tools.py:66` whitelists `"pirates"`; `kilo_bridge.py` has no `pirates` branch → `else: result["data"] = f"Unknown action: {action}"` (line 562), status stays `"error"`, but process exits 0. `tools.py:139–145` maps `ok = proc.returncode == 0` from the **exit code**, not the JSON `status` → `rp_bridge({"action":"pirates"})` returns `ok: True` with an error payload. Reverse: bridge implements `market`/`loc`/`char_query`/`novel_recall` (kilo_bridge.py:39–74) which are absent from `_BRIDGE_ACTIONS` and therefore unreachable through the plugin.

### BUG-6 (MED) — raw_roll semantics inconsistent between writer and odds reader

`cli.py:447–453` logs `raw_roll = total` (the **modified** total, e.g. 100+50=150) into `roll_history`, while `roll_theater.py:211` interprets `raw_roll >= 96` as a crit for pool odds. Modified totals inflate crit rates (a `60 +50` roll logs as 110). Telegram path (cli.py:373) has the same issue.

### BUG-7 (LOW) — `cmd_economy_flow` division-by-zero

`cli.py:113`: `SELECT COALESCE(SUM(hull_current/speed),0) FROM maya_rp.ships WHERE …` — any active ship with `speed = 0` raises a PG division-by-zero error and crashes the command (no try/except around it).

### BUG-8 (LOW) — `save` action evaluates default label eagerly

`kilo_bridge.py:185`: `params.get("label", f"… {await Database.fetchval(…)}")` — the default expression is evaluated **even when `label` is supplied**, adding an unconditional DB round-trip per save.

### BUG-9 (LOW) — `modules/memories.py` consolidation deletes originals despite "archive" docstring; no transaction

Docstring `memories.py:161` says "archive the originals"; code `memories.py:193–195` executes `DELETE FROM … WHERE id = ANY($1::int[])`. Irreversible loss of granular memories (gist survives). Insert+delete per character (lines 188–195) are not wrapped in a transaction — a crash between them leaves a duplicated summary or orphaned originals.

### BUG-10 (LOW) — `rp_ingest_novel.py` bypasses Config.SESSION_ID

`rp_ingest_novel.py:124`: `VALUES ($1,…)` bound with literal `3` — if `Config.SESSION_ID` changes, ingestion still writes session 3. Same class: `savegame.py:130` (`session_id: int = 3`), `core/events.py:39` (`data.get("session_id", 3)`).

---

## 2. Missing / partially implemented systems

- **`core/engine.py` does not exist** (task premise confirmed). Engine entry is `scripts/cli.py` → `scripts/orchestrator.py run_full_tick` / `MODULE_MAP`. `modules/events.py` also does not exist — events live in `core/events.py` (EventBus) + `modules/encounters.py` (mapped under the `"events"` flag, orchestrator.py:402).
- **`local_gen.FAST_MODEL` is documented but unwired** (`modules/local_gen.py:12,25` — "fast fallback"). Grep: only the definition references it; `generate()` (line 35) has no fallback path. If the 8B model is absent/OOMs, generation raises instead of falling back.
- **Events embedding**: `core/memory.store_event` exists and works, but is only invoked by `scripts/embed_all.py` (manual). No automatic path embeds new events (see §3).
- **`get_or_create_system_lore`**: the "create" half now exists (kilo_bridge.py:402–413, comment admits it previously never did) — resolved, but the placeholder row it writes (`content = "System lore placeholder…"`) will rank in future semantic searches with a plausible-looking stub.
- **`cli.py` dispatch vs defined commands**: `cmd_memory_surface` (modules/memories.py:87) is defined but never dispatched (cli.py:892–949); usage strings lag the real command set (e.g. `voyage`, `sentiment`, `king`, `adjutant` missing from cli.py:894).
- **Packaging**: `pyproject.toml` declares only `asyncpg`; `httpx` (core/memory.py:25, modules/local_gen.py:43, modules/memories.py:139) and `pytest-asyncio` (used by pyproject `asyncio_mode`) are undeclared.

## 3. Unwired data pipelines (writer no reader / reader no writer)

| Pipeline                                       | Writers                                                                          | Readers                                                        | Status                                                                                                                                                                                                   |
| ---------------------------------------------- | -------------------------------------------------------------------------------- | -------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `events.embedding` → semantic recall           | `narrative.py:14`, `roll_theater.py:157`, `core/events.py:36`, dozens of modules | `core.memory.recall` (bridge `memory`, kilo_bridge.py:172–177) | **Broken link**: writers never embed; reader requires `embedding IS NOT NULL` (memory.py:51). Only manual `scripts/embed_all.py` bridges. `EventBus.emit` (events.py:36–42) also writes unembedded rows. |
| `character_memories`                           | **none in repo** (`memories.store` has zero callers in scripts/modules/core)     | `cmd_memory_surface` (not dispatched)                          | Unwired both ends in-engine; only the tick's expiry runs (orchestrator.py:284). Presumably written externally (Kilo/SQL).                                                                                |
| `roll_hall` / roll events                      | roll_theater.py:154–161 (importance=4, no embedding)                             | `cli.py roll hall` only                                        | Roll events invisible to semantic recall; no reader in bridge.                                                                                                                                           |
| `stream_templates.trigger_tag_embed`           | `cli.py templates embed` / `local_gen.upsert_template`                           | `core/stream_interceptor` (semantic tier)                      | Wired, but only for rows whose embed is NULL (cli.py:463) — embeds happen on demand, not on insert.                                                                                                      |
| Config flags `dramatic_structure`, `meanwhile` | —                                                                                | —                                                              | No writer, no reader, no module. Dead flags.                                                                                                                                                             |
| `roll_pools`/`pool_bets`                       | cli.py roll flow + roll_theater                                                  | `resolve_pool` on next vs-roll                                 | Complete via CLI; not in tick/bridge. Design choice, not a bug.                                                                                                                                          |

## 4. Performance / resource concerns

- **Global Ollama serialization** (`core/memory.py:16`): one `asyncio.Lock` for all embeddings on the GTX 1060 — deliberate (documented), but novel ingestion (rp_ingest_novel) of a whole book = hundreds of serialized ~50 ms+ calls; bulk workbench ingestion will be slow.
- **`ORDER BY RANDOM()`** full-table scans: `kilo_bridge.get_ambient_lore` (kilo_bridge.py:420–439) over `wiki_articles`.
- **Savegame restore is per-row f-string INSERTs** (savegame.py:263–265) — thousands of round-trips inside one transaction (crew_roster alone is 4,090 rows per the QA note at savegame.py:20). Slow but atomic.
- **`db.py` pool**: no `max_inactive_connection_lifetime`/statement-cache tuning; `max_size=15` (config.py:26) per-pool; each kilo_bridge invocation opens+closes the pool (kilo_bridge.py:15,569) — pool churn per call is cheap after first init, fine.
- **`core/log.py:19–26`**: per-day file handler, no rotation — unbounded growth within a day.
- **`kilo_bridge.save`**: unconditional extra `fetchval` per save (BUG-8).
- **`cli.py` subprocess delegation** (roll100/schema/sync-pack, cli.py:597–670) spawns fresh interpreters with relative paths (see BUG-1 class).

## 5. Reliability issues

1. **Entry-point fragility (BUG-1)** — engine reachable only under specific CWD+env; a systemd/desktop wrapper or workbench that doesn't replicate `cwd=ENGINE_DIR` + PYTHONPATH fails at import with a confusing `ModuleNotFoundError: core`.
2. **`Database.status()` / `transaction()` bypass the reconnect wrapper** (db.py:90–124 vs 60–71): a dead pool raises `ConnectionDoesNotExistError` in `status()` instead of reconnecting — inconsistent with `_run()`'s QA-fixed behavior.
3. **Migration ordering by string sort with duplicate numbers** (`scripts/migrate.py:18`: `sorted(mig_dir.glob("*.sql"))`): duplicates exist — 083 (crew-expansion vs events-ships-indexes), 084, 085, 086, 087, 088, 089, 090, 091, 092 (integration-fill / third-ship / 092b-third-ship-ships), 093 (eden-register / roll-theater). Order is ASCII-collation-dependent (`068-faction… < 068_system_id_fk < 068b_backfill…`). Highest migration: **097-adjutant-prompts.sql** (74 items in dir incl. seeds). Fragile for any new migration touching FK'd tables.
4. **Hardcoded DSN + password in source** (config.py:21–24, self-acknowledged "Roast me for hardcoding"): single-user Tailscale tradeoff; an external workbench cannot repoint the DB without editing source. Any future credential rotation = source edit + redeploy.
5. **Cross-session queries** (BUG-4) — data correctness hazard the moment the DB hosts >1 session.
6. **Checksum mismatch proceeds with a warning only** (savegame.py:208–210) — by design (documented), but restore-on-corrupt-save is possible.
7. **`savegame.import_sav` SQL assembly**: column names come from the .sav file, double-quoted (savegame.py:247); a crafted name containing `"` breaks out of the identifier. Values are quote-doubled/`::jsonb`-cast (safe-ish). Supply-chain risk only for untrusted .sav files.
8. **cli.py `status` uses unqualified table names** (cli.py:15–19: `sessions`, `resources`, `territory`, `victory_tracking`) — works only because the DSN sets `search_path=maya_rp,public` (config.py:22–23). Any caller connecting with a different DSN breaks silently at SQL level.

## 6. Potential false positives (look broken but fine)

- **`modules/events.py` missing / config flags `events`, `calendar`, `consequences`, `pacing` without module files** — NOT bugs: `MODULE_MAP` routes them to `encounters`, `calendar_tkg`, `core.consequences`, `core.pacing` (orchestrator.py:402,414,417,305). Only `dramatic_structure`/`meanwhile` are genuinely dead (BUG-9/§2).
- **`vec[:1536]` slices** (memory.py:38,48) vs `vector(768)` casts — benign for current models (nomic 768, bge-m3 1024 both ≤1536) but silently truncates any future >1536-dim model before the PG cast fails. Latent, not live.
- **`rp_cli query` SELECT-only guard is start-anchored** (tools.py:189–200) — a query like `SELECT 1; DROP TABLE x` passes the regex, but `cli.py cmd_query` uses `Database.fetch` (asyncpg prepared statement) which rejects multi-statement strings → safe in practice.
- **Chapter/PART regexes in rp_ingest_novel.py:31–33** — verified against real files: `book-01-the-awakening.md` uses `## Chapter 1: …` headings, which `^##\s+Chapter` matches. Works.
- **`roll_theater.py:255` residual `house_keeps` math** — always adds 0 (paid ≥ winning bets at 1.8×), dead line, not a bug.
- **Savegame checksum verify** — functional: hash computed pre-checksum-insertion (savegame.py:165–166) round-trips byte-identically through `json.loads`→`json.dumps(indent=1)` (key order preserved) — verified by reading, not running.
- **`tier_of` thresholds** (roll_theater.py:20–30): crit at ≥96 or +30 over DC, fumble at ≤5 or −40 under — intentional relative-to-DC design, not an off-by-one.
- **`consume_blessing` refresh logic** (roll_theater.py:175–192) — verified: charges 1→0 after 30-day refresh, `last_used_game_day` NULL-safe via −999 sentinel.
- **kilo_bridge `write_lore` uses `ON CONFLICT (session_id,title)`** — requires that unique constraint to exist; migration 062 (wiki-unique-title) covers it; failure path returns the error string (kilo_bridge.py:341–342) rather than crashing.

## 7. Reproduction conditions

- **BUG-1**: (a) any cwd ≠ repo root + absolute script path → `ModuleNotFoundError: core`; (b) repo root but `env -u PYTHONPATH` → same. Both reproduced 2026-08-15 (see ledger). Any fresh shell/desktop launcher/systemd unit lacking the interactive shell's PYTHONPATH hits this.
- **BUG-2**: `python3 scripts/cli.py health` with DB reachable → `KeyError: 'connected'`.
- **BUG-3**: `python3 scripts/kilo_bridge.py loc '{"query":"…"}'` → JSON `status:"error"` with populated `data`.
- **BUG-4**: `market` with ≥2 sessions having price history → latest 13 ticks mix sessions; `pool open` after rolls in another session → odds include foreign rolls.
- **BUG-5**: `rp_bridge({"action":"pirates"})` → `ok:True`, `data.status:"error"`.
- **BUG-6**: roll `60 +50 vs 90` → `roll_history.raw_roll=110`, counted as crit by `open_pool` odds.
- **BUG-7**: any active ship with `speed=0` (e.g. newly created ships before stats set) → `flow` crashes.
- **Events-recall starvation (§3)**: run bridge `memory` query after a fresh event (e.g. any roll) without ever running `scripts/embed_all.py` → empty `data` despite recent events.

## 8. Test coverage summary (static count, not run)

- **11 test files, 103 test functions** (`grep -cE "def test_"` per file; matches the known 103-passing baseline). 717 lines total.
- Per-file: config 7 · context_sentinel 10 · local_gen 4 · pregnancy 5 · prison 6 · roll_theater 6 · romance_playbook 22 · romance 12 · savegame 7 · stream_interceptor 14 · tick_paths 10.
- **Covered areas**: pure logic — tier/odds math, blessings, flavor; romance intent/thresholds/milestones; savegame pure helpers (classify/fk order/checksum); stream interceptor expansion/interpolation; config flags; pregnancy/prison constants; tick dispatch paths (mocked).
- **Zero coverage**: `kilo_bridge.py` (all 28 actions), `core/db.py`, `core/memory.py`/`core/embed.py`, `modules/memories.py`, `modules/narrative.py`, `modules/local_gen.generate` (only 4 tests), `scripts/rp_ingest_novel.py`, `scripts/cli.py` dispatch, plugin `tools.py`, migrations. No integration tests against PG; no tests for the bridge JSON contract (which is exactly where BUG-3/5 live).

## 9. Suggested fixes (priority order)

1. **Fix the import bootstrap** (BUG-1): `scripts/cli.py:4` → `sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))`. Audit all `scripts/*.py` for the same `__file__ + "/.."` string-concat pattern (`grep -rn '__file__ *+' scripts/`).
2. **`cli.py:31`**: drop `status['connected']` (or add the key in `db.status()`).
3. **Bridge status contract**: set `result["status"] = "ok"` in the `loc`/`char_query`/`novel_recall` branches; make plugin `_run` parse the JSON `status` field instead of exit code; sync `_BRIDGE_ACTIONS` with implemented actions (add market/loc/char_query/novel_recall, remove `pirates` or implement it).
4. **Session-scope every query** (BUG-4): add `session_id` filters to kilo_bridge market-history/den queries, roll_theater pool odds, rp_ingest_novel delete; replace literal `3` with `Config.SESSION_ID` (rp_ingest_novel.py:124, savegame.py:130, events.py:39, kilo_bridge.py:555).
5. **Wire event embedding**: embed on insert in `EventBus.emit`/`_story_entry`/`memorialize` (best-effort, non-blocking — mirror `store_event`'s try/except), or add a post-tick incremental embed sweep so `memory.recall` stops being starved.
6. **Character memories**: add a bridge action (`memory_char`) using `modules.memories.recall`, or document the table as externally-managed; fix the consolidate DELETE-vs-archive mismatch and wrap per-character ops in a transaction.
7. **Migration hygiene**: enforce unique numeric prefixes (reject duplicates in `migrate.py`); document 068/068b/092/092b ordering intent.
8. **Packaging**: add `httpx` (and `pytest-asyncio` as dev dep) to pyproject; consider `python-dotenv`/env override for DSN so the workbench can point at a different DB without source edits.
9. **`local_gen.generate`**: implement the documented FAST_MODEL fallback on connection/model errors; fix `_strip_think`'s `/\w+` regex mangling "and/or"-style text (local_gen.py:31).
10. **Add contract tests**: 3–5 pytest tests over `kilo_bridge.handle()` with a stubbed Database (assert `status=="ok"` for all 28 actions, session-scoping of queries) — would have caught BUG-3/4/5.

## 10. Evidence ledger

**Files read (all in-scope):**

- `scripts/kilo_bridge.py` (582 lines, full) · `scripts/cli.py` (949, full) · `core/db.py` (124, full) · `core/config.py` (137, full) · `core/log.py` (35, full) · `core/memory.py` (62, full) · `core/embed.py` (21, full) · `core/savegame.py` (277, full) · `core/events.py` (44, full) · `modules/roll_theater.py` (305, full) · `modules/local_gen.py` (116, full) · `modules/narrative.py` (79, full) · `modules/memories.py` (204, full) · `scripts/rp_ingest_novel.py` (139, full) · `~/.hermes/plugins/rp-engine/tools.py` (383, full) · `scripts/orchestrator.py` (lines 390–435 only — MODULE_MAP + tick refs) · `scripts/migrate.py` (line 18 only) · `pyproject.toml` (full) · `migrations/` (directory listing, 74 items, max **097**)
- **Explicitly absent** (verified): `cli.py` at repo root, `modules/events.py`, `core/engine.py`, `rp_ingest_novel.py` at root (it is `scripts/rp_ingest_novel.py`).

**Commands run (all read-only probes; no pytest, no manual PG writes):**

1. `wc -l` inventory of scope files; `ls migrations/ | sort -V` (max 097); repo-wide LOC = 24,828
2. Config-flag vs module-file audit (Python one-liner; 82 flags, 6 without module files)
3. `python3 scripts/cli.py config` from repo root → OK (exit 0)
4. `cd /tmp && python3 …/scripts/cli.py config` → ModuleNotFoundError (BUG-1 repro)
5. `cd /home/maya && python3 Bumi-Hijau/…/cli.py config` → ModuleNotFoundError (BUG-1 repro)
6. `env -u PYTHONPATH python3 scripts/cli.py config` from repo root → ModuleNotFoundError (BUG-1 repro, env-dependence)
7. `sys.path` dumps via throwaway `scripts/_dbg.py`/`_dbg2.py` (deleted) — normal vs `env -u PYTHONPATH`; confirms PYTHONPATH empty-entry mechanism
8. `cd /tmp && timeout 12 python3 …/kilo_bridge.py status` → `{"status":"ok", …game_day 2096…}` (import-robustness proof; incidental read-only live call, script's own behavior)
9. `cd /tmp && env -u PYTHONPATH python3 …/kilo_bridge.py bonds` → OK (bridge immune to both CWD and PYTHONPATH)
10. Greps: `FAST_MODEL` (1 hit, definition only), `store_event` callers (1 hit: embed*all.py), `embed_all` refs, `dramatic_structure|meanwhile` (config + gen_wiki_source only), `memories.*` importers (cli.py:531 only), `def test*`counts per test file (103 total),`sorted(mig_dir.glob` (migrate.py:18)
11. Novel-format check: `head -25 book-01-the-awakening.md` — `## Chapter N:` headings match ingest regexes

**Not verified (honest limits):** no live-DB state assertions beyond the two incidental bridge reads; `core/stream_interceptor.py`, `core/state.py`, `core/guard.py`, `core/context_sentinel.py`, `scripts/orchestrator.py` tick body, `scripts/char_query.py`, `rp_novel_recall` module, and all other modules were **not** read (out of scope). Claims about them are limited to what grep/callers show.

---

## Appendix — Integration-readiness map for the external workbench (Writingway)

- **Robust entry point: `scripts/kilo_bridge.py`** — one JSON-in/JSON-out process per call; works from any cwd with absolute path (`python3 /abs/scripts/kilo_bridge.py <action> '<json>'`); needs `cwd` only for relative invocation. **Do not** drive the engine through `scripts/cli.py` until BUG-1 is fixed.
- **Lore storage**: `maya_rp.wiki_articles` — 768-dim pgvector, session-scoped, timeline-aware (`is_procedural`, `recorded_at_game_day`, `relevance_end_day`); API = `get_lore` / `write_lore` / `get_ambient_lore` / `get_or_create_system_lore` / `check_physics`. JSON compendium in the workbench maps 1:1 to this table (export via `SELECT` or a future bridge action).
- **RAG**: `maya_rp.novel_chunks` (book/part/chapter, 768-dim) via `scripts/rp_novel_recall.py`; bridge action `novel_recall` exists but is **not** whitelisted in the plugin (BUG-5) and currently reports `status:"error"` even on success (BUG-3).
- **Memory**: `core.memory.recall` over `events` — starved until embeddings are wired (§3). Character memories are LIKE-keyword only and externally-managed.
- **AI generation points**: local Ollama only (`modules/local_gen.py`, `http://localhost:11434`) — 8B abliterated primary, 4B fallback documented but unwired; the engine itself makes no external-LLM calls for prose (tags → `stream_templates` via `core/stream_interceptor`). A workbench with 8 providers would plug in at the _tag-expansion_ layer or call bridge actions for state and write prose itself.
- **Context injection today**: plugin `pre_llm_call` injects only the `cli status` text (≤800 chars, tools.py:363) on RP-trigger regex; there is **no automatic lore/memory/objective injection** — the workbench must call bridge actions explicitly per scene.
- **State portability**: `.sav` v2 (`core/savegame.py`) excludes vector tables and telemetry — RAG must be re-ingested after restore (`scripts/rp_ingest_novel.py`); write_lore/wiki vectors are lost on restore unless re-embedded.
