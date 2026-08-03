#!/usr/bin/env python3
"""
Wiki Ingest — reads Markdown lore files, chunks them into wiki-sized articles,
embeds them on the GTX 1060 (via Ollama/nomic-embed-text), and stores in
maya_rp.wiki_articles for semantic retrieval.

Usage:
  python3 scripts/wiki_ingest.py                          # Full re-ingest (skip existing titles)
  python3 scripts/wiki_ingest.py --force                   # Re-embed even if title exists
  python3 scripts/wiki_ingest.py --file setting-bible.md   # Ingest a single file

Lore files are defined in LORE_FILES below. Add new `.md` files there as your
wiki grows.
"""
import asyncio, sys, os, re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.config import Config
from core.db import Database
from core.log import info
from core.memory import embed_text

# ─── Map of lore files to their default categories ───────────────────────
# Each file maps to a base category. The chunker may override per-section.
LORE_FILES: dict[str, str] = {
    # Universe setting — factions, physics, technology
    f"{Config.ROOT}/../adventures/tkg/setting-bible.md": "history",
    # Current progression — fleet, story beats, state
    f"{Config.ROOT}/../adventures/tkg/progression.md": "technology",
}

# Glob for character sheets and novels
CHAR_SHEETS_DIR = f"{Config.ROOT}/../adventures/tkg/character-sheets"
NOVEL_DIR = f"{Config.ROOT}/../adventures/tkg/novel"


# ─── Markdown Chunker ────────────────────────────────────────────────────

