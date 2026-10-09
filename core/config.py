#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  RP ENGINE — Single Configuration File                      ║
║  All knobs, toggles, credentials in ONE place.              ║
║  Edit ONLY this file to change behaviour.                   ║
╚══════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import re
import sys
import os
from typing import ClassVar
from urllib.parse import urlsplit, urlunsplit


#: True when the process default came from the fallback rather than from the engine's own resolver.
#: A silent fallback is how a write reaches a session nobody chose, so the fallback announces itself.
SESSION_FALLBACK_USED = False


def _default_session() -> int:
    """Resolve the process default from the engine's single session source.

    Two things are worth knowing about this value. It is resolved **once**, at import, so a long-lived
    process keeps the session it started with even after the arc moves. And when the resolver fails,
    this falls back to the legacy TKG campaign, which is the **frozen reference** session — so the
    fallback announces itself rather than letting a write arrive somewhere nobody chose.

    @returns the session id this process will use when a call does not name one.
    """
    global SESSION_FALLBACK_USED
    try:
        from core.session import resolve_session

        return int(resolve_session())
    except Exception as exc:
        SESSION_FALLBACK_USED = True
        print(
            f"warning: no session resolved ({exc.__class__.__name__}); falling back to the legacy "
            "TKG campaign, which is the FROZEN reference session. Name a session explicitly, or "
            "write ~/.config/rp-engine/active_arc.",
            file=sys.stderr,
        )
        return 3  # no arc file and no override: the legacy TKG campaign


#: Built-in DSN. It holds the `rp_engine` password, so `RP_ENGINE_DSN` can replace it.
_DEFAULT_DSN = (
    "postgres://rp_engine:REDACTED@postgresql.tail73711d.ts.net:5432/maya_memory"
    "?search_path=maya_rp,public"
)
_DB_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}")


def _resolve_dsn(environ=None) -> tuple[str, bool]:
    """Resolve the database DSN from the environment.

    `RP_ENGINE_DSN` replaces the built-in DSN. `RP_ENGINE_DB` then replaces the database name in
    whichever DSN applies. `OC_PG_*` is not read: on this host it names a superuser, and the engine
    must keep running as `rp_engine`.

    @param environ - mapping to read, `os.environ` by default.
    @returns `(dsn, used_default)`. `used_default` is true when the environment named no DSN.
    @raises RuntimeError - `RP_ENGINE_DB` is not a plain database name. The message never carries a DSN.
    """
    env = os.environ if environ is None else environ
    given = (env.get("RP_ENGINE_DSN") or "").strip()
    dsn = given or _DEFAULT_DSN
    name = (env.get("RP_ENGINE_DB") or "").strip()
    if name:
        if not _DB_NAME.fullmatch(name):
            raise RuntimeError("RP_ENGINE_DB must be a plain database name (letters, digits, underscore)")
        dsn = urlunsplit(urlsplit(dsn)._replace(path="/" + name))
    return dsn, not given


_DSN, _DSN_FALLBACK = _resolve_dsn()


