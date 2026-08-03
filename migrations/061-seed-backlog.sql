-- 061: Seed backlog completion — faction minds, diplomacy, intel, ops
-- Closes every remaining "not seeded" gap from the 31 Jul module audit (§5).
-- Tier 1: faction AI personalities, missing Setia relations, treaties, envoys
-- Tier 2: spy networks, pirate bases, science missions, research labs,
--         infrastructure instances, megastructure (Stellar Forge @ Mastika)
-- Tier 3: chekhov elements, narrative seeds, C4 labor slaves, diplomatic actions

-- ── 1. FACTION AI PERSONALITIES (9 minds) ────────────────────────────────
INSERT INTO maya_rp.faction_ai_state
    (session_id, faction_name, aggression, expansionism, xenophobia, militarism, economic_focus)
VALUES
    (3, 'Setia Empire (Kingdom)', 35, 60, 25, 55, 70),
    (3, 'Vein Collective',        20, 30, 60, 25, 75),
    (3, 'Iron Concord',           40, 55, 35, 60, 55),
    (3, 'The Silent Choir',       15, 25, 75, 20, 40),
    (3, 'Ghost Signal',           30, 20, 80, 30, 30),
    (3, 'The Den',                95, 70, 45, 85, 20),
    (3, 'Free Ports Alliance',    25, 35, 30, 30, 70),
    (3, 'Exodus Fleet',           15, 20, 40, 25, 50),
    (3, 'Lost Colonies',          35, 15, 85, 50, 35);

-- ── 2. MISSING SETIA RELATIONS (4 pairs) ─────────────────────────────────
INSERT INTO maya_rp.faction_relations
    (session_id, faction_a, faction_b, standing, trade_volume, military_tension, last_interaction)
VALUES
    (3, 1, 3, 'friendly',   12000, 0.1, 'Joint patrols and defense pact'),
    (3, 1, 2, 'friendly',    8000, 0.1, 'Vein mining and fuel agreement'),
    (3, 1, 4, 'suspicious',   200, 0.4, 'Choir observes recovered space; strange signals'),
    (3, 1, 5, 'suspicious',     0, 0.2, 'Ghost Signal defeated — systems absorbed');

-- ── 3. TREATIES (3) ──────────────────────────────────────────────────────
INSERT INTO maya_rp.treaties
    (name, treaty_type, faction_a_id, faction_b_id, signed_at, duration_days, expires_at, active, terms, created_by)
VALUES
    ('Concord Joint Patrol Treaty', 'defense', 1, 3, NOW(), 365, NOW() + interval '365 days', TRUE,
     '["Joint patrols of shared borders", "Mutual defense notification", "No first strike"]'::jsonb, 'crown'),
    ('Vein Mining & Fuel Agreement', 'economic', 1, 2, NOW(), 365, NOW() + interval '365 days', TRUE,
     '["Vein passage rights", "Mining royalties to crown", "Fuel purchase preference"]'::jsonb, 'crown'),
    ('Free Ports Trade Accord', 'trade', 1, 7, NOW(), 365, NOW() + interval '365 days', TRUE,
     '["Open commerce lanes", "Port access for Setia hulls", "Pirate interdiction cooperation"]'::jsonb, 'crown');

-- ── 4. ENVOYS (3 posted) ─────────────────────────────────────────────────
INSERT INTO maya_rp.envoys
    (faction_id, target_faction_id, envoy_name, mission_type, started_at, duration_days, status)
VALUES
    (1, 3, 'Sara Valdez',      'diplomatic',       NOW(), 30, 'active'),
    (1, 2, 'Isha Nakamura',    'trade_negotiation', NOW(), 30, 'active'),
    (1, 7, 'Cassandra Vale',    'commerce',          NOW(), 30, 'active');

-- ── 5. SPY NETWORKS (2) ──────────────────────────────────────────────────
INSERT INTO maya_rp.spy_networks
    (faction_id, target_faction_id, established_at, active, agents, effectiveness, notes)
VALUES
    (1, 6, NOW(), TRUE, 12, 70, 'Nyx Blackwater web — Den movement watch'),
    (1, 4, NOW(), TRUE,  5, 45, 'Silent Choir observation ring');

-- ── 6. PIRATE BASES (2 — The Den) ────────────────────────────────────────
INSERT INTO maya_rp.pirate_bases
    (faction_id, system_id, name, hidden, defenses, treasury, status)
