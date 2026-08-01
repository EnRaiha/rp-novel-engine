-- 070: News freshness — game_day stamp + retire stale backlog
-- Problem: articles generated during time skips (ticks 94-108) lingered unread
-- and rolled as "news" days later. Fix: stamp each article with the game day
-- it was generated on; roll_news only serves fresh articles and retires old ones.

-- ── 1. Add game_day stamp ───────────────────────────────────────────────
ALTER TABLE maya_rp.news_articles ADD COLUMN IF NOT EXISTS game_day INT;

-- ── 2. Retire the stale backlog: all unread articles predate the current
--      freshness window (they are old news). Mark read so they never roll.
UPDATE maya_rp.news_articles
   SET read = true
 WHERE read = false
   AND game_day IS NULL;

-- ── 3. Backfill stamp for future reference: newest articles approximate
--      current game day (26); older ones trail off.
UPDATE maya_rp.news_articles
   SET game_day = 26 - ((SELECT COALESCE(MAX(tick_number),0) FROM maya_rp.news_articles) - tick_number) / 3
 WHERE game_day IS NULL;

-- ── 4. Index for freshness queries ──────────────────────────────────────
CREATE INDEX IF NOT EXISTS news_game_day_idx ON maya_rp.news_articles (session_id, game_day);

-- ── 5. Grants ───────────────────────────────────────────────────────────
GRANT SELECT, UPDATE ON maya_rp.news_articles TO rp_engine;
