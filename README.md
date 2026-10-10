# rp-novel-engine

A session-scoped RPG engine for a long-form novel: one PostgreSQL database, one tick loop, and a
Python module per subsystem.

## What it does

- Runs a campaign in game days. `scripts/orchestrator.py` calls 24 phases in order.
- Keeps every row tied to a campaign through `session_id`, so two novels can share one database.
- Names the novel a campaign belongs to: `novels` plus `sessions.novel_id` (migration 137).
- Audits the game master's prose for persona drift (`core/ooc.py`).
- Exports and restores a campaign as a portable `.sav` (`core/savegame.py`).

## Layout

| Path | What lives there |
|---|---|
| `core/` | DB pool, config, session resolution, events, savegame, OOC audit |
| `modules/` | One subsystem per file: economy, fleet, battle, diplomacy, research, and the rest |
| `migrations/` | Ordered SQL, one transaction each, applied by `scripts/migrate.py` |
| `scripts/` | CLI verbs, the tick, one-shot data scripts, bridges |
| `tests/` | pytest, against a live database, scratch campaigns only |

## Run

```bash
python3 -m pytest tests/ -q -p no:cacheprovider     # needs a database
```

## Database

The engine reads its DSN in this order:

1. `RP_ENGINE_DSN` in the environment.
2. `~/.config/rp-engine/dsn`, mode 600, one line.
3. The built-in default in `core/config.py`, which carries no credentials.

`RP_ENGINE_DB` replaces the database name in whichever DSN applies.

The schema lives in `migrations/`. `scripts/migrate.py` records each applied file in
`maya_rp._migrations` and skips a file already recorded.

## Notes

- Sessions are resolved per call: explicit argument, then `RP_SESSION`, then the active arc file.
- A frozen campaign is readable and refuses every write unless maintenance is armed.
- The published history drops the internal graph cache and carries no database credential.
