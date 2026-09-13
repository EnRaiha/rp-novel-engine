-- 094-planet-types-expand.sql — Expand planet_types_catalog to full taxonomy.
INSERT INTO maya_rp.planet_types_catalog (name, description, habitability_min, habitability_max, special_events, resource_modifiers, rarity) VALUES
('Continental', 'Terrestrial with large landmasses, temperate zones, river systems.', 40, 80, '{flood_plain,ancient_riverbed,continental_shelf}', '{"food": 1.6, "alloys": 1.1, "research": 1.1}', 'common'),
('Arid', 'Semi-arid world with scrublands and seasonal rivers.', 20, 50, '{sandstorm,dry_riverbed,oasis}', '{"food": 0.8, "fuel": 1.1, "alloys": 1.2}', 'common'),
('Ice World', 'Global cryosphere with possible subsurface oceans.', 0, 20, '{cryo_deposits,subsurface_ocean,ice_spikes}', '{"food": 0.3, "fuel": 1.4, "alloys": 1.0, "research": 1.3}', 'uncommon'),
('Frozen', 'Ancient ice crust, no active biosphere.', 0, 5, '{frozen_archives,ice_caves,permafrost_vault}', '{"food": 0, "fuel": 1.2, "alloys": 0.8, "research": 1.1}', 'common'),
('Rocky', 'Cratered rocky body with heavy metals.', 0, 10, '{meteor_impact,mineral_vein,crater_lake}', '{"food": 0, "fuel": 0.6, "alloys": 1.6}', 'common'),
('Molten', 'Lava seas, tectonic fury, young crust.', 0, 0, '{lava_tube,eruption,rare_crystals}', '{"food": 0, "fuel": 1.8, "alloys": 2.2}', 'uncommon'),
('Toxic', 'Venusian crushing atmosphere, acid clouds.', 0, 0, '{acid_storms,metal_rain,atmospheric_harvest}', '{"food": 0, "fuel": 1.6, "alloys": 0.8, "research": 1.2}', 'uncommon'),
('Ringed Gas Giant', 'Gas giant with spectacular rings and many moons.', 0, 0, '{shepherd_moon,ring_harvest,storm_cell}', '{"fuel": 3.5, "alloys": 0.3, "research": 1.7}', 'rare'),
('Ice Giant', 'Methane haze, supercritical water oceans.', 0, 0, '{methane_lake,deep_ocean_vent,atmospheric_harvest}', '{"fuel": 2.5, "alloys": 0.2, "research": 1.4}', 'rare'),
('Dwarf Planet', 'Small icy/rocky body, trans-system.', 0, 5, '{mineral_vein,frozen_archives,meteor_impact}', '{"food": 0, "fuel": 0.4, "alloys": 1.0}', 'common'),
('Asteroid Field', 'Dense belt, mining-rich, navigational hazard.', 0, 0, '{mineral_vein,rare_crystals,hidden_base}', '{"food": 0, "fuel": 0.8, "alloys": 2.0, "research": 0.8}', 'common'),
('Carbon World', 'Diamond crust, graphite plains, hydrocarbon seas.', 0, 0, '{diamond_mine,hydrocarbon_sea,graphite_cavern}', '{"food": 0, "fuel": 1.2, "alloys": 2.4, "research": 1.0}', 'rare'),
('Crystal World', 'Silicate spires, reflective surfaces, exotic minerals.', 0, 10, '{crystal_cavern,resonance_spire,exotic_mineral}', '{"food": 0, "fuel": 0.5, "alloys": 1.8, "research": 1.6}', 'rare'),
('Habitat Station', 'Orbital habitat — artificial world.', 40, 80, '{hydroponics_ring,docking_hub,ai_core}', '{"food": 1.0, "fuel": 0.5, "alloys": 0.8, "research": 1.2}', 'uncommon'),
('Star', 'Stellar primary — the system sun.', 0, 0, '{solar_flare,coronal_mass_ejection,harvestable_plasma}', '{"fuel": 0, "alloys": 0, "research": 0}', 'unique')
ON CONFLICT (name) DO NOTHING;