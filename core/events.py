"""Async event bus — pub/sub for cross-module communication."""

import asyncio, json, logging
from datetime import datetime, timezone
from typing import Dict, List, Callable, Awaitable, Optional
from .db import Database
from core.log import info, error

EventCallback = Callable[[Dict], Awaitable[None]]

#: Background work the bus starts and must keep alive. `asyncio.create_task` hands back a task the
#: event loop holds only a weak reference to, so a task nobody keeps can be collected before it ever
#: runs, and nothing reports it because its exception is never retrieved. Measured while reviewing
#: this module: 330 events carry the `bus` tag in session 5 and 3 of them hold an embedding, while
#: the engine log has no "Embedding failed" line for those days — the task never reached
#: `store_event`. Keeping the reference is what the asyncio documentation asks for, and the callback
#: is what turns a dying task into a line somebody can read.
_pending: set = set()


def _settle(task) -> None:
    _pending.discard(task)
    if not task.cancelled() and task.exception() is not None:
        error("events", f"background task failed: {task.exception()!r}")


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _pending.add(task)
    task.add_done_callback(_settle)


def _bus_session(data: Dict) -> int:
    """The session an emitted event belongs to.

    The literal 3 stood here, so any payload that omitted `session_id` was filed in the frozen
    reference campaign. `core.session` is the one source of session in this engine: explicit, then
    `RP_SESSION`, then the active arc, then a refusal that names what to pass. A refusal is caught
    by the handler below and logged, which is right: filing in the wrong campaign is worse than
    filing nothing.
    """
    from core.session import resolve_session

    return resolve_session(data.get("session_id"))


class EventBus:
    _listeners: Dict[str, List[EventCallback]] = {}

    @classmethod
    def on(cls, event_type: str, callback: EventCallback):
        if event_type not in cls._listeners:
            cls._listeners[event_type] = []
        cls._listeners[event_type].append(callback)

    @classmethod
    def off(cls, event_type: str, callback: EventCallback):
        if event_type in cls._listeners:
            cls._listeners[event_type] = [
                cb for cb in cls._listeners[event_type] if cb != callback
            ]

    @classmethod
    async def emit(cls, event_type: str, data: Dict):
        # `logging.info` and `logging.error` went to the root logger, which has no handler here and
        # sits at WARNING: the info line was dropped outright and the error line never reached
        # `logs/tick_YYYYMMDD.log`, which is the file the engine is read back from.
        info("events", f"Event: {event_type}")
        if event_type in cls._listeners:
            tasks = [cb(data) for cb in cls._listeners[event_type]]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            # Inspect results for silent failures — EventBus should never hide errors
            for i, cb_result in enumerate(results):
                if isinstance(cb_result, Exception):
                    cb_name = getattr(cls._listeners[event_type][i], "__name__", str(i))
                    error(
                        "events",
                        f"Event listener '{cb_name}' for '{event_type}' failed: {cb_result}",
                    )
        # Also log to events table
        try:
            sid = _bus_session(data)
            event_id = await Database.fetchval(
                "INSERT INTO events (session_id, happened_at, event_type, title, description, tags) "
                "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
                sid,
                datetime.now(timezone.utc),
                event_type,
                f"Event: {event_type}",
                json.dumps(data, ensure_ascii=False)[:497]
                + ("..." if len(json.dumps(data, ensure_ascii=False)) > 500 else ""),
                json.dumps(["bus", event_type]),
            )
            # Embed asynchronously (fire-and-forget) so the event bus never
            # blocks on Ollama — otherwise recall stays starved (2026-08-15 fix).
            if event_id:
                from core.memory import store_event

                _spawn(store_event(
                    event_id,
                    f"Event: {event_type}",
                    str(data)[:200],
                    sid,
                ))
            # Character memory wiring: events carrying a character_id also get
            # stored as a character memory (was dead code — zero callers, 2026-08-15 fix).
            char_id = data.get("character_id") or data.get("char_id")
            if char_id and event_id:
                from modules.memories import store as store_memory

                _spawn(store_memory(
                    int(char_id),
                    "event",
                    f"{event_type}: {str(data)[:200]}",
                    keywords=[event_type],
                    source_event_id=event_id,
                    session_id=sid,
                ))
        except Exception as e:
            error("events", f"Failed to log event: {e}")
