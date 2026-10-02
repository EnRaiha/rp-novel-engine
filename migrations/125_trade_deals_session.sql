-- ═══════════════════════════════════════════════════════════════════
-- FACTIONS TRADE DEALS BELONG TO A CAMPAIGN
--
-- The table had no session marker, and `modules/economy.gate_toll_income` sums it without a filter,
-- so a session with no map and no trade network still reported treasury income: session 5, whose
-- world is empty, read 14,700,000 credits from the trades of the frozen campaign of 2026-08-15.
--
-- Those five deals are Setia's network in session 3, so the column is added with default 3 and every
-- existing row belongs there. A campaign-owned table needs the marker the code should have been
-- filtering on all along.
-- ═══════════════════════════════════════════════════════════════════
BEGIN;
SET search_path TO maya_rp;

ALTER TABLE faction_trade_deals ADD COLUMN IF NOT EXISTS session_id integer NOT NULL DEFAULT 3;

CREATE INDEX IF NOT EXISTS faction_trade_deals_session_idx ON faction_trade_deals (session_id);

COMMENT ON COLUMN faction_trade_deals.session_id IS
  'Campaign that signed the deal. Session 3 rows predate this column and are the frozen campaign''s';

COMMIT;
