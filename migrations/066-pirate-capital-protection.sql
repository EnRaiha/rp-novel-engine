-- 066: King's rule — pirates pop up anywhere, but never near the capital.
-- pirate_zones get a `protected` flag; protected zones never spawn pirate fleets.
ALTER TABLE maya_rp.pirate_zones ADD COLUMN IF NOT EXISTS protected BOOLEAN NOT NULL DEFAULT FALSE;

-- Current fringe zones (Systems 1-5) are all legal spawn points — untouched.
-- The capital (TKG Mastika) has no zone of its own; raids exclude it in code.
