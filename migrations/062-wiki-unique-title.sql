-- 062: Unique (session_id, title) for wiki_articles — enables write_lore upsert.
-- Dedupe first (keep the newest per session+title), then index.
DELETE FROM maya_rp.wiki_articles a
USING maya_rp.wiki_articles b
WHERE a.session_id = b.session_id AND a.title = b.title AND a.id < b.id;

CREATE UNIQUE INDEX IF NOT EXISTS wiki_articles_session_title_key
    ON maya_rp.wiki_articles (session_id, title);
