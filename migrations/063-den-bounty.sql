-- 063: Harta Karun — the Den as treasure.
-- 1. Bounty poster on The Den (paid when the faction is defeated).
INSERT INTO maya_rp.pirate_bounties (pirate_faction_id, bounty_amount, last_updated)
VALUES (6, 2000000, NOW())


-- 2. Hoards start meaty — the Den has been raiding for months.
UPDATE maya_rp.pirate_bases SET treasury = 750000 WHERE id = 1;
UPDATE maya_rp.pirate_bases SET treasury = 450000 WHERE id = 2;