VALUES
    (6, 1127, 'Den Fringe Base — TKG Approaches', TRUE,  80, 500000, 'active'),
    (6, 1131, 'Den Raid Staging — 5-0',           FALSE, 60, 300000, 'active');

-- ── 7. SCIENCE MISSIONS (3 of 10 vessels deployed) ───────────────────────
INSERT INTO maya_rp.science_missions
    (session_id, ship_id, sector_id, mission_type, status, progress, target_progress, scientist_id, research_reward, started_at)
VALUES
    (3, 1013, NULL, 'bisik_survey',       'active', 0, 100, NULL, 500, NOW()),
    (3, 1014, NULL, 'ghost_decryption',   'active', 0, 100, NULL, 450, NOW()),
    (3, 1015, NULL, 'vein_mapping',       'active', 0, 100, NULL, 400, NOW());

-- ── 8. RESEARCH LABS (2) ─────────────────────────────────────────────────
INSERT INTO maya_rp.research_labs (colony_id, name, level, research_field, research_rate, created_at)
VALUES
    (1, 'Pelabuhan Pharma Lab',   1, 'biotech',        50, NOW()),
    (3, 'Waja Metallurgy Lab',    1, 'material_science', 40, NOW());

-- ── 9. INFRASTRUCTURE INSTANCES (6 first builds) ─────────────────────────
INSERT INTO maya_rp.infrastructure_instances
    (session_id, infrastructure_type_id, territory_id, sector_id, name, level, status, built_at, upgrades_applied, production_bonus)
VALUES
    (3,  1, 170, NULL, 'Mastika Surface Mine',    1, 'operational', NOW(), '[]'::jsonb, 0.05),
    (3,  2, 169, NULL, 'Waja Deep Core Mine',     1, 'operational', NOW(), '[]'::jsonb, 0.05),
    (3,  6, 172, NULL, 'Pelabuhan Basic Refinery', 1, 'operational', NOW(), '[]'::jsonb, 0.05),
    (3, 20, 167, NULL, 'Cendana Hydroponic Farm',  1, 'operational', NOW(), '[]'::jsonb, 0.05),
    (3, 17, 168, NULL, 'Bayu Assembly Plant',      1, 'operational', NOW(), '[]'::jsonb, 0.05),
    (3, 14, 170, NULL, 'Mastika Trade Station',    1, 'operational', NOW(), '[]'::jsonb, 0.05);

-- ── 10. MEGASTRUCTURE — Stellar Forge (the Iron Crane build) ─────────────
INSERT INTO maya_rp.megastructure_construction
    (session_id, megastructure_type_id, sector_id, territory_id, current_phase, progress_pct,
     started_at, estimated_completion, status, resources_allocated)
VALUES
    (3, 5, NULL, 170, 1, 40, NOW() - interval '5 days', NOW() + interval '120 days', 'construction',
     '{"alloys": 1500000, "credits": 2000000, "fuel": 500000}'::jsonb);

-- ── 11. CHEKHOV ELEMENTS (5 planted) ─────────────────────────────────────
INSERT INTO maya_rp.chekhov_elements
    (session_id, element_type, description, importance, introduced_game_day, payoff_deadline, payoff_method, status)
VALUES
    (3, 'burn_scar',      'The Burn Scar — endgame threat. Choir connected. Do not surface early.',      9.7, 20, 45, 'reveal_via_choir_arc',      'pending'),
    (3, 'bisik_anomaly',  'Bisik subsurface signal — precursor mystery in our backyard.',                7.0, 20, 35, 'investigation_complete',   'pending'),
    (3, 'voss_markers',   'Voss genetic markers — blood tests pending for Rika, Celestine, Hanum.',      5.0, 20, 40, 'blood_test_complete',      'pending'),
    (3, 'choir_watch',    'Silent Choir observing recovered space — strange signals.',                   6.0, 20, 50, 'diplomacy_progress',       'pending'),
    (3, 'ghost_decryption','Ghost Signal data — decryption research needed.',                            7.0, 20, 45, 'research_complete',        'pending');

-- ── 12. NARRATIVE SEEDS (5) ──────────────────────────────────────────────
INSERT INTO maya_rp.narrative_seeds
    (session_id, seed_type, content, planted_at_game_day, payoff_condition, payoff_event_template, payoff_game_day, status, foreshadow_count, max_foreshadows)
