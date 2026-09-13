-- 096: wormholes + black holes + white holes (2026-08-15, Izzat's space-travel theory build)
--
-- THREE new travel/anomaly systems, physics-grounded:
--
-- 1. WORMHOLES (Einstein-Rosen / Morris-Thorne) — A↔B pairs that cut travel
--    ~90%. Need exotic matter (negative energy) to stay open; without upkeep
--    they DECAY and can COLLAPSE mid-transit. Aether Nexus = the hub.
--    wormholes.status: stable | decaying | collapsed
--
-- 2. BLACK HOLES — not a lane: a region. Two uses:
--      - Slingshot (Oberth effect): pass close → travel days ×0.6, but roll
--        vs hazard; fail = pulled toward event horizon (ships lost).
--      - Time dilation: 1 ship-day near the hole = N game-days outside.
--      Sector star_type = 'black_hole'.
--
-- 3. WHITE HOLES — time-reversal of a black hole (mathematically
--    self-consistent, never observed): NOTHING can enter, everything EXITS.
--    Exit-only mystery. Linked to a black hole: ships swallowed by the BH can
--    emerge here (narrative save). Sector star_type = 'white_hole'.
--    Canon hook: the unexplained Magnetar light = white-hole signature.

-- ── tables ──
CREATE TABLE IF NOT EXISTS maya_rp.wormholes (
    id                 serial PRIMARY KEY,
    session_id         integer NOT NULL DEFAULT 3,
    name               text NOT NULL,
    entry_sector_id    integer REFERENCES maya_rp.sectors(id),
    exit_sector_id     integer REFERENCES maya_rp.sectors(id),
    stability          numeric NOT NULL DEFAULT 1.0,     -- 1.0 stable → 0 collapsed
    decay_per_tick     numeric NOT NULL DEFAULT 0.01,    -- without exotic-matter upkeep
    travel_multiplier  numeric NOT NULL DEFAULT 0.10,    -- 90% travel cut
    status             text NOT NULL DEFAULT 'stable',   -- stable|decaying|collapsed
    discovered         boolean NOT NULL DEFAULT FALSE,
    notes              text
);

CREATE TABLE IF NOT EXISTS maya_rp.black_holes (
    id                    serial PRIMARY KEY,
    session_id            integer NOT NULL DEFAULT 3,
    name                  text NOT NULL,
    sector_id             integer REFERENCES maya_rp.sectors(id),
    hazard_level          numeric NOT NULL DEFAULT 0.85,   -- event-horizon roll vs this
    slingshot_multiplier  numeric NOT NULL DEFAULT 0.60,   -- travel_days × 0.6
    time_dilation_ratio   numeric NOT NULL DEFAULT 4.0,    -- 1 ship-day = 4 game-days
    status                text NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS maya_rp.white_holes (
    id               serial PRIMARY KEY,
    session_id       integer NOT NULL DEFAULT 3,
    name             text NOT NULL,
    sector_id        integer REFERENCES maya_rp.sectors(id),
    linked_black_hole_id integer REFERENCES maya_rp.black_holes(id),  -- where swallowed ships emerge
    mystery_pct      numeric NOT NULL DEFAULT 0.0,        -- 0..100 studied
    status           text NOT NULL DEFAULT 'mystery',     -- mystery|studied|breached
    notes            text
);

-- ── seed: the three exotic bodies ──
INSERT INTO maya_rp.sectors (name, x_coord, y_coord, z_coord, star_type, controlled_by, hazard_level, hidden)
VALUES
  ('The Maw',                300, 150, 2, 'black_hole', NULL,          0.90, false),
  ('Gravitas Toll',          480, 400, 2, 'black_hole', NULL,          0.80, false),
  ('White Eclipse',          380, 220, 2, 'white_hole', NULL,          0.60, true),   -- Magnetar light source
  ('Voidgate',               200, 420, 2, 'white_hole', NULL,          0.50, false)
ON CONFLICT DO NOTHING;

-- wormholes: Aether Nexus hub pair + a frontier pair
INSERT INTO maya_rp.wormholes (session_id, name, entry_sector_id, exit_sector_id, stability, decay_per_tick, travel_multiplier, status, discovered, notes)
SELECT 3, 'Aether Nexus Pair',
       e.id, x.id, 1.0, 0.005, 0.10, 'stable', TRUE,
       'The Aether Nexus ring links the core to the Rim — kept open by the megastructure.'
FROM maya_rp.sectors e, maya_rp.sectors x
WHERE e.name='Skyhold' AND x.name='Veil Drift Station'
  AND NOT EXISTS (SELECT 1 FROM maya_rp.wormholes w WHERE w.name='Aether Nexus Pair');

INSERT INTO maya_rp.wormholes (session_id, name, entry_sector_id, exit_sector_id, stability, decay_per_tick, travel_multiplier, status, discovered, notes)
SELECT 3, 'Ghostgate Thread',
       e.id, x.id, 0.55, 0.03, 0.08, 'decaying', TRUE,
       'A barely-held smuggler wormhole — feeds on exotic matter nobody pays for.'
FROM maya_rp.sectors e, maya_rp.sectors x
WHERE e.name='Ghost Thread' AND x.name='Murk Thread'
  AND NOT EXISTS (SELECT 1 FROM maya_rp.wormholes w WHERE w.name='Ghostgate Thread');

-- black holes: The Maw (big, deadly) + Gravitas Toll (safer slingshot lane)
INSERT INTO maya_rp.black_holes (session_id, name, sector_id, hazard_level, slingshot_multiplier, time_dilation_ratio, status)
SELECT 3, 'The Maw', s.id, 0.90, 0.55, 6.0, 'active'
FROM maya_rp.sectors s WHERE s.name='The Maw'
  AND NOT EXISTS (SELECT 1 FROM maya_rp.black_holes b WHERE b.name='The Maw');

INSERT INTO maya_rp.black_holes (session_id, name, sector_id, hazard_level, slingshot_multiplier, time_dilation_ratio, status)
SELECT 3, 'Gravitas Toll', s.id, 0.75, 0.65, 3.0, 'active'
FROM maya_rp.sectors s WHERE s.name='Gravitas Toll'
  AND NOT EXISTS (SELECT 1 FROM maya_rp.black_holes b WHERE b.name='Gravitas Toll');

-- white holes: White Eclipse = the Magnetar light (linked to The Maw);
-- Voidgate = unlinked mystery exit
INSERT INTO maya_rp.white_holes (session_id, name, sector_id, linked_black_hole_id, mystery_pct, status, notes)
SELECT 3, 'White Eclipse', s.id, b.id, 35.0, 'mystery',
       'The Magnetar light! Aurora Solis chase leads here. Exit-only — nothing enters.'
FROM maya_rp.sectors s, maya_rp.black_holes b
WHERE s.name='White Eclipse' AND b.name='The Maw'
  AND NOT EXISTS (SELECT 1 FROM maya_rp.white_holes w WHERE w.name='White Eclipse');

INSERT INTO maya_rp.white_holes (session_id, name, sector_id, linked_black_hole_id, mystery_pct, status, notes)
SELECT 3, 'Voidgate', s.id, NULL, 5.0, 'mystery',
       'A silent exit nobody charted. Derelict ships drift out with dead crews.'
FROM maya_rp.sectors s
WHERE s.name='Voidgate'
  AND NOT EXISTS (SELECT 1 FROM maya_rp.white_holes w WHERE w.name='Voidgate');
