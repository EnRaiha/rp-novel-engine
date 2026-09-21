-- 104 — QA fix wave, 2026-09-16 (rp-engine)
-- Runs as the maya_rp owner. Idempotent.

-- 1. crew_career.py writes crew_roster.rank (tick backfill + promotions + manual
--    promotion checks). The column never existed in any migration, so every one
--    of those statements failed and the bare `except: pass` hid it.
ALTER TABLE maya_rp.crew_roster
    ADD COLUMN IF NOT EXISTS rank varchar(40) DEFAULT 'Crewman';

-- 2. narrative_hooks: open hooks are 'active' — briefing.py, objectives.py,
--    narrative.py and dramatic_structure.py all filter status='active'. The
--    column default was 'pending', which no reader matched, while pacing.py's
--    crisis detector counted exactly those 'pending' rows, so it saw every hook
--    as a crisis while the briefing reported zero crises.
ALTER TABLE maya_rp.narrative_hooks
    ALTER COLUMN status SET DEFAULT 'active';
UPDATE maya_rp.narrative_hooks SET status = 'active' WHERE status = 'pending';