VALUES
    (3, 'arc',        'Silent Choir approach — Sera as bridge, Isha as translator.',       20, 'choir_diplomacy_started', 'choir_arc',     30, 'pending', 0, 3),
    (3, 'threat',     'The Den consolidating — pirate council active, mobile command ship.',20, 'den_escalation',         'den_crisis',    25, 'pending', 0, 3),
    (3, 'mystery',    'Bisik anomaly — survey deployed (KB Seeker-01).',                   20, 'survey_launched',         'bisik_reveal',  30, 'pending', 0, 3),
    (3, 'opportunity','Exodus Fleet asylum request — supplies in exchange for intel.',     20, 'asylum_granted',          'exodus_alliance',25, 'pending', 0, 3),
    (3, 'character',  'Zara El-Amin lab station — the plain box at Heaven Yard.',          20, 'lab_completed',           'lab_breakthrough',15,'pending', 0, 3);

-- ── 13. C4 LABOR CORPS (5 representative rows; 420 total narrative) ──────
INSERT INTO maya_rp.slaves
    (session_id, name, species, gender, age, strength, intelligence, loyalty, health,
     assigned_to, assigned_id, role, acquired_at, acquired_from, cost, status)
VALUES
    (3, 'C4-001', 'human', 'M', 34, 55, 40, 60, 70, 'C4 Labor Corps', NULL, 'labor', NOW(), 'pirate_screening', 0, 'working'),
    (3, 'C4-002', 'human', 'M', 29, 60, 35, 55, 75, 'C4 Labor Corps', NULL, 'labor', NOW(), 'pirate_screening', 0, 'working'),
    (3, 'C4-003', 'human', 'F', 41, 45, 50, 65, 70, 'C4 Labor Corps', NULL, 'labor', NOW(), 'pirate_screening', 0, 'working'),
    (3, 'C4-004', 'xeno',  'M', 27, 70, 30, 50, 80, 'C4 Labor Corps', NULL, 'labor', NOW(), 'pirate_screening', 0, 'working'),
    (3, 'C4-005', 'human', 'F', 38, 50, 45, 70, 65, 'C4 Labor Corps', NULL, 'labor', NOW(), 'pirate_screening', 0, 'working');

-- ── 14. DIPLOMATIC ACTIONS (3 history rows) ──────────────────────────────
INSERT INTO maya_rp.diplomatic_actions
    (action_type, actor_faction_id, target_faction_id, treaty_id, details, happened_at, success, response)
VALUES
    ('treaty_signed', 1, 3, (SELECT id FROM maya_rp.treaties WHERE name='Concord Joint Patrol Treaty'),
     '["Joint patrols established", "Defense pact signed"]'::jsonb, NOW(), TRUE, 'accepted'),
    ('treaty_signed', 1, 2, (SELECT id FROM maya_rp.treaties WHERE name='Vein Mining & Fuel Agreement'),
     '["Mining and fuel agreement", "Passage rights secured"]'::jsonb, NOW(), TRUE, 'accepted'),
    ('treaty_signed', 1, 7, (SELECT id FROM maya_rp.treaties WHERE name='Free Ports Trade Accord'),
     '["Trade accord", "Port access for Setia hulls"]'::jsonb, NOW(), TRUE, 'accepted');

-- ── 15. CABINET MEETINGS (2 history rows) ────────────────────────────────
INSERT INTO maya_rp.cabinet_meetings
    (session_id, meeting_type, agenda, attendees, decisions, cohesion, minutes, convened_at)
VALUES
    (3, 'regular', 'Reconstruction Bond — allocation of the 527M reserve',
     '["14 queens", "Hariz officiating"]'::jsonb,
     '["Bond waves 1-3 closed", "Wave 4 deferred pending auction timing"]'::jsonb,
     85, 'Bond structure approved. Wave 4 held until the pirate fleet auction clears.',
     NOW() - interval '3 days'),
    (3, 'regular', 'Fleet review — captured hulls and pirate screening',
     '["14 queens", "Valdez", "Khatri"]'::jsonb,
     '["58 hulls integrated", "180 executed / 420 C4 / 60 trained"]'::jsonb,
     80, 'Screening closed. Internal ship market framework approved.',
     NOW() - interval '1 day');