def chunk_markdown(filepath: str, base_category: str) -> list[dict]:
    """
    Split a markdown file into chunks based on ## or ### headers.
    Returns list of {title, content, category, source_file}.
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()

    # Remove YAML front matter
    text = re.sub(r'^---\n.*?\n---\n', '', text, flags=re.DOTALL)

    chunks = []
    # Split on ## headers (top-level sections)
    sections = re.split(r'\n(?=##\s)', text)

    for section in sections:
        section = section.strip()
        if not section or len(section) < 50:
            continue

        lines = section.split('\n')
        # Extract the header (first ## or ### line)
        title = "Untitled"
        header_match = re.match(r'^#{1,3}\s+(.+)$', lines[0])
        if header_match:
            title = header_match.group(1).strip()
            content_lines = lines[1:]
        else:
            content_lines = lines

        content = '\n'.join(content_lines).strip()
        if len(content) < 50:
            continue

        # Auto-categorize based on header keywords
        cat = auto_category(title, content, base_category)

        # If section is too large (800+ chars), split by paragraphs
        if len(content) > 800:
            sub_chunks = split_large_chunk(title, content)
            for sc in sub_chunks:
                sc["category"] = auto_category(sc["title"], sc["content"], cat)
                sc["source_file"] = os.path.basename(filepath)
                chunks.append(sc)
        else:
            chunks.append({
                "title": title,
                "content": content,
                "category": cat,
                "source_file": os.path.basename(filepath),
            })

    return chunks


def split_large_chunk(title: str, content: str) -> list[dict]:
    """Split a large section (>800 chars) into smaller chunks by paragraph."""
    paragraphs = content.split('\n\n')
    chunks = []
    current_chunk = ""
    chunk_idx = 0

    for para in paragraphs:
        if not para.strip():
            continue
        # Table rows are kept together
        if para.strip().startswith('|') and para.strip().endswith('|'):
            current_chunk += para + "\n\n"
            continue
        if len(current_chunk) + len(para) > 600 and current_chunk:
            suffix = f" (pt.{chunk_idx + 1})" if chunk_idx > 0 else ""
            chunks.append({
                "title": f"{title}{suffix}",
                "content": current_chunk.strip(),
            })
            current_chunk = para + "\n\n"
            chunk_idx += 1
        else:
            current_chunk += para + "\n\n"

    if current_chunk.strip():
        suffix = f" (pt.{chunk_idx + 1})" if chunk_idx > 0 else ""
        chunks.append({
            "title": f"{title}{suffix}",
            "content": current_chunk.strip(),
        })

    return chunks if chunks else [{"title": title, "content": content}]


def auto_category(title: str, content: str, fallback: str) -> str:
    """Heuristic category detection based on title and content keywords."""
    t = title.lower()
    c = content.lower()

    if any(w in t for w in ['fleet', 'ship', 'weapon', 'combat', 'vessel', 'military', 'command']):
        return 'technology'
    if any(w in t for w in ['faction', 'domain', 'ethos', 'standing', 'concord', 'collective']):
        return 'faction'
    if any(w in t for w in ['planet', 'system', 'location', 'station', 'node', 'sector']):
        return 'location'
    if any(w in t for w in ['character', 'profile', 'officer', 'crew', 'companion']):
        return 'character'
    if any(w in t for w in ['history', 'story', 'chapter', 'prologue', 'departure']):
        return 'history'
    if any(w in t for w in ['rule', 'physics', 'law', 'constraint']) or '[RULE' in content:
        return 'rules'
    if any(w in t for w in ['species', 'alien', 'race', 'creature']):
        return 'species'
    # Technology keywords in content
    if any(w in c for w in ['vein network', 'ftl', 'fusion', 'torch drive']):
        return 'technology'

    return fallback


def extract_tags(title: str, content: str, category: str) -> list[str]:
    """Extract meaningful tags from the article."""
    tags = set()
    t = title.lower()
    c = content.lower()

    # Faction tags
    faction_map = {
        'tkg': 'tkg', 'vein collective': 'vein_collective', 'iron concord': 'iron_concord',
        'silent choir': 'silent_choir', 'ghost signal': 'ghost_signal', 'den': 'den',
        'pirate': 'pirate', 'council': 'council', 'setia': 'setia',
    }
    for keyword, tag in faction_map.items():
        if keyword in t or keyword in c:
            tags.add(tag)

    # Tech tags
    tech_map = {
        'vein': 'vein', 'fusion': 'fusion', 'ftl': 'ftl', 'weapon': 'weapon',
        'ship': 'ship', 'ai': 'ai', 'shield': 'shield', 'armour': 'armour',
    }
    for keyword, tag in tech_map.items():
        if keyword in t or keyword in c:
            tags.add(tag)

    # Category tag
    tags.add(category)

    return sorted(tags)


# ─── Ingestion ───────────────────────────────────────────────────────────

async def ingest_file(filepath: str, category: str, force: bool = False) -> int:
    """Read, chunk, embed, and store a single lore file. Returns chunk count."""
    if not os.path.exists(filepath):
        info("wiki", f"Skipping {filepath} (not found)")
        return 0

    info("wiki", f"Ingesting {os.path.basename(filepath)}...")
    chunks = chunk_markdown(filepath, category)
    inserted = 0

    for i, chunk in enumerate(chunks):
        # Context Sentinel: sanitize chunk BEFORE embedding/storage so
        # injection patterns never get baked into the RAG database.
        from core.context_sentinel import scan_text
        scan = scan_text(chunk['content'], source=f"file:{filepath}")
        if not scan.is_clean:
            info("sentinel", f"  ⚠️ Sanitized {len(scan.findings)} injection pattern(s) in '{chunk['title']}'")
        chunk['content'] = scan.sanitized

        # Build embedding text — title + content
        embed_text_input = f"{chunk['title']}. {chunk['content']}"

        # Check if already exists
        existing = await Database.fetchval(
            "SELECT id FROM maya_rp.wiki_articles WHERE title=$1 AND source_file=$2 AND session_id=$3",
            chunk['title'], chunk['source_file'], Config.SESSION_ID,
        )
        if existing and not force:
            continue  # Skip — already ingested

        # Generate embedding on GTX 1060
        try:
            embedding = await embed_text(embed_text_input)
        except Exception as e:
            info("wiki", f"  Embedding failed for '{chunk['title']}': {e}")
            continue

        vec_str = "[" + ",".join(map(str, embedding)) + "]"
        tags = extract_tags(chunk['title'], chunk['content'], chunk['category'])

        if existing:
            # Update existing
            await Database.execute(
                """UPDATE maya_rp.wiki_articles
                   SET content=$1, category=$2, tags=$3, embedding=$4::vector(768), source_file=$5
                   WHERE id=$6""",
                chunk['content'], chunk['category'], tags, vec_str,
                chunk['source_file'], existing,
            )
        else:
            # Insert new
            await Database.execute(
                """INSERT INTO maya_rp.wiki_articles
                   (session_id, title, category, tags, content, source_file, embedding)
                   VALUES ($1, $2, $3, $4, $5, $6, $7::vector(768))""",
                Config.SESSION_ID, chunk['title'], chunk['category'], tags,
                chunk['content'], chunk['source_file'], vec_str,
            )
        inserted += 1
        info("wiki", f"  [{i+1}/{len(chunks)}] {'Updated' if existing else 'Inserted'}: {chunk['title'][:60]}")

    return inserted


async def ingest_directory(dirpath: str, category: str, force: bool = False) -> int:
    """Ingest all .md files in a directory."""
    total = 0
    if not os.path.isdir(dirpath):
        info("wiki", f"Directory not found: {dirpath}")
        return 0
    for fname in sorted(os.listdir(dirpath)):
        if fname.endswith('.md'):
            fp = os.path.join(dirpath, fname)
            total += await ingest_file(fp, category, force)
    return total


async def main():
    force = '--force' in sys.argv
    single_file = None
    for arg in sys.argv[1:]:
        if arg.startswith('--file='):
            single_file = arg.split('=', 1)[1]
        elif arg == '--file' and len(sys.argv) > sys.argv.index(arg) + 1:
            idx = sys.argv.index(arg)
            single_file = sys.argv[idx + 1]

    await Database.init()
    sid = Config.SESSION_ID
    info("wiki", f"Wiki Ingestion — session={sid} force={force}")

    total = 0
    if single_file:
        # Ingest a specific file — look it up in LORE_FILES by basename
        matched = False
        for fp, cat in LORE_FILES.items():
            if os.path.basename(fp) == single_file or fp.endswith(single_file):
                total += await ingest_file(fp, cat, force)
                matched = True
                break
        if not matched:
            # Try as a direct path
            cat = 'history'
            for fp, c in LORE_FILES.items():
                if os.path.dirname(fp) == os.path.dirname(single_file):
                    cat = c
                    break
            total += await ingest_file(single_file, cat, force)
    else:
        # Full ingest
        for filepath, category in LORE_FILES.items():
            total += await ingest_file(filepath, category, force)
        total += await ingest_directory(CHAR_SHEETS_DIR, 'character', force)
        total += await ingest_directory(NOVEL_DIR, 'history', force)

    # Summary
    count = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.wiki_articles WHERE session_id=$1", sid)
    info("wiki", f"Done. {total} articles ingested/updated. Total wiki articles: {count}")

    await Database.close()


if __name__ == "__main__":
    asyncio.run(main())
