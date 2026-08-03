#!/usr/bin/env python3
"""
Generate wiki source code pages from live RP engine files.
Run: python3 scripts/gen_wiki_source.py
Output: /home/maya/Bumi-Hijau/wiki/rp-engine-*-source.md
"""
import os, re

PROJECT = "/home/maya/Bumi-Hijau/rp-engine-py"
WIKI = "/home/maya/Bumi-Hijau/wiki"
SKILL_DIR = "/home/maya/plugins/maya-skills/skills/rp-engine"
COMMANDS_DIR = "/home/maya/.kilo/command"

CORE_FILES = sorted([
    "config.py", "db.py", "state.py", "events.py", "log.py",
    "utils.py", "reputation.py", "memory.py", "pacing.py",
    "master_briefing.py", "dramatic_structure.py", "guard.py",
    "session_rituals.py", "player_profile.py", "scene_stack.py",
    "consequences.py", "chekhov.py",
])

SCRIPTS_FILES = sorted([
    "cli.py", "orchestrator.py", "kilo_bridge.py",
    "wiki_ingest.py", "embed_all.py", "migrate.py",
])

PLUGIN_FILES = sorted([
    "SKILL.md",
])
PLUGIN_COMMANDS = sorted([
    "rp-restore.md", "rp-save.md", "rp-end.md", "rp-query.md",
    "rp-check.md", "rp-lore.md", "rp-record-lore.md",
    "rp-physics.md", "rp-timeskip.md", "rp-act.md", "rp-look.md",
])
PLUGIN_CONTINUE = "/home/maya/Bumi-Hijau/main/rp-continue-session.md"


def get_module_files() -> list[str]:
    """Get all module .py files from modules/ directory."""
    mods_dir = os.path.join(PROJECT, "modules")
    files = []
    for f in sorted(os.listdir(mods_dir)):
        if f.endswith(".py") and f != "__init__.py":
            # Determine orchestrator status
            orch_path = os.path.join(PROJECT, "scripts", "orchestrator.py")
            name = f.replace(".py", "")
            wired = "❌ NOT WIRED"
            if os.path.exists(orch_path):
                with open(orch_path) as ofh:
                    orch_text = ofh.read()
                if f'"{name}"' in orch_text or f"'{name}'" in orch_text:
                    wired = "✅ WIRED"
            files.append((name, f, wired))
    return files


def read_file(path: str) -> str:
    """Read file content, returning empty string on error."""
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return f"(file not found: {path})"


def strip_yaml_frontmatter(text: str) -> str:
    """Remove YAML frontmatter (--- ... ---) from Markdown files."""
    return re.sub(r'^---\n.*?\n---\n', '', text, flags=re.DOTALL)


def fmt_source_code(filename: str, content: str) -> str:
    """Format a source code block for Markdown."""
    title = filename.replace(".py", "").replace("_", " ").title()
    title = re.sub(r'\bRp\b', 'RP', title)
    return f"\n## `{filename}` ({len(content.splitlines())} lines)\n\n```python\n{content}\n```\n"


# ─── CORE SOURCE ───────────────────────────────────────────────────────

def gen_core():
    lines = ["# RP Engine — Core Source",
             "",
             "> Full source code of `core/` directory. Auto-generated from live engine.",
             f"> Generated: 2026-07-31 | {len(CORE_FILES)} files | ~{sum(len(read_file(os.path.join(PROJECT, 'core', f)).splitlines()) for f in CORE_FILES)} lines",
             ""]
    for fname in CORE_FILES:
        content = read_file(os.path.join(PROJECT, "core", fname))
        lines.append(fmt_source_code(fname, content))
    return "\n".join(lines)


# ─── MODULES SOURCE ───────────────────────────────────────────────────

def gen_modules():
    mods = get_module_files()
    total_lines = 0
    for _, fname, _ in mods:
        total_lines += len(read_file(os.path.join(PROJECT, "modules", fname)).splitlines())

    lines = ["# RP Engine — Module Source",
             "",
             "> Full source code of all `modules/` directory. Auto-generated.",
             f"> Generated: 2026-07-31 | {len(mods)} modules | ~{total_lines} lines",
             "",
             "### Module Index",
             "",
             "| Module | Wired? | Lines |",
             "|--------|:------:|:-----:|",
             ]
    for name, fname, wired in mods:
        count = len(read_file(os.path.join(PROJECT, "modules", fname)).splitlines())
        lines.append(f"| `{fname}` | {wired} | {count} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    for name, fname, wired in mods:
        content = read_file(os.path.join(PROJECT, "modules", fname))
        lines.append(fmt_source_code(fname, content))

    return "\n".join(lines)


# ─── SCRIPTS SOURCE ───────────────────────────────────────────────────

def gen_scripts():
    total_lines = 0
    for fname in SCRIPTS_FILES:
        total_lines += len(read_file(os.path.join(PROJECT, "scripts", fname)).splitlines())

    lines = ["# RP Engine — Scripts Source",
             "",
             "> Full source code of `scripts/` directory.",
             f"> Generated: 2026-07-31 | {len(SCRIPTS_FILES)} scripts | ~{total_lines} lines",
             ""]
    for fname in SCRIPTS_FILES:
        content = read_file(os.path.join(PROJECT, "scripts", fname))
        lines.append(fmt_source_code(fname, content))

    return "\n".join(lines)


# ─── PLUGIN SOURCE ────────────────────────────────────────────────────

def gen_plugin():
    lines = ["# RP Engine — Plugin Source",
             "",
             "> Kilo plugin files: SKILL.md, commands, continue file.",
             f"> Generated: 2026-07-31",
             ""]

    # SKILL.md (strip YAML frontmatter, show as markdown)
    skill_content = strip_yaml_frontmatter(read_file(os.path.join(SKILL_DIR, "SKILL.md")))
    lines.append("\n## `SKILL.md` (RP Engine Skill)\n")
    lines.append(skill_content)
    lines.append("")

    # Kilo commands
    lines.append("\n---\n")
    lines.append("## Kilo Commands\n")
    for cmd in PLUGIN_COMMANDS:
        content = strip_yaml_frontmatter(read_file(os.path.join(COMMANDS_DIR, cmd)))
        lines.append(f"\n### `{cmd}`\n")
        lines.append(content)
        lines.append("")

    # Continue file
    lines.append("\n---\n")
    lines.append("## Continue File\n")
    lines.append(f"### `rp-continue-session.md`\n")
    cont = strip_yaml_frontmatter(read_file(PLUGIN_CONTINUE))
    lines.append(cont)

    return "\n".join(lines)


# ─── MAIN ─────────────────────────────────────────────────────────────

TARGETS = {
    "rp-engine-core-source.md": gen_core,
    "rp-engine-modules-source.md": gen_modules,
    "rp-engine-scripts-source.md": gen_scripts,
    "rp-engine-plugin-source.md": gen_plugin,
}


def main():
    for filename, generator in TARGETS.items():
        path = os.path.join(WIKI, filename)
        content = generator()
        with open(path, "w") as f:
            f.write(content)
        print(f"  ✅ {path} ({len(content.splitlines())} lines)")


if __name__ == "__main__":
    main()
