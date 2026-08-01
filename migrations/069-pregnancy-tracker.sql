-- 069: Pregnancy tracker — mothers, due dates, trimesters, births
-- Spec: track royal pregnancies per session; advance() rolls trimesters
-- and fires birth events when due. Never auto-deletes history.

-- ── 1. Table ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS maya_rp.pregnancies (
    id                  SERIAL PRIMARY KEY,
    session_id          INT NOT NULL REFERENCES maya_rp.sessions(id),
    mother_id           INT REFERENCES maya_rp.characters(id),
    mother_name         TEXT NOT NULL,
    father_name         TEXT DEFAULT 'King Izzat',
    conceived_game_day  INT NOT NULL,
    due_game_day        INT NOT NULL,
    gestation_days      INT NOT NULL DEFAULT 270,   -- standard TKG human term
    trimester           INT NOT NULL DEFAULT 1,     -- 1 | 2 | 3
    status              TEXT NOT NULL DEFAULT 'active',  -- active | due_soon | birthed | lost
    baby_name           TEXT,
    baby_gender         TEXT,                        -- male | female | unknown
    notes               TEXT,
    birthed_game_day    INT,
    created_at          TIMESTAMPTZ DEFAULT now(),
    UNIQUE (session_id, mother_id)
);

-- ── 2. Indexes ──────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS pregnancies_active_idx
    ON maya_rp.pregnancies (session_id, status, due_game_day);
CREATE INDEX IF NOT EXISTS pregnancies_due_idx
    ON maya_rp.pregnancies (due_game_day);

-- ── 3. Seed: current royal pregnancies (Engine Day 26) ──────────────────
-- Lyra Valance — just conceived (due in ~270 days)
INSERT INTO maya_rp.pregnancies
    (session_id, mother_id, mother_name, conceived_game_day, due_game_day, gestation_days, trimester, status, notes)
VALUES
    (3, 34, 'Lyra Valance', 22, 292, 270, 1, 'active', 'Just conceived. Vein Collective lineage — bridge pregnancy.')
ON CONFLICT (session_id, mother_id) DO NOTHING;

-- Layla Frost — 4 months pregnant (due in ~150 days)
INSERT INTO maya_rp.pregnancies
    (session_id, mother_id, mother_name, conceived_game_day, due_game_day, gestation_days, trimester, status, notes)
VALUES
    (3, 64, 'Layla Frost', 26 - 120, 176, 270, 2, 'active', '4 months along. Custodian of Lost Logs; quiet pregnancy.')
ON CONFLICT (session_id, mother_id) DO NOTHING;

-- ── 4. Grants ────────────────────────────────────────────────────────────
GRANT SELECT, INSERT, UPDATE, DELETE ON maya_rp.pregnancies TO rp_engine;
GRANT USAGE, SELECT ON SEQUENCE maya_rp.pregnancies_id_seq TO rp_engine;
