-- 080-novel-adaptation-depth.sql
-- Fasa 2 & 3: crew pools, medals, crew_skills, title pressure columns
-- Runs as owner: maya

-- 1. slave_market: price_tier + category (half-beast / succubus / ex-commander / common)
ALTER TABLE maya_rp.slave_market ADD COLUMN IF NOT EXISTS price_tier TEXT DEFAULT 'common';
ALTER TABLE maya_rp.slave_market ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'common';
ALTER TABLE maya_rp.slave_market ADD COLUMN IF NOT EXISTS hidden_talent TEXT;

-- 2. artifacts: sacrifice_backstory + award_type (medal support)
ALTER TABLE maya_rp.artifacts ADD COLUMN IF NOT EXISTS sacrifice_backstory TEXT;
ALTER TABLE maya_rp.artifacts ADD COLUMN IF NOT EXISTS award_recipient TEXT;

-- 3. crew_roster: specialization (artisan/planner/navigator) + promotion_source
ALTER TABLE maya_rp.crew_roster ADD COLUMN IF NOT EXISTS specialization TEXT;
ALTER TABLE maya_rp.crew_roster ADD COLUMN IF NOT EXISTS promotion_source TEXT;

-- 4. territory: revocation_risk + title_performance
ALTER TABLE maya_rp.territory ADD COLUMN IF NOT EXISTS revocation_risk INT DEFAULT 0;
ALTER TABLE maya_rp.territory ADD COLUMN IF NOT EXISTS title_performance INT DEFAULT 0;

-- 5. research_projects: blueprint_price + saleable (blueprint market)
ALTER TABLE maya_rp.research_projects ADD COLUMN IF NOT EXISTS blueprint_price BIGINT DEFAULT 0;
ALTER TABLE maya_rp.research_projects ADD COLUMN IF NOT EXISTS saleable BOOLEAN DEFAULT false;

-- 6. quarterly tasks table
CREATE TABLE IF NOT EXISTS maya_rp.quarterly_tasks (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES maya_rp.sessions(id),
    quarter INT,                 -- game_day / 90
    task_index INT,              -- 1-4
    title TEXT,
    objective TEXT,
    target_value INT DEFAULT 0,
    progress INT DEFAULT 0,
    reward_type TEXT DEFAULT 'blueprint',  -- blueprint, credits, research
    reward_value BIGINT DEFAULT 0,
    status TEXT DEFAULT 'active',          -- active, completed, failed
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_quarterly_tasks_session ON maya_rp.quarterly_tasks(session_id, status);
