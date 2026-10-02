-- ═══════════════════════════════════════════════════════════════════
-- FRAMING BELONGS ON THE ASSET ROW
--
-- Framing was implicit: `STYLES` carried "512x512, upper body portrait" in the prompt text and
-- `portrait_render.py` wrote a literal 512x512 into the row regardless of what was rendered. A
-- waist-up render would therefore have been recorded as a square bust, and the row would have been
-- the only place a reader could have looked.
--
-- The column makes the framing a fact the database holds, so a query can select every waist render
-- and the renderer can size the latent from the same value that appears in the prompt.
--
-- Every row that exists today was rendered bust, so that is the backfill.
-- ═══════════════════════════════════════════════════════════════════
BEGIN;
SET search_path TO maya_rp;

ALTER TABLE character_assets ADD COLUMN IF NOT EXISTS framing text NOT NULL DEFAULT 'bust';

COMMENT ON COLUMN character_assets.framing IS
  'Composition of the render: bust, waist, knee or full. The prompt clause and the latent size both come from it';

CREATE INDEX IF NOT EXISTS character_assets_framing_idx ON character_assets (framing);

COMMIT;
