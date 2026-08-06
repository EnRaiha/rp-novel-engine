#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  RP ENGINE — Single Configuration File                      ║
║  All knobs, toggles, credentials in ONE place.              ║
║  Edit ONLY this file to change behaviour.                   ║
╚══════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations
import os
from typing import ClassVar


class Config:
    """Static config — imported directly, no instantiation needed."""

    # ─── Database ───────────────────────────────────────────────
    # RP_ENGINE has OWNER on maya_rp schema. Roast me for hardcoding.
    # This is a single-user private Tailscale game engine.
    DSN: ClassVar[str] = (
        "postgres://rp_engine:REDACTED@100.65.243.60:5432/maya_memory"
        "?search_path=maya_rp,public"
    )
    DB_MIN_SIZE: ClassVar[int] = 1
    DB_MAX_SIZE: ClassVar[int] = 15  # Increased for concurrent kilo_bridge + tick safety
    DB_TIMEOUT: ClassVar[int] = 30  # seconds

    # ─── Session ────────────────────────────────────────────────
    # TKG = session_id 3. Everything else has been purged.
    SESSION_ID: ClassVar[int] = 3

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
        # Existing game systems (7)
        "pirates": True, "slave_system": True,
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
        "agnes": True, "guardrails": True, "faction_ai": True,
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
        lines = [
            f"╔══ RP Engine Config ════════════════════════",
            f"║ Session:     {cls.SESSION_ID} ({cls.RP_UNIVERSE})",
            f"║ RP Mode:     {'ACTIVE' if cls.RP_MODE_ACTIVE else 'OFF'} ({cls.RP_TONE})",
            f"║ Database:    postgres://rp_engine@100.65.243.60/maya_memory",
            f"║ Schema:      maya_rp (260 tables)",
            f"║ Time mult:   {cls.TIME_MULTIPLIER}x",
            f"║ Modules on:  {len(cls.active_modules())}",
            f"║ Root:        {cls.ROOT}",
            f"╚════════════════════════════════════════════",
        ]
        return "\n".join(lines)
