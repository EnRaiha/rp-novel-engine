-- ═══════════════════════════════════════════════════════════════════
-- SCIENCE PROGRAMMES AND THE LONG KNIFE: Fasa 2.3 and 2.4
--
-- Adds columns to tables that already exist. No new table. No seed rows.
--   research_queue   the faction programme row (one per faction per tier)
--   dark_ops         the sabotage or assassination that stalls it
-- Canon: wiki/rp-dev/SCIENCE-ASSASSINATION-2026-10-02.md
--
-- Why research_queue: it is already the per-session cursor over the
-- research_projects catalog (modules/research.py:run_tick), and it already
-- carries session_id. Putting the programme here leaves the 66 catalog rows
-- and the 48 technologies rows with their current meaning.
--
-- Status vocabulary. research_queue.status stays free text. A programme row
-- uses theory | building | stalled | complete | abandoned. The queue keeps
-- pending and active, so run_tick, which selects those two, never picks up a
-- programme row.
--
-- Seed rows are a separate unit, blocked on funding: session 5 has no
-- maya_rp.resources row and factions.treasury is 0 for TKG.
-- ═══════════════════════════════════════════════════════════════════
BEGIN;
SET LOCAL search_path TO maya_rp;

-- ── Fasa 2.3: the programme ────────────────────────────────────────
ALTER TABLE research_queue ADD COLUMN IF NOT EXISTS faction_id integer REFERENCES factions(id);
ALTER TABLE research_queue ADD COLUMN IF NOT EXISTS tier_target smallint;
ALTER TABLE research_queue ADD COLUMN IF NOT EXISTS programme_days integer NOT NULL DEFAULT 0;
ALTER TABLE research_queue ADD COLUMN IF NOT EXISTS lead_character_id integer REFERENCES characters(id);
ALTER TABLE research_queue ADD COLUMN IF NOT EXISTS theory_only boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN research_queue.faction_id IS 'Faction that owns the programme. NULL on a legacy queue row.';
COMMENT ON COLUMN research_queue.tier_target IS 'Rung the programme climbs. 5 is the peak that can be built; 6 to 9 exist only as theory.';
COMMENT ON COLUMN research_queue.programme_days IS 'Programme-days, advanced by modules/programme_cost.py. Not credits and not percent.';
COMMENT ON COLUMN research_queue.lead_character_id IS 'Named scientist. NULL means no advance: progress rate is 0.';
COMMENT ON COLUMN research_queue.theory_only IS 'Faction holds the theory and cannot prove it. Always paired with lead_character_id IS NULL. The reason is read from factions.doctrine or factions.scale_class, never stored.';
COMMENT ON COLUMN research_queue.status IS 'Queue: pending | active | complete. Programme: theory | building | stalled | complete | abandoned. A programme row must never use active.';

CREATE UNIQUE INDEX IF NOT EXISTS research_queue_programme_key
    ON research_queue (session_id, faction_id, tier_target)
    WHERE faction_id IS NOT NULL;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'research_queue_tier_target_check') THEN
    ALTER TABLE research_queue ADD CONSTRAINT research_queue_tier_target_check
      CHECK (tier_target IS NULL OR tier_target BETWEEN 5 AND 9);
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'research_queue_theory_only_check') THEN
    ALTER TABLE research_queue ADD CONSTRAINT research_queue_theory_only_check
      CHECK (NOT theory_only OR lead_character_id IS NULL);
  END IF;
END $$;

-- ── Fasa 2.4: the operation ────────────────────────────────────────
-- dark_ops is the chosen house of the three that exist. espionage_missions
-- and conspiracies stay unused, and this link does not make a fourth one.
-- A programme operation writes success_chance = kill_score and outcome =
-- kill_outcome, so the deciding number is readable off the row. darkops.run_op
-- is not used for it: that function rolls random.randint, which P5 forbids.
ALTER TABLE dark_ops ADD COLUMN IF NOT EXISTS programme_id integer REFERENCES research_queue(id);
ALTER TABLE dark_ops ADD COLUMN IF NOT EXISTS target_character_id integer REFERENCES characters(id);

COMMENT ON COLUMN dark_ops.programme_id IS 'Programme this operation bleeds. NULL when the operation is not aimed at one.';
COMMENT ON COLUMN dark_ops.target_character_id IS 'The named person. target_name stays the display name; this is the link resolution reads.';
COMMENT ON COLUMN dark_ops.success_chance IS 'For a programme operation, the deterministic kill score from modules/programme_cost.py. Never a random roll.';

COMMIT;
