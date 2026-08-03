# Module Contract

Every module in this directory MUST export:

```python
async def run_tick(session_id: int) -> dict | None:
    """
    Run one tick of this module.

    Returns:
        dict with results (e.g. {"prisoners": 5, "escaped": 1})
        None if nothing happened this tick.

    Rules:
        - Use Database.fetchrow / .fetch / .execute / .fetchval for all DB access
        - Use info() / warn() / error() from core.log — never print()
        - NEVER raise exceptions — return {"error": "message"} instead
        - Be idempotent — safe to run twice in a row
        - All timestamps use UTC
    """
```

To add a new module:
1. Create `modules/your_module.py` with `async def run_tick(session_id)`
2. Add to `Config.MODULES` in `core/config.py`
3. Add to the tick pipeline in `scripts/orchestrator.py` (import + run_module call)
4. Add to `MODULE_MAP` in `scripts/orchestrator.py`
