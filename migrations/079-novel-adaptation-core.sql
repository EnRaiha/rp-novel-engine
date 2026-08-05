-- 079-novel-adaptation-core.sql
-- Wreck Assembly + Duel System + Ship Legacy (novel adaptation, GLM pack)
-- Runs as owner: maya

-- Wreck Inventory untuk sistem assembly (novel bab 7 — "Blizzard Zero")
CREATE TABLE IF NOT EXISTS maya_rp.wreck_inventory (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES maya_rp.sessions(id),
    source_ship_id INTEGER,          -- kapal asal sebelum menjadi wreck
    name TEXT,
    tier INTEGER,
    hull INTEGER,
    power_rating INTEGER,
    sub_class TEXT,
    acquired_at TIMESTAMPTZ DEFAULT NOW(),
    status TEXT DEFAULT 'available'  -- available, used
);

-- Sistem Duel 1v1 (novel bab 13-17 — "Bald Eagle vs Blizzard Zero")
CREATE TABLE IF NOT EXISTS maya_rp.duels (
    id SERIAL PRIMARY KEY,
    session_id INTEGER REFERENCES maya_rp.sessions(id),
    player_ship_id INTEGER REFERENCES maya_rp.ships(id),
    opponent_name TEXT,
    opponent_tier INTEGER,
    opponent_hull INTEGER,
    opponent_power INTEGER,
    stakes_type TEXT,                -- credits, ship, favor
    stakes_value TEXT,
    venue TEXT,
    status TEXT DEFAULT 'pending',   -- pending, resolved
    result TEXT,                     -- victory_clean, victory_crippled, defeat_survive, defeat_destroyed
    created_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

-- Ship Legacy (medal/honor tracking — novel bab 211 "medal earned with love's life")
ALTER TABLE maya_rp.ships ADD COLUMN IF NOT EXISTS battle_honors INTEGER DEFAULT 0;
ALTER TABLE maya_rp.ships ADD COLUMN IF NOT EXISTS legacy_score INTEGER DEFAULT 0;

-- Index untuk prestasi
CREATE INDEX IF NOT EXISTS idx_wreck_inventory_session ON maya_rp.wreck_inventory(session_id, status);
CREATE INDEX IF NOT EXISTS idx_duels_session ON maya_rp.duels(session_id, status);
