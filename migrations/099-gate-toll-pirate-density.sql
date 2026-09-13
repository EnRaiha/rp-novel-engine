-- 099: gate tolls + pirate density per lane (2026-08-15, Izzat's canon)
--
-- "The mainstream path by gate at Setia is the most used because it only has
-- appropriate fair, less pirate, low risk." — Izzat
--
-- The Setia gates are the HIGHWAY of the nebula:
--   · toll_credits   — fair toll per crossing (Setia maintains the gates;
--                      that upkeep is why pirates are thin there)
--   · pirate_density — 0..1 encounter chance per transit on that lane type
--
-- Canon values (fair = affordable enough that traders still prefer the gate):
--   gate            toll 25,000C · pirates 0.05  (garrisoned, patrolled)
--   standard        0 toll       · pirates 0.15  (open lanes, some risk)
--   hazardous       0 toll       · pirates 0.30  (bad space, worse company)
--   unstable        0 toll       · pirates 0.45  (lane barely holds together)
--   hidden_thread   0 toll       · pirates 0.65  (no guards = pirate bait;
--                    handled by the act-driven interception model in voyage.py)
--   void / wormhole / slingshot — exotic transits have their own risk models
--                    (void 20% hazard, wormhole collapse, slingshot horizon).

ALTER TABLE maya_rp.sector_connections
  ADD COLUMN IF NOT EXISTS toll_credits BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS pirate_density NUMERIC NOT NULL DEFAULT 0.15;

-- Setia gates: the fair, safe highway
UPDATE maya_rp.sector_connections
   SET toll_credits = 25000, pirate_density = 0.05
 WHERE lane_type = 'gate';

UPDATE maya_rp.sector_connections SET pirate_density = 0.15 WHERE lane_type = 'standard';
UPDATE maya_rp.sector_connections SET pirate_density = 0.30 WHERE lane_type = 'hazardous';
UPDATE maya_rp.sector_connections SET pirate_density = 0.45 WHERE lane_type = 'unstable';
UPDATE maya_rp.sector_connections SET pirate_density = 0.65 WHERE lane_type = 'hidden_thread';

-- voyage lane_type + toll record
ALTER TABLE maya_rp.voyages
  ADD COLUMN IF NOT EXISTS lane_type TEXT NOT NULL DEFAULT 'standard',
  ADD COLUMN IF NOT EXISTS toll_paid BIGINT NOT NULL DEFAULT 0;
