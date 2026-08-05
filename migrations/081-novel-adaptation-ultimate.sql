-- 081-novel-adaptation-ultimate.sql
-- Ultimate 5: Talent Shortage + Ship Legacy/Scars + Quarterly Tasks upgrade
-- Runs as owner: maya

-- 1. TALENT SHORTAGE — crew bottleneck (novel: bottleneck bukan kapal, tapi crew)
ALTER TABLE maya_rp.ships ADD COLUMN IF NOT EXISTS crew_current INTEGER DEFAULT 0;
ALTER TABLE maya_rp.ships ADD COLUMN IF NOT EXISTS crew_required INTEGER DEFAULT 0;
ALTER TABLE maya_rp.ships ADD COLUMN IF NOT EXISTS undercrewed_penalty NUMERIC DEFAULT 0.0;

-- 2. SHIP LEGACY — procedural scars + veteran kills (novel: Blizzard Zero ada sejarah)
ALTER TABLE maya_rp.ships ADD COLUMN IF NOT EXISTS veteran_kills INTEGER DEFAULT 0;
ALTER TABLE maya_rp.ships ADD COLUMN IF NOT EXISTS scars_jsonb JSONB DEFAULT '[]'::jsonb;
ALTER TABLE maya_rp.ships ADD COLUMN IF NOT EXISTS ship_rank TEXT DEFAULT 'Standard'; -- Standard/Veteran/Legendary

-- 3. QUARTERLY TASKS — upgrade schema (task_type, target, required_amount, current_progress, reward_blueprint)
ALTER TABLE maya_rp.quarterly_tasks ADD COLUMN IF NOT EXISTS task_type TEXT DEFAULT 'generic';
ALTER TABLE maya_rp.quarterly_tasks ADD COLUMN IF NOT EXISTS target TEXT DEFAULT '';
ALTER TABLE maya_rp.quarterly_tasks ADD COLUMN IF NOT EXISTS required_amount INTEGER DEFAULT 0;
ALTER TABLE maya_rp.quarterly_tasks ADD COLUMN IF NOT EXISTS current_progress INTEGER DEFAULT 0;
ALTER TABLE maya_rp.quarterly_tasks ADD COLUMN IF NOT EXISTS reward_blueprint TEXT DEFAULT '';

-- 4. CREW ROSTER — ship assignment tracking
ALTER TABLE maya_rp.crew_roster ADD COLUMN IF NOT EXISTS ship_id INTEGER;

-- Index untuk crew bottleneck query
CREATE INDEX IF NOT EXISTS idx_crew_roster_unassigned ON maya_rp.crew_roster(session_id, ship_id, status);
