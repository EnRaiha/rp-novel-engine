-- 077-dynamic-interpolation-dialogue.sql
-- 1) readable_hint (better semantic embedding text) + required_context JSONB
--    (which live-state keys the template needs for {placeholder} interpolation)
-- 2) Upgrade key templates to dynamic placeholders (railgun/plasma/treaty/market)
-- 3) NPC dialogue archetypes ([SAY: ...])
ALTER TABLE maya_rp.stream_templates ADD COLUMN IF NOT EXISTS readable_hint TEXT;
ALTER TABLE maya_rp.stream_templates ADD COLUMN IF NOT EXISTS required_context JSONB DEFAULT '[]'::jsonb;

UPDATE maya_rp.stream_templates SET
    readable_hint = 'railgun kinetic impact hypervelocity slug',
    required_context = '["attacker_name","target_name","target_armor_type"]'::jsonb,
    expanded_text = 'The hyper-dense tungsten rod fired by {attacker_name} hit {target_name} with the force of a speeding train. Their {target_armor_type} armor might as well have been paper. There was no scream — just the wet, crunching shockwave of skeletal structure instantly liquefying. The vacuum swallowed the red mist instantly.'
WHERE trigger_tag = '[HIT: RAILGUN_KINETIC]';

UPDATE maya_rp.stream_templates SET
    readable_hint = 'plasma bolt burn searing armor melt',
    required_context = '["attacker_name","target_name","weapon_name"]'::jsonb,
    expanded_text = 'The bolt of superheated energy from {attacker_name}''s {weapon_name} did not just pierce the hull; it flash-vaporized the composite plate. A spray of white slag erupted outward, searing through {target_name}''s voidsuit. The smell of scorched synthetic fabric and boiling flesh flooded the compartment.'
WHERE trigger_tag = '[HIT: PLASMA_BURN]';

UPDATE maya_rp.stream_templates SET
    readable_hint = 'diplomatic treaty signed agreement peace',
    required_context = '["faction_a","faction_b","location"]'::jsonb,
    expanded_text = 'The quantum-ink dried on the treaty, binding {faction_a} and {faction_b} in cold data. The ambient tension in the {location} dropped by a fraction. Handshakes were exchanged — firm, calculated, and devoid of warmth, but binding nonetheless. The geopolitical map had just shifted.'
WHERE trigger_tag = '[DIP: TREATY_SIGNED]';

UPDATE maya_rp.stream_templates SET
    readable_hint = 'market crash economic disaster credits fall',
    required_context = '["commodity","percentage_drop"]'::jsonb,
    expanded_text = 'The digital tickers flashed crimson across the bridge. A sudden, violent plunge in the {commodity} indices. Wealth evaporated in an instant as the value plummeted by {percentage_drop} percent. The silent hum of the economic sector was replaced by the frantic shouts of brokers trying to dump assets before the floor fell out entirely.'
WHERE trigger_tag = '[ECO: MARKET_CRASH]';

-- NPC dialogue archetypes — enforce distinct voices for minor characters
INSERT INTO maya_rp.stream_templates (trigger_tag, readable_hint, expanded_text, category) VALUES
('[SAY: STOIC_ACK]', 'stoic soldier acknowledgement flat response', '"Understood," he replied, his voice flat as steel. He did not look up from the console, but his hand moved to confirm the order.', 'dialogue'),
('[SAY: SCIENTIST_EXCITEMENT]', 'scientist excited discovery fascinating waveform', '"Fascinating!" she breathed, leaning closer to the scope. "The energy signature is completely outside known parameters. Look at this waveform!"', 'dialogue'),
('[SAY: PIRATE_THREAT]', 'pirate threat toll hull scrap sneer', '"You''re in my waters now, mate," the comms crackled with a sneer. "Pay the toll, or we scrape your hull for scrap."', 'dialogue')
ON CONFLICT (trigger_tag) DO NOTHING;

-- Reset embeddings: they must re-embed with readable_hint
UPDATE maya_rp.stream_templates SET trigger_tag_embed = NULL;
