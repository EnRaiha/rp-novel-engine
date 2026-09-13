-- 091-sera-roman-legions.sql — Sera's 4 FULL Roman legions, paced over 1080 days.
-- Time disturbance caused legionnaires to be queued early; corrected via this schedule.
-- Roman doctrine per canon (rp-current-session line 544): century → cohort → legion.
-- Canon standard (line 505): 1 legion = 100 warships ±20% + 20 support = ~120 hulls.

-- Structure (Sera Roman doctrine):
--   1 Century = 6 hulls
--   1 Cohort  = 2 Centuries  = 12 hulls
--   1 Legion  = 10 Cohorts   = 120 hulls (100 warships + 20 support)
--   4 Legions = 480 hulls over 1080 days (270d/legion)
--
-- Legion names (Roman-style):
--   LEGIO I   PRIMA   (First)      — completing day 1323+270   = D1593
--   LEGIO II  SECUNDA (Second)     — completing day 1323+540   = D1863
--   LEGIO III TERTIA  (Third)      — completing day 1323+810   = D2133
--   LEGIO IV  QUARTA  (Fourth)     — completing day 1323+1080  = D2403

INSERT INTO maya_rp.build_queue
    (session_id, project_name, project_type, status, build_time_days,
     alloy_cost, credit_cost, notes, created_at)
VALUES
    (3, 'LEGIO I PRIMA — Full Legion (10 cohorts / 120 hulls: 100 warships + 20 support, Sera Roman doctrine)',
     'legion_build', 'queued', 270, 300000, 600000000,
     'Sera Roman legion #1/4 · century(6)→cohort(12)→legion(120) · paced 270d · completes ~D1593', now()),
    (3, 'LEGIO II SECUNDA — Full Legion (10 cohorts / 120 hulls: 100 warships + 20 support, Sera Roman doctrine)',
     'legion_build', 'queued', 540, 300000, 600000000,
     'Sera Roman legion #2/4 · paced 540d · completes ~D1863', now()),
    (3, 'LEGIO III TERTIA — Full Legion (10 cohorts / 120 hulls: 100 warships + 20 support, Sera Roman doctrine)',
     'legion_build', 'queued', 810, 300000, 600000000,
     'Sera Roman legion #3/4 · paced 810d · completes ~D2133', now()),
    (3, 'LEGIO IV QUARTA — Full Legion (10 cohorts / 120 hulls: 100 warships + 20 support, Sera Roman doctrine)',
     'legion_build', 'queued', 1080, 300000, 600000000,
     'Sera Roman legion #4/4 · paced 1080d · completes ~D2403', now());

-- Event
INSERT INTO maya_rp.events (session_id, event_type, title, description, happened_at)
VALUES (3, 'build',
        '🏛️ SERA''S 4 FULL ROMAN LEGIONS — PACED 1080 DAYS',
        'Time disturbance corrected: legionnaires queued early. Sera now raises 4 full Roman legions '
        '(century=6 hulls → cohort=12 → legion=120: 100 warships + 20 support per canon). '
        'LEGIO I PRIMA (~D1593) · II SECUNDA (~D1863) · III TERTIA (~D2133) · IV QUARTA (~D2403). '
        'Total 480 hulls over 1080 days. Distinct from the recent 16-build specialist queue.',
        now());