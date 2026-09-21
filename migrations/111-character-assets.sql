-- 111 — character assets: preset images per character and occasion.
--
-- One row per (character, kind, occasion): the image the game shows when a
-- character appears in a scene of that kind (portrait / emotion / outfit /
-- scene). `status = 'pending'` doubles as the render queue: scripts/portrait_render.py
-- picks pending rows, renders through ComfyUI, and fills image_path.
--
-- Owner: maya. Apply by hand:
--   PGPASSWORD=$POSTGRES_PASS psql -h $OC_PG_HOST -U maya -d maya_memory -f <this>

CREATE TABLE IF NOT EXISTS maya_rp.character_assets (
    id bigserial PRIMARY KEY,
    session_id int NOT NULL,
    character_id int NOT NULL REFERENCES maya_rp.characters(id) ON DELETE CASCADE,
    kind text NOT NULL DEFAULT 'portrait',
    occasion text NOT NULL DEFAULT 'neutral',
    image_path text,
    prompt text,
    negative_prompt text,
    model text,
    lora text,
    seed bigint,
    width int,
    height int,
    provider text NOT NULL DEFAULT 'comfyui-local',
    status text NOT NULL DEFAULT 'ready',
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT character_assets_status_check CHECK (status IN ('pending', 'ready', 'failed'))
);

-- One preset image per character and occasion; a new render replaces it.
CREATE UNIQUE INDEX IF NOT EXISTS character_assets_character_occasion
    ON maya_rp.character_assets (character_id, kind, occasion);

-- The renderer's queue scan stays cheap.
CREATE INDEX IF NOT EXISTS character_assets_pending
    ON maya_rp.character_assets (status) WHERE status <> 'ready';

COMMENT ON TABLE maya_rp.character_assets IS
    'Preset character images per occasion; status=pending is the render queue.';
