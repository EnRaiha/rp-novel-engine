"""Async event bus — pub/sub for cross-module communication."""

import asyncio, json, logging
from datetime import datetime, timezone
from typing import Dict, List, Callable, Awaitable, Optional
from .db import Database

EventCallback = Callable[[Dict], Awaitable[None]]


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
        logging.info(f"Event: {event_type}")
        if event_type in cls._listeners:
            tasks = [cb(data) for cb in cls._listeners[event_type]]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            # Inspect results for silent failures — EventBus should never hide errors
            for i, cb_result in enumerate(results):
                if isinstance(cb_result, Exception):
                    cb_name = getattr(cls._listeners[event_type][i], "__name__", str(i))
                    logging.error(
                        f"Event listener '{cb_name}' for '{event_type}' failed: {cb_result}"
                    )
        # Also log to events table
        try:
            event_id = await Database.fetchval(
                "INSERT INTO events (session_id, happened_at, event_type, title, description, tags) "
                "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
                data.get("session_id", 3),
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

                asyncio.create_task(
                    store_event(
                        event_id,
                        f"Event: {event_type}",
                        str(data)[:200],
                        data.get("session_id", 3),
                    )
                )
            # Character memory wiring: events carrying a character_id also get
            # stored as a character memory (was dead code — zero callers, 2026-08-15 fix).
            char_id = data.get("character_id") or data.get("char_id")
            if char_id and event_id:
                from modules.memories import store as store_memory

                asyncio.create_task(
                    store_memory(
                        int(char_id),
                        "event",
                        f"{event_type}: {str(data)[:200]}",
                        keywords=[event_type],
                        source_event_id=event_id,
                        session_id=data.get("session_id", 3),
                    )
                )
        except Exception as e:
            logging.error(f"Failed to log event: {e}")
