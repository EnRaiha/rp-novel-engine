"""Global state manager — session, save/load, checkpoint orchestration."""
import json, asyncio
from datetime import datetime, timezone
from typing import Dict, Optional, List
from pathlib import Path
from .db import Database
from .config import Config

class StateManager:
    @classmethod
    async def gather(cls, session_id: int = 3) -> Dict:
        """Gather full game state for checkpoint export."""
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
        return state

    @classmethod
    async def export_md(cls, session_id: int = 3) -> str:
        """Generate Markdown snapshot of entire game state."""
        state = await cls.gather(session_id)
        lines = [f"# RP Engine State — Session {session_id}"]
        lines.append(f"**Generated:** {datetime.now(timezone.utc).isoformat()}\n")
        if state.get("resources"):
            r = state["resources"]
            lines.append(f"## Resources\nCredits: {r['credits']:,} | Alloys: {r['alloys']:,} | Fuel: {r['fuel']:,}\n")
        if state.get("territories"):
            lines.append("## Territories")
            for t in state["territories"]:
                lines.append(f"- {t['system_name']}: Pop {t['population']:,}, Tax {float(t['tax_rate'])*100:.0f}%, Dev {t['development_level']}, Crisis {t['crisis_level']}")
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
    async def save_checkpoint(cls, session_id: int = 3, label: str = "") -> str:
        """Save a story checkpoint."""
        cfg = Config.get()
        md = await cls.export_md(session_id)
        num = 1
        existing = await Database.fetch("SELECT checkpoint_number FROM story_checkpoints WHERE session_id=$1", session_id)
        used = {r["checkpoint_number"] for r in existing}
        for n in (1, 2, 3):
            if n not in used:
                num = n
                break
        fp = Path(cfg.BACKUP_DIR) / f"checkpoint_{num}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        fp.write_text(md)
        await Database.execute(
            "INSERT INTO story_checkpoints (session_id, checkpoint_number, label, md_file_path) VALUES ($1, $2, $3, $4) "
            "ON CONFLICT DO NOTHING",
            session_id, num, label, str(fp))
        return str(fp)
