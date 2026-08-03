-- 078-standing-orders.sql
-- Rapid Response Doctrine: one legion on 24/7 jump-ready standby, rotating
-- every 24h (Vanguard -> Bulwark -> Shadow -> Forge). King's order 2026-08-03.
CREATE TABLE IF NOT EXISTS maya_rp.standing_orders (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL,
    order_name TEXT NOT NULL,
    detail TEXT NOT NULL,
    rotation_hours INTEGER NOT NULL DEFAULT 24,
    current_unit TEXT NOT NULL,
    next_rotation_at TIMESTAMPTZ,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON maya_rp.standing_orders TO rp_engine;
GRANT USAGE, SELECT ON SEQUENCE maya_rp.standing_orders_id_seq TO rp_engine;

INSERT INTO maya_rp.standing_orders
    (session_id, order_name, detail, rotation_hours, current_unit, next_rotation_at)
VALUES
    (3, 'Rapid Response — 1 Legion Standby (24/7)',
     'One legion on jump-ready standby around the clock; rotates every 24h. Cycle: Vanguard (1.08M) -> Bulwark -> Shadow -> Forge. Fuelled, crews on alert, jump coordinates synced. Deploy on King''s word — no further approval needed.',
     24, 'Legion Vanguard', NOW() + INTERVAL '24 hours');
