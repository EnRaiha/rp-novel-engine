-- 088-voyage-transit.sql — REAL transit-time accounting for fleet/ship movement.
-- Voyages now consume game days. Rate anchors:
--   grid (sector_connections): 24h per distance unit (engine-derived avg)
--   interstellar (light-years): 710 ly/day (canon: Serein->Mastika 28,400 ly / 40 days)

CREATE TABLE IF NOT EXISTS maya_rp.voyages (
    id            SERIAL PRIMARY KEY,
    session_id    INTEGER NOT NULL,
    voyage_name   TEXT NOT NULL,
    origin        TEXT,
    destination   TEXT,
    distance_units NUMERIC(12,3),          -- grid units (sector_connections scale)
    distance_ly   NUMERIC(14,2),           -- interstellar light-years
    travel_hours  NUMERIC(14,2),
    travel_days   NUMERIC(8,3),
    depart_day    INTEGER,
    arrive_day    INTEGER,
    status        TEXT NOT NULL DEFAULT 'in_transit',   -- in_transit / arrived / cancelled
    fleet_tag     TEXT,                                  -- e.g. 'Shadow', 'Expedition'
    ship_count    INTEGER DEFAULT 0,
    notes         TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    arrived_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_voyages_status_day ON maya_rp.voyages (session_id, status, arrive_day);
CREATE INDEX IF NOT EXISTS idx_voyages_depart   ON maya_rp.voyages (session_id, depart_day);

-- Ensure no duplicate equivalent voyage rows (same name+origin+destination+depart in same session)
CREATE UNIQUE INDEX IF NOT EXISTS idx_voyages_unique
    ON maya_rp.voyages (session_id, voyage_name, depart_day);