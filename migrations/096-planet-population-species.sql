-- 096-planet-population-species.sql — Population composition by SPECIES per planet (Stellaris-style pops).
-- Each planet's population breaks down into species groups. Population is resource-driven and
-- faction-INDEPENDENT; species composition reflects who actually lives there.

CREATE TABLE IF NOT EXISTS maya_rp.planet_population (
    id          SERIAL PRIMARY KEY,
    session_id  INTEGER NOT NULL,
    planet_id   INTEGER NOT NULL REFERENCES maya_rp.planets(id),
    species_id  INTEGER REFERENCES maya_rp.species_catalog(id),
    species_name TEXT NOT NULL,
    count       BIGINT NOT NULL DEFAULT 0,
    pct         NUMERIC(6,2) DEFAULT 0,      -- share of planet population
    dominant    BOOLEAN DEFAULT FALSE,
    updated_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (session_id, planet_id, species_id)
);
CREATE INDEX IF NOT EXISTS idx_planet_pop_planet ON maya_rp.planet_population (session_id, planet_id);
CREATE INDEX IF NOT EXISTS idx_planet_pop_species ON maya_rp.planet_population (session_id, species_name);