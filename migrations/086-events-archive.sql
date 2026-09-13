-- 086: events retention (ML review roadmap #6, 2026-08-14)
-- events grows every tick (14.5K rows at audit time). Housekeeping moves
-- rows older than 180 days to events_archive and prunes them from the live
-- table (same shape, indexes included via LIKE ... INCLUDING ALL).
CREATE TABLE IF NOT EXISTS maya_rp.events_archive (LIKE maya_rp.events INCLUDING ALL);
