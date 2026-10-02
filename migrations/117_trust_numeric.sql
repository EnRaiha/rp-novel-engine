-- ═══════════════════════════════════════════════════════════════════
-- TRUST VOCABULARY — one type, one meaning
-- Applied 2026-10-02. The column held '60', '35', 'high', 'medium', 'low', 'minimal', 'none'.
-- The stance model silently fell back to 0.5 on the words, which made every
-- faction relationship a soft readout nobody could audit.
-- Backup of the raw vocabulary: ~/backups/trust-vocabulary-*.json
-- ═══════════════════════════════════════════════════════════════════
BEGIN;
SET search_path TO maya_rp;

ALTER TABLE factions ALTER COLUMN trust DROP DEFAULT;
ALTER TABLE factions ALTER COLUMN trust TYPE integer
  USING (CASE WHEN trust ~ '^[0-9]+$' THEN trust::integer
              WHEN lower(trust) = 'high' THEN 80
              WHEN lower(trust) = 'medium' THEN 50
              WHEN lower(trust) = 'low' THEN 35
              WHEN lower(trust) = 'minimal' THEN 15
              WHEN lower(trust) IN ('none', '') THEN 0
              ELSE 50 END);
ALTER TABLE factions ALTER COLUMN trust SET DEFAULT 50;

COMMENT ON COLUMN factions.trust IS 'integer 0-100. Vocabulary words are gone; do not write text here again';

COMMIT;
