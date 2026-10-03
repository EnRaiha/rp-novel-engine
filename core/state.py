"""Global state manager — session, save/load, checkpoint orchestration."""
from datetime import datetime, timezone
from typing import Dict
from pathlib import Path
from .db import Database
from .config import Config
from core.log import warn
from core.utils import comma


def _resolve_session(session_id: int | None) -> int:
    """The session the caller named, or the one the arc resolves to.

    The default used to be the literal 3 — the frozen reference campaign — so a
    caller that named none gathered from, and checkpointed, the one campaign that
    must not be written to. `core.session.resolve_session` refuses to guess.
    """
    from core.session import resolve_session

    resolved = resolve_session(session_id)
    if resolved is None:
        raise ValueError("no session named and the engine is in maintenance mode")
    return int(resolved)


class StateManager:
    @classmethod
    async def gather(cls, session_id: int | None = None) -> Dict:
        """Gather full game state for checkpoint export."""
        session_id = _resolve_session(session_id)
        state = {}
        state["session"] = await Database.fetchrow("SELECT * FROM sessions WHERE id=$1", session_id)
        state["resources"] = await Database.fetchrow("SELECT alloys, fuel, credits, dream_essence FROM resources WHERE session_id=$1", session_id)
        state["territories"] = await Database.fetch(
            "SELECT system_name, population, tax_rate, development_level, crisis_level FROM territory WHERE session_id=$1 AND controlling_faction='Setia Empire'",
            session_id)
        state["factions"] = await Database.fetch(
            "SELECT name, standing, reputation FROM factions WHERE session_id=$1 AND name NOT IN ('Setia Empire')", session_id)
        state["story"] = await Database.fetch(
            "SELECT happened_at, category, title, content, importance FROM story_log WHERE session_id=$1 ORDER BY happened_at DESC LIMIT 15", session_id)
        state["hooks"] = await Database.fetch(
            "SELECT hook_type, description, status FROM narrative_hooks WHERE session_id=$1 AND status!='resolved'", session_id)
        # ── ML importance gating (2026-08-14): blend recency with the
        # trained event-importance model — top 15 by score, not raw recency.
        try:
            from core.decision_models import predict_event_importance
            rows = await Database.fetch(
                "SELECT happened_at, category, title, content, importance, event_type "
                "FROM story_log WHERE session_id=$1 ORDER BY happened_at DESC LIMIT 40",
                session_id)
            if rows:
                scored = []
                for r in rows:
                    ev = {"event_type": r.get("event_type") or r.get("category") or "",
                          "tags": [], "happened_at": r["happened_at"]}
                    scored.append((predict_event_importance(ev), dict(r)))
                scored.sort(key=lambda x: -x[0])
                state["story"] = [s[1] for s in scored[:15]]
        except Exception as exc:
            # ML off/degraded → the recency list above stays authoritative, and
            # the reason is logged: a silent pass hid a model that failed to load.
            warn("state", f"event-importance model unavailable, keeping the recency list: {exc!r}")
        return state

    @classmethod
    async def export_md(cls, session_id: int | None = None) -> str:
        """Generate Markdown snapshot of entire game state."""
        session_id = _resolve_session(session_id)
        state = await cls.gather(session_id)
        lines = [f"# RP Engine State — Session {session_id}"]
        lines.append(f"**Generated:** {datetime.now(timezone.utc).isoformat()}\n")
        if state.get("resources"):
            r = state["resources"]
            lines.append(f"## Resources\nCredits: {comma(r['credits'])} | Alloys: {comma(r['alloys'])} | Fuel: {comma(r['fuel'])}\n")
        if state.get("territories"):
            lines.append("## Territories")
            for t in state["territories"]:
                tax = f"{float(t['tax_rate'])*100:.0f}%" if t["tax_rate"] is not None else "n/a"
                lines.append(f"- {t['system_name']}: Pop {comma(t['population'])}, Tax {tax}, Dev {t['development_level']}, Crisis {t['crisis_level']}")
            lines.append("")
        if state.get("factions"):
            lines.append("## Factions")
            for f in state["factions"]:
                lines.append(f"- {f['name']}: {f['standing']} (Rep: {f['reputation']})")
            lines.append("")
        if state.get("story"):
            lines.append("## Recent Story")
            for e in state["story"][:8]:
                lines.append(f"- [{e['happened_at'].strftime('%m-%d %H:%M') if e['happened_at'] else ''}] {e['title']}")
            lines.append("")
        return "\n".join(lines)

    @classmethod
    async def save_checkpoint(cls, session_id: int | None = None, label: str = "") -> str:
        """Save a story checkpoint into one of three slots."""
        session_id = _resolve_session(session_id)
        cfg = Config.get()
        md = await cls.export_md(session_id)
        rows = await Database.fetch(
            "SELECT checkpoint_number, MAX(created_at) AS last_used FROM story_checkpoints "
            "WHERE session_id=$1 GROUP BY checkpoint_number",
            session_id)
        last_used = {r["checkpoint_number"]: r["last_used"] for r in rows}
        free = [n for n in (1, 2, 3) if n not in last_used]
        # Three slots. With all three taken the oldest is the one this checkpoint
        # replaces; the previous selection kept its initial 1 whenever every slot
        # was used, so every save after the third claimed slot 1 again — measured
        # 395 rows numbered 1 against one each of 2 and 3 for session 3.
        num = min(free) if free else min(last_used, key=lambda n: (last_used[n] is not None, last_used[n]))
        fp = Path(cfg.BACKUP_DIR) / f"checkpoint_{num}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        fp.write_text(md, encoding="utf-8")
        await Database.execute(
            "INSERT INTO story_checkpoints (session_id, checkpoint_number, label, md_file_path) VALUES ($1, $2, $3, $4) "
            "ON CONFLICT DO NOTHING",
            session_id, num, label, str(fp))
        return str(fp)
