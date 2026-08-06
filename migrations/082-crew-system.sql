-- 082-crew-system.sql
-- Crew System: crew pool + production + consumption + history
-- Runs as owner: maya

-- 1. Resources: crew pool (numeric, trained crew ready untuk assign)
ALTER TABLE maya_rp.resources ADD COLUMN IF NOT EXISTS crew_pool BIGINT DEFAULT 0;
ALTER TABLE maya_rp.resources ADD COLUMN IF NOT EXISTS crew_trained_total BIGINT DEFAULT 0;
ALTER TABLE maya_rp.resources ADD COLUMN IF NOT EXISTS crew_consumed_total BIGINT DEFAULT 0;

-- 2. Crew production log (history — untuk kira "from old council till now")
CREATE TABLE IF NOT EXISTS maya_rp.crew_production_log (
    id SERIAL PRIMARY KEY,
    session_id INTEGER,
    game_day INTEGER,
    source TEXT,                -- university, academy, recruitment, al_asir, event
    amount INTEGER,
    pool_after BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_crew_prod_log ON maya_rp.crew_production_log(session_id, game_day);

-- 3. Crew consumption log
CREATE TABLE IF NOT EXISTS maya_rp.crew_consumption_log (
    id SERIAL PRIMARY KEY,
    session_id INTEGER,
    game_day INTEGER,
    ship_id INTEGER,
    ship_name TEXT,
    amount INTEGER,
    pool_after BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_crew_cons_log ON maya_rp.crew_consumption_log(session_id);
