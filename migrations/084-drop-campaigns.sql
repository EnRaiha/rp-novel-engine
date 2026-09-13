-- 084: drop orphan campaigns table (QA PIPE-2, 2026-08-14)
-- Evidence: 0 rows, no INSERT anywhere in modules/core/scripts,
-- no SELECT anywhere. Legacy of the Rust port. Drops its 2 unused
-- indexes (idx_campaigns_session, idx_campaigns_status) automatically.
DROP TABLE IF EXISTS maya_rp.campaigns CASCADE;
