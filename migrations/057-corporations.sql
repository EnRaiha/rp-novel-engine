-- 057: Corporation system v2 — contracts, CEOs, standing
-- Spec: charter companies, assign CEOs, issue directives, automated tick revenue.

-- ── 1. Upgrade existing corporations table (v1 had faction_id/treasury only) ──
ALTER TABLE maya_rp.corporations ADD COLUMN IF NOT EXISTS session_id INT;
ALTER TABLE maya_rp.corporations ADD COLUMN IF NOT EXISTS ceo_character_id INT REFERENCES maya_rp.characters(id);
ALTER TABLE maya_rp.corporations ADD COLUMN IF NOT EXISTS tier INT DEFAULT 1;
ALTER TABLE maya_rp.corporations ADD COLUMN IF NOT EXISTS efficiency INT DEFAULT 50;   -- 0-100
ALTER TABLE maya_rp.corporations ADD COLUMN IF NOT EXISTS standing INT DEFAULT 50;     -- 0-100 (player relationship)
ALTER TABLE maya_rp.corporations ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active';
ALTER TABLE maya_rp.corporations ADD COLUMN IF NOT EXISTS created_at_game_day INT;

UPDATE maya_rp.corporations SET session_id = 3, tier = 1, efficiency = 75, standing = 80,
                                created_at_game_day = 1
WHERE session_id IS NULL;

ALTER TABLE maya_rp.corporations ALTER COLUMN session_id SET NOT NULL;
ALTER TABLE maya_rp.corporations ADD CONSTRAINT corporations_session_name_key UNIQUE (session_id, name);

-- ── 2. Corporate contracts (directives) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS maya_rp.corporate_contracts (
    id               SERIAL PRIMARY KEY,
    session_id       INT NOT NULL,
    corp_id          INT REFERENCES maya_rp.corporations(id) ON DELETE CASCADE,
    contract_type    TEXT NOT NULL, -- 'resource_extraction','production_boost','privateering'
    target_system    TEXT,
    payout_credits   BIGINT DEFAULT 0,
    payout_alloys    BIGINT DEFAULT 0,
    duration_days    INT NOT NULL,
    days_remaining   INT NOT NULL,
    status           TEXT DEFAULT 'active'
);

-- ── 3. Seed: Bumi Hijau Industrial ───────────────────────────────────────
INSERT INTO maya_rp.corporations (session_id, name, industry, faction_id, tier, treasury, efficiency, standing, created_at_game_day)
VALUES (3, 'Bumi Hijau Industrial', 'manufacturing', 1, 2, 1500000, 75, 80, 1)
ON CONFLICT (session_id, name) DO NOTHING;

-- ── 4. Grants for engine user ────────────────────────────────────────────
GRANT SELECT, INSERT, UPDATE, DELETE ON maya_rp.corporate_contracts TO rp_engine;
GRANT USAGE, SELECT ON SEQUENCE maya_rp.corporate_contracts_id_seq TO rp_engine;
