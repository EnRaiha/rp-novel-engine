-- 072-drop-intimacy-session-fks.sql
-- BUGFIX: last_intimacy_session / first_intimacy_session / first_kiss_session
-- store the GAME DAY (a day counter, e.g. 127), NOT sessions(id) — the FK
-- constraints were wrong and broke process_indulgence() on any live intimacy.
-- character_id + session_id FKs remain (correct).
ALTER TABLE maya_rp.romance_arcs DROP CONSTRAINT IF EXISTS romance_arcs_last_intimacy_session_fkey;
ALTER TABLE maya_rp.romance_arcs DROP CONSTRAINT IF EXISTS romance_arcs_first_intimacy_session_fkey;
ALTER TABLE maya_rp.romance_arcs DROP CONSTRAINT IF EXISTS romance_arcs_first_kiss_session_fkey;
