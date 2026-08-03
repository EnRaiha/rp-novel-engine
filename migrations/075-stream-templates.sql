-- 075-stream-templates.sql
-- Narrative templating: LLM emits compact [CATEGORY: TAG] hints; the engine
-- expands them from PG before display — consistent lore, token efficiency,
-- environment/combat/intimacy descriptions editable without prompt changes.
CREATE TABLE IF NOT EXISTS maya_rp.stream_templates (
    id SERIAL PRIMARY KEY,
    trigger_tag TEXT UNIQUE NOT NULL,
    expanded_text TEXT NOT NULL,
    category VARCHAR(50) NOT NULL DEFAULT 'environment',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON maya_rp.stream_templates TO rp_engine;
GRANT USAGE, SELECT ON SEQUENCE maya_rp.stream_templates_id_seq TO rp_engine;

INSERT INTO maya_rp.stream_templates (trigger_tag, expanded_text, category) VALUES
-- environment (mirrors LOCATION_MOODS in modules/romance.py)
('[ENV: HEAVEN_POOL]', 'The Heaven pool glows with a starfield wall, fusion-fed heat, and rising steam. The water laps gently against the deck.', 'environment'),
('[ENV: BRIDGE]', 'The bridge hums in dim command lighting. A starfield stretches endlessly through the main viewport.', 'environment'),
('[ENV: QUARTERS]', 'Warm personal quarters, soft ambient light, the muffled sound of the ship breathing around you.', 'environment'),
('[ENV: OBSERVATION]', 'Nebula glow pours through the observation glass. The void is silent and vast.', 'environment'),
('[ENV: GARDEN]', 'The bioluminescent Eden dome runs its night cycle. Water drips, leaves rustle, the air is thick with green.', 'environment'),
('[ENV: FORGE]', 'Forge-fire glow, amber heat. Distant clanging and thermal hiss echo off the yard walls.', 'environment'),
('[ENV: WRECKAGE]', 'Emergency lights stutter over debris silence. Creaking metal, static, and the smell of burnt circuitry.', 'environment'),
('[ENV: VOID]', 'Total darkness except each other. Only breathing, only the two of you against the infinite.', 'environment'),
-- combat / horror (visceral register — TKG lore standard)
('[HIT: PLASMA_BURN]', 'The plasma bolt did not just pierce the armor; it flash-vaporized the composite plate. A spray of superheated white slag erupted outward, searing through the voidsuit beneath. The smell of scorched fabric and boiled flesh flooded the compartment.', 'combat'),
('[HIT: RAILGUN_KINETIC]', 'The hyper-dense tungsten rod hit with the force of a speeding train. There was no scream — just the wet, crunching shockwave of skeletal structure instantly liquefying. The vacuum swallowed the red mist, leaving only a spinning, fragmented torso where a soldier had been a second before.', 'combat'),
('[HORROR: BUG_AMBUSH]', 'The vent grate exploded downward. Chitinous limbs — slick with something viscous and yellow — speared through the smoke. Before the marine could raise his rifle, a serrated mandible clamped around his shoulder, shearing through the collarbone with a sickening, grinding pop.', 'horror'),
('[INJURY: DECOMPRESSION]', 'The hull breach screamed. The pressure differential ripped the air from his lungs. Capillaries in his eyes burst like tiny red fireworks, and the freezing vacuum crystallized the moisture on his tongue as he was dragged toward the void.', 'horror'),
-- intimacy (DS Register — mirrors SENSORY_LEXICON in modules/romance.py)
('[SENSE: PECK]', 'A fleeting spark across the room, the ghost of warmth, a soft sharp intake of breath.', 'intimacy'),
('[SENSE: SANDWICH]', 'Two bodies flanking, trapping heat. Overlapping heartbeats, whispered names lost in the steam.', 'intimacy'),
('[SENSE: DOGGY]', 'The arch of the spine, surrendering the face. Muffled cries, depth and power, the loss of control.', 'intimacy'),
('[SENSE: MISSIONARY]', 'Eye contact — the vow position. Synchronized breathing, the breaking of names, total weight, total acceptance.', 'intimacy'),
('[SENSE: PILEDRIVER]', 'Gravity doing the work, folded and helpless. Staccato ah-ah-ahh breaking the rhythm — the defeat of the mind, the breaker.', 'intimacy'),
('[SENSE: POOL_DECK]', 'Wet marble and silver hair fanned out. Cries echoing off the starfield wall, cool stone and warm water.', 'intimacy'),
-- system
('[SYSTEM: DB_ERROR]', '### Engine Connection Error\nThe system failed to connect to PostgreSQL. Check DSN and network.', 'system')
ON CONFLICT (trigger_tag) DO NOTHING;
