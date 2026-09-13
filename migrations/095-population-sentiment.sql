-- 095-population-sentiment.sql — Population sentiment/bias layer (Izzat, Day 1383).
-- Per-system × per-faction: how the PEOPLE feel (population is resource-driven and
-- faction-INDEPENDENT — sentiment tracks what people think OF factions, not under them).

CREATE TABLE IF NOT EXISTS maya_rp.population_sentiment (
    id             SERIAL PRIMARY KEY,
    session_id     INTEGER NOT NULL,
    territory_id   INTEGER NOT NULL REFERENCES maya_rp.territory(id),
    faction_id     INTEGER REFERENCES maya_rp.factions(id),
    faction_name   TEXT NOT NULL,                    -- denormalized (rotation-safe)
    sentiment      INTEGER NOT NULL DEFAULT 0,       -- -100 .. +100 (net feeling)
    approval       INTEGER NOT NULL DEFAULT 0,       -- 0..100 (support)
    fear           INTEGER NOT NULL DEFAULT 0,       -- 0..100 (dread/coercion)
    trust          INTEGER NOT NULL DEFAULT 0,       -- 0..100 (credibility)
    bias           INTEGER NOT NULL DEFAULT 0,       -- 0..100 (news/media slant)
    last_shift     INTEGER NOT NULL DEFAULT 0,       -- last sentiment delta
    last_shift_reason TEXT,
    updated_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (session_id, territory_id, faction_id)
);

CREATE INDEX IF NOT EXISTS idx_pop_sent_terr ON maya_rp.population_sentiment (session_id, territory_id);
CREATE INDEX IF NOT EXISTS idx_pop_sent_fac  ON maya_rp.population_sentiment (session_id, faction_id);

-- Seed helper rows: for every territory (controlled + neutral), baseline sentiment
-- toward the territory's own controlling faction, plus toward Setia Empire.
DO $$
DECLARE
    t RECORD;
    fac RECORD;
BEGIN
    FOR t IN SELECT id, controlling_faction FROM maya_rp.territory WHERE session_id=3 LOOP
        -- Baseline toward governing faction (if any): neutral-positive by morale
        IF t.controlling_faction IS NOT NULL AND t.controlling_faction <> '' THEN
            INSERT INTO maya_rp.population_sentiment
                (session_id, territory_id, faction_name, sentiment, approval, fear, trust, bias, last_shift_reason)
            SELECT 3, t.id, t.controlling_faction, 5, 55, 10, 45, 0, 'seed: governance baseline'
            WHERE NOT EXISTS (SELECT 1 FROM maya_rp.population_sentiment ps
                              WHERE ps.session_id=3 AND ps.territory_id=t.id AND ps.faction_name=t.controlling_faction);
        END IF;
        -- Baseline toward Setia Empire (all territories know the Empire)
        INSERT INTO maya_rp.population_sentiment
            (session_id, territory_id, faction_name, sentiment, approval, fear, trust, bias, last_shift_reason)
        SELECT 3, t.id, 'Setia Empire (Kingdom)', 10, 60, 5, 55, 0, 'seed: empire baseline'
        WHERE NOT EXISTS (SELECT 1 FROM maya_rp.population_sentiment ps
                          WHERE ps.session_id=3 AND ps.territory_id=t.id AND ps.faction_name='Setia Empire (Kingdom)');
    END LOOP;
END $$;