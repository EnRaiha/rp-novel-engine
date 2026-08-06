-- 083-crew-expansion.sql
-- 1. University expand ke setiap sistem + graduation cycle
-- 2. Crew clearance (C1-C4 vs C5+) + screening
-- 3. AI allocation support
-- Runs as owner: maya

-- University campuses: tambah territory_id + graduation cycle columns
ALTER TABLE maya_rp.university_campuses ADD COLUMN IF NOT EXISTS territory_id INTEGER;
ALTER TABLE maya_rp.university_campuses ADD COLUMN IF NOT EXISTS graduation_cycle_days INTEGER DEFAULT 30;
ALTER TABLE maya_rp.university_campuses ADD COLUMN IF NOT EXISTS last_graduation_day INTEGER DEFAULT 0;

-- Crew clearance: C1-C4 = clearance 1, C5+ = clearance 5 (loyalty tinggi / screened)
ALTER TABLE maya_rp.crew_roster ADD COLUMN IF NOT EXISTS clearance_level INTEGER DEFAULT 1;
ALTER TABLE maya_rp.crew_roster ADD COLUMN IF NOT EXISTS screened BOOLEAN DEFAULT false;

-- Ships: min clearance requirement (derive dari tier: tier>=5 = C5+ = clearance 5)
ALTER TABLE maya_rp.ships ADD COLUMN IF NOT EXISTS min_clearance INTEGER DEFAULT 1;

-- Crew market: functional role (bukan slave semata — lelaki & perempuan bekerja)
ALTER TABLE maya_rp.slave_market ADD COLUMN IF NOT EXISTS functional_role TEXT DEFAULT 'worker';
ALTER TABLE maya_rp.slave_market ADD COLUMN IF NOT EXISTS clearance_level INTEGER DEFAULT 1;

-- AI allocation log (Heaven AI manage crew)
CREATE TABLE IF NOT EXISTS maya_rp.crew_allocation_log (
    id SERIAL PRIMARY KEY,
    session_id INTEGER,
    game_day INTEGER,
    ship_id INTEGER,
    ship_name TEXT,
    crew_assigned INTEGER,
    source TEXT,               -- ai_heaven, university_cohort, market, screening
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_crew_alloc_log ON maya_rp.crew_allocation_log(session_id);
