-- 060: Complete materials coverage — recipe names missed in 059.
INSERT INTO maya_rp.materials (name, category, base_value, tech_tier) VALUES
('Eden Medium',   'arcane',   90.0,  4),
('Nutrient Base', 'processed', 3.0,  2),
('Pure Water',    'raw',      0.3,  1)
ON CONFLICT (name) DO NOTHING;
