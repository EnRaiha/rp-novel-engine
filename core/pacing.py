#!/usr/bin/env python3
"""Narrative Pacing Director — controls prose style by scene mode. GM's sense of rhythm."""
from __future__ import annotations
import json
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

MODES = {
    "combat":     {"speed":"fast","senses":["kinesthetic","auditory"],"internal":"minimal","dialogue":"shouted_brief","para":"short","tension_floor":7,"desc":"sparse","time":"slow","example":"The hull screamed. Nethara's blade was already moving."},
    "crisis":     {"speed":"urgent","senses":["visual","auditory"],"internal":"scattered","dialogue":"interrupted_overlapping","para":"medium","tension_floor":8,"desc":"selective","time":"compressed","example":"Three problems. Twelve seconds. No good options left."},
    "social":     {"speed":"moderate","senses":["visual","thermal"],"internal":"active","dialogue":"subtext_heavy","para":"medium","tension_floor":2,"desc":"character_focused","time":"normal","example":"Melano's fingers traced the rim of his cup. He hadn't taken a sip in ten minutes."},
    "intimate":   {"speed":"slow","senses":["tactile","olfactory","thermal"],"internal":"deep","dialogue":"whispered_fragmented","para":"flowing","tension_floor":1,"desc":"rich","time":"stretched","example":"Her breath. The warmth where skin met skin. The silence that said everything.","anti_fade_rule":"CRITICAL ANTI-FADE: Do not use time-skips, fade-to-black, or 'they spent the night together' to avoid writing the scene. You must write the progression of the intimacy scene as it happens, maintaining the same literary commitment as a combat scene. Do not break the narrative flow."},
    "exploration":{"speed":"wandering","senses":["visual","olfactory","ambient_sound"],"internal":"curious","dialogue":"wonder_observations","para":"variable","tension_floor":1,"desc":"environmental","time":"normal","example":"The corridor opened into a cavern that shouldn't exist inside a ship."},
    "political":  {"speed":"measured","senses":["visual"],"internal":"calculating","dialogue":"formal_layered","para":"long","tension_floor":4,"desc":"power_dynamics","time":"normal","example":"The vote was never about the treaty. It was about who controlled the silence after."},
    "downtime":   {"speed":"leisurely","senses":["ambient","olfactory","thermal"],"internal":"reflective","dialogue":"casual_revealing","para":"flowing","tension_floor":0,"desc":"atmospheric","time":"fast_forward","example":"The afternoon dissolved into cards, bad coffee, and arguments about whether stars had feelings."},
    "horror":     {"speed":"dreadful","senses":["auditory","thermal_cold"],"internal":"doubting","dialogue":"hesitant_unreliable","para":"staccato","tension_floor":6,"desc":"wrong_details","time":"distorted","example":"The shadows were wrong. Not darker — wrong. As if something had drawn them incorrectly."},
}

OPENING_BEATS = {
    "combat": "The alarms haven't stopped.",
    "crisis": "Something is wrong. You can feel it in the way the crew moves.",
    "social": "The room settles as you enter. Eyes turn.",
    "intimate": "The door closes behind you. The rest of the universe fades.",
    "exploration": "The viewscreen fills with something new.",
    "political": "The council chamber waits. Every word will be measured.",
    "downtime": "The ship hums its quiet song. For now, there is peace.",
    "horror": "Something changed while you were sleeping. You can't name it. But you feel it.",
}

CHECK_QUERIES = {
    # narrative_hooks has hook_type/status — no 'severity' column (audit 31 Jul).
    # Open hooks are 'active' (readers: briefing/objectives/dramatic_structure/
    # narrative all filter status='active'); 'pending' was the column default and
    # matched nothing else, so counting it pinned the mode to crisis forever.
    "crisis": ["SELECT COUNT(*) FROM maya_rp.narrative_hooks WHERE session_id=$1 AND status='active'"],
    "combat": ["SELECT COUNT(*) FROM maya_rp.sieges WHERE session_id=$1 AND status='active'"],
    # cabinet_meetings has no status — convened without minutes = in progress.
    "political": ["SELECT COUNT(*) FROM maya_rp.cabinet_meetings WHERE session_id=$1 AND convened_at IS NOT NULL AND minutes IS NULL"],
    "exploration": ["SELECT COUNT(*) FROM maya_rp.science_missions WHERE session_id=$1 AND status='active'"],
}
PRIORITY = ["crisis","combat","political","exploration","social","horror","downtime"]


class PacingDirector:
    @staticmethod
    async def ensure(session_id: int):
        await Database.execute(
            "INSERT INTO maya_rp.narrative_pacing (session_id,mode,entered_at_game_day,tension,scenes_in_mode) "
            "VALUES ($1,'downtime',(SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1),0,0) ON CONFLICT DO NOTHING",
            session_id)

    @staticmethod
    async def get_mode(session_id: int = None) -> dict:
        if session_id is None: session_id = Config.SESSION_ID
        await PacingDirector.ensure(session_id)
        row = await Database.fetchrow("SELECT * FROM maya_rp.narrative_pacing WHERE session_id=$1", session_id)
        mode = row["mode"] if row else "downtime"
        cfg = MODES.get(mode, MODES["downtime"])
        return {"mode": mode, "config": cfg, "tension": row["tension"] if row else 0,
                "scenes_in_mode": row["scenes_in_mode"] if row else 0}

    @staticmethod
    def instruction(cfg: dict, mode: str) -> str:
        return (f"<pacing mode=\"{mode}\">\n"
                f"  <prose>{cfg['speed']}</prose>\n"
                f"  <senses>{', '.join(cfg['senses'])}</senses>\n"
                f"  <dialogue>{cfg['dialogue']}</dialogue>\n"
                f"  <internal>{cfg['internal']}</internal>\n"
                f"  <description>{cfg['desc']}</description>\n"
                f"  <time>{cfg['time']}</time>\n"
                + (f"  <tension_floor>{cfg['tension_floor']}</tension_floor>\n" if cfg.get('tension_floor', 0) > 0 else "")
                + f"  <example>{cfg['example']}</example>\n"
                + f"</pacing>")

    @staticmethod
    async def transition(new_mode: str, reason: str, session_id: int = None):
        if session_id is None: session_id = Config.SESSION_ID
        if new_mode not in MODES: return
        gd = await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id)
        await Database.execute(
            "UPDATE maya_rp.narrative_pacing SET mode=$1, entered_at_game_day=$2, last_transition_reason=$3, scenes_in_mode=0 WHERE session_id=$4",
            new_mode, gd, reason, session_id)
        info("pacing", f"Mode \u2192 {new_mode} — {reason}")

    @staticmethod
    async def check_transitions(session_id: int = None) -> str | None:
        if session_id is None: session_id = Config.SESSION_ID
        pm = await PacingDirector.get_mode(session_id)
        cm = pm["mode"]
        for target in PRIORITY:
            if target == cm or target == "horror": continue
            if target == "downtime": continue
            for q in CHECK_QUERIES.get(target, []):
                v = await Database.fetchval(q, session_id)
                if v and v > 0: return target
        return None

    @staticmethod
    async def adjust_tension(delta: int, reason: str = "", session_id: int = None):
        if session_id is None: session_id = Config.SESSION_ID
        await Database.execute(
            "UPDATE maya_rp.narrative_pacing SET tension = GREATEST(0, LEAST(10, tension + $1)) WHERE session_id=$2",
            delta, session_id)
        row = await Database.fetchrow("SELECT tension, mode FROM maya_rp.narrative_pacing WHERE session_id=$1", session_id)
        info("pacing", f"Tension {delta:+d} \u2192 {row['tension']}/10 [{row['mode']}]")

    @staticmethod
    async def increment(session_id: int = None):
        if session_id is None: session_id = Config.SESSION_ID
        await Database.execute("UPDATE maya_rp.narrative_pacing SET scenes_in_mode = scenes_in_mode + 1 WHERE session_id=$1", session_id)

    @staticmethod
    async def run_tick(session_id: int = None) -> dict:
        if session_id is None: session_id = Config.SESSION_ID
        try:
            await PacingDirector.ensure(session_id)
            r = await PacingDirector.get_mode(session_id)
            new_mode = await PacingDirector.check_transitions(session_id)
            if new_mode:
                await PacingDirector.transition(new_mode, "auto_detected", session_id)
                r["mode"] = new_mode
            return {"mode": r["mode"], "tension": r["tension"]}
        except Exception as e:
            info("pacing", f"Error: {e}")
            return {"error": str(e)}
