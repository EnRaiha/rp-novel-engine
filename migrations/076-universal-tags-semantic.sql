-- 076-universal-tags-semantic.sql
-- 1) Universal narrative tags: economy / diplomacy / science / exploration / social
-- 2) trigger_tag_embed vector column + HNSW index for semantic fallback matching
--    (interceptor tier 2: short LLM hints -> nearest template tag)
ALTER TABLE maya_rp.stream_templates ADD COLUMN IF NOT EXISTS trigger_tag_embed vector(768);
CREATE INDEX IF NOT EXISTS idx_stream_templates_embed
    ON maya_rp.stream_templates USING hnsw (trigger_tag_embed vector_cosine_ops);

INSERT INTO maya_rp.stream_templates (trigger_tag, expanded_text, category) VALUES
-- ECONOMY
('[ECO: MARKET_CRASH]', 'The digital tickers flashed crimson across the bridge. A sudden, violent plunge in the trade indices. Wealth evaporated in an instant, and the silent hum of the economic sector was replaced by the frantic shouts of brokers trying to dump assets before the floor fell out entirely.', 'economy'),
('[ECO: TRADE_BOOM]', 'The weekly ledger glowed green. A surge of rare earths and refined alloys had flooded the market. The treasury bulked up, and the merchant guilds were practically throwing credits at the Crown for a chance to expand their operations.', 'economy'),
-- DIPLOMACY & POLITICS
('[DIP: TREATY_SIGNED]', 'The quantum-ink dried on the treaty, binding the factions in cold data. The ambient tension in the chamber dropped by a fraction. Handshakes were exchanged — firm, calculated, and devoid of warmth, but binding nonetheless. The geopolitical map had just shifted.', 'diplomacy'),
('[DIP: BETRAYAL]', 'The encrypted transmission cut out. The coordinates were a lie. The realization hit the bridge crew like a kinetic impact: they had been sold out. The diplomatic channel was not a bridge; it was a trapdoor.', 'diplomacy'),
-- SCIENCE & RESEARCH
('[SCI: TECH_BREAKTHROUGH]', 'The containment field hummed with a new, stable resonance. The lead scientist wiped sweat from her brow, eyes wide with the manic glow of success. The theoretical had become operational. The fleet had just leaped a decade forward in engineering.', 'science'),
('[SCI: ANOMALY_DETECTED]', 'The sensor array screamed with static. A massive gravitational lensing event registered on the edge of the system. The data did not match any known celestial body. It was pulling at the fabric of space-time itself. Something vast was watching.', 'science'),
-- EXPLORATION & CELESTIAL
('[EXP: NEW_SYSTEM]', 'The viewport shifted from the blinding white of FTL to the velvet dark of uncharted space. Three gas giants loomed in the distance, their rings catching the pale light of a white dwarf. No navigational beacons. No debris. Pure, untouched frontier.', 'exploration'),
('[EXP: DERELICT_FOUND]', 'A cold, dead hulk drifted in the void. The hull was scarred with plasma burns older than the war. No life signs, no running lights — just the ghost of a ship that failed to come home, holding secrets in its frozen corridors.', 'exploration'),
-- SOCIAL & CREW
('[SOC: MORALE_LOW]', 'The mess hall was silent. Trays scraped against metal, but no one spoke. The eyes of the crew were downcast, hollowed by exhaustion and the creeping weight of the war. The ship felt less like a vessel and more like a tomb drifting through the stars.', 'social'),
('[SOC: CELEBRATION]', 'A roar went up from the lower decks. The intercom crackled with laughter and off-key singing. For one night, the war was a million miles away. The booze flowed, the music pounded, and the crew remembered what it meant to be alive.', 'social')
ON CONFLICT (trigger_tag) DO NOTHING;
