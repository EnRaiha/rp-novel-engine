-- 053-lore-branching-collapse.sql
-- Lore Branching: tie procedural wiki entries to checkpoints
-- + collapse tracking fields
-- ============================================================

-- 1a. Add checkpoint_id to wiki_articles for timeline-safe lore
ALTER TABLE maya_rp.wiki_articles ADD COLUMN IF NOT EXISTS checkpoint_id INT DEFAULT NULL;

-- 1b. Index for fast checkpoint filtering
CREATE INDEX IF NOT EXISTS idx_wiki_articles_checkpoint
    ON maya_rp.wiki_articles (session_id, checkpoint_id);

-- 2. Flag collapse events in story_arcs
ALTER TABLE maya_rp.story_arcs ADD COLUMN IF NOT EXISTS collapse_type VARCHAR(50) DEFAULT NULL;
ALTER TABLE maya_rp.story_arcs ADD COLUMN IF NOT EXISTS collapse_recovery TEXT DEFAULT NULL;

-- 3. Track overall faction/crew morale aggregate in resources for collapse detection
ALTER TABLE maya_rp.resources ADD COLUMN IF NOT EXISTS aggregate_morale INT DEFAULT 50;

-- 4. Add a time_skip log for Chrono-Engine transparency
CREATE TABLE IF NOT EXISTS maya_rp.time_skip_log (
    id          SERIAL PRIMARY KEY,
    session_id  INT NOT NULL DEFAULT 3,
    days_skipped INT NOT NULL,
    focus       VARCHAR(50) DEFAULT 'balanced',
    credits_before BIGINT,
    credits_after  BIGINT,
    events_summary TEXT[],
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
