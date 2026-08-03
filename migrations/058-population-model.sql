-- 058: Unified population model support
-- The model itself lives in modules/economy.py (grow · migrate · die · wipe).
-- This migration makes the data correct for it:

-- 1. Mastika's carrying capacity: canonical 2.5B capital world → room to grow.
--    (max_population is the data-driven override; otherwise cap = 10M × dev)
UPDATE maya_rp.territory SET max_population = 5000000000
WHERE session_id = 3 AND system_name = 'TKG Mastika';