class Config:
    """Static config — imported directly, no instantiation needed."""

    # ─── Database ───────────────────────────────────────────────
    # The built-in DSN is in this file. RP_ENGINE_DSN replaces it. RP_ENGINE_DB replaces the database name only.
    # This is a single-user private Tailscale game engine.
    # Addressed by its Tailscale name, per the addressing convention: `100.65.243.60:5432` is the
    # fallback and stays in this comment rather than in the DSN. Measured before the change: the
    # name resolves through MagicDNS and the engine connects and queries through it.
    DSN: ClassVar[str] = _DSN
    DSN_FALLBACK_USED: ClassVar[bool] = _DSN_FALLBACK
    DB_MIN_SIZE: ClassVar[int] = 1
    DB_MAX_SIZE: ClassVar[int] = 15  # Increased for concurrent kilo_bridge + tick safety
    DB_TIMEOUT: ClassVar[int] = 30  # seconds

    # ─── Session ────────────────────────────────────────────────
    # The default every module inherits, resolved once at import from the single
    # source: RP_SESSION, then the active-arc file, then the legacy TKG id. Entry
    # points that must not guess (cli.py, the bridges) resolve_per_call instead.
    SESSION_ID: ClassVar[int] = _default_session()

    # ─── Paths ──────────────────────────────────────────────────
    ROOT: ClassVar[str] = os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
    BACKUP_DIR: ClassVar[str] = "/home/maya/backups"
    ARCHIVE_DIR: ClassVar[str] = "/home/maya/archive"
    MIGRATIONS_DIR: ClassVar[str] = os.path.join(ROOT, "migrations")
    LOG_DIR: ClassVar[str] = os.path.join(ROOT, "logs")

    # ─── RP Mode ────────────────────────────────────────────────
    # Controls narrative voice, tone matrix, and LLM injection
    RP_MODE_ACTIVE: ClassVar[bool] = True
    RP_TONE: ClassVar[str] = "English"       # English / Malay
    RP_UNIVERSE: ClassVar[str] = "TKG"       # TKG / Echoes / Custom

    # ─── Feature Flags ──────────────────────────────────────────
    # Set False to skip a module during full tick
    MODULES: ClassVar[dict[str, bool]] = {
        # Core state (5)
        "economy": True, "research": True, "diplomacy": True,
        "narrative": True, "victory": True,
        # Crew system (novel: crew bottleneck)
        "crew_system": True,
        # Narrative modules (9 JS→Python ports)
        "prison": True, "romance": True, "social": True,
        "mystery": True, "council": True, "celestial": True,
        "fleet_economy": True, "tactics": True, "events": True,
        "market": True,
        # Existing game systems (7)
        "pirates": True, "slave_system": True, "pregnancy": True,
        "megastructures_ports": True, "infrastructure": True,
        "space_wonders": True, "space_horror": True, "battle": True,
        # Ship operations (5)
        "ship_generation": True, "ship_building": True,
        "fleet": True, "refit": True, "weapon_design": True,
        # Intel & military (6)
        "espionage": True, "darkops": True, "stealth": True,
        "defense": True, "siege": True, "disasters": True,
        # Science & progress (8)
        "tech_tree": True, "manufacturing": True, "auto_queue": True, "exoscience": True,
        "academy": True, "university": True, "alchemy": True,
        "archaeology": True, "artifacts": True,
        # Narrative & media (5)
        "adventures": True, "narrator": True, "news": True,
        "quest": True, "epilogue": True, "image_gen": True,
        # Integration & safety (4)
        "agnes": False, "guardrails": True, "faction_ai": True,
        "event_catalog": True, "collapse": True,
        # Characters
        "characters": True,
        # New features (roadmap)
        "calendar": True, "consequences": True, "narrative_seeds": True,
        "war": True, "memories": True, "locations": True,
        # GM BRAIN features
        "pacing": True, "objectives": True, "environment": True,
        # Tier 3 — Living Universe
        "npc_autonomy": True, "secrets": True, "dramatic_structure": True,
        "themes": True, "meanwhile": True, "conversation_log": True,
        "physical_state": True, "chekhov": True, "world_react": True,
        # Frontiers
        "logistics": True, "geopolitics": True, "crew_career": True, "ideology": True,
        "corporations": True,
        # Transit — real voyage time accounting
        "voyage": True, "population_sentiment": True, "ministry_ai": True,
    }

    # ─── Tick Control ───────────────────────────────────────────
    # Narrative time multiplier: 1 = real-time, 4 = 4 game days per tick
    TIME_MULTIPLIER: ClassVar[int] = 4

    # ─── API Keys (external services) ───────────────────────────
    # Telemetry / Image gen / Narration — optional
    SENTRY_DSN: ClassVar[str | None] = None
    # e.g. "http://key@100.81.212.67:9199/1"
    OPENAI_API_KEY: ClassVar[str | None] = None
    REPLICATE_API_KEY: ClassVar[str | None] = None

    # ─── Derived ────────────────────────────────────────────────
    @classmethod
    def get(cls) -> Config:
        """Backward-compatible accessor for legacy import style."""
        return cls

    @classmethod
    def is_module_active(cls, name: str) -> bool:
        return cls.MODULES.get(name, False)

    @classmethod
    def active_modules(cls) -> list[str]:
        return [k for k, v in cls.MODULES.items() if v]

    @classmethod
    def summary(cls) -> str:
        # The host comes from the DSN rather than a second copy of it, so a move of the database
        # cannot leave the summary pointing at the old address.
        # `netloc` rather than a split on "@": a DSN without credentials has no "@" and starts with the scheme.
        parts = urlsplit(cls.DSN)
        host = parts.netloc.rsplit("@", 1)[-1]
        database = parts.path.lstrip("/")
        lines = [
            f"╔══ RP Engine Config ════════════════════════",
            f"║ Session:     {cls.SESSION_ID} ({cls.RP_UNIVERSE})",
            f"║ RP Mode:     {'ACTIVE' if cls.RP_MODE_ACTIVE else 'OFF'} ({cls.RP_TONE})",
            f"║ Database:    postgres://rp_engine@{host}/{database}",
            f"║ Schema:      maya_rp (260 tables)",
            f"║ Time mult:   {cls.TIME_MULTIPLIER}x",
            f"║ Modules on:  {len(cls.active_modules())}",
            f"║ Root:        {cls.ROOT}",
            f"╚════════════════════════════════════════════",
        ]
        return "\n".join(lines)
