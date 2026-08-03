-- 065: Harta Karun — Den hoard floor at 40M, no ceiling.
-- Base treasuries snap to the floor; the Den faction treasury too.
UPDATE maya_rp.pirate_bases SET treasury = GREATEST(treasury, 40000000) WHERE status='active';
UPDATE maya_rp.factions SET treasury = GREATEST(treasury, 40000000)
WHERE is_pirate=true AND (status='active' OR status IS NULL);
