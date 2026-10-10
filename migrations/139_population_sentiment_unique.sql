-- population_sentiment needs a unique key on (session_id, territory_id, faction_name).
-- `ON CONFLICT (session_id, territory_id, faction_name)` in modules/population_sentiment.py and
-- modules/news.py raised InvalidColumnReference on a database built from migrations/.
-- The live database already has this index, so applying the file there changes nothing.
--
-- APPLIED 2026-10-10 as `maya`, recorded in `_migrations`. The CREATE fails while duplicate rows exist.
-- Check: SELECT session_id, territory_id, faction_name, count(*) FROM maya_rp.population_sentiment GROUP BY 1,2,3 HAVING count(*) > 1;
BEGIN;
SET LOCAL search_path TO maya_rp;

CREATE UNIQUE INDEX IF NOT EXISTS pop_sentiment_session_territory_faction_key
    ON population_sentiment (session_id, territory_id, faction_name);

COMMIT;
