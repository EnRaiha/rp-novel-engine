-- 090-malam-kiri-pregnant.sql — GM correction: Malam + Kiri ARE pregnant (hidden from system).
-- Same-week impregnation attempts as the births of Cahaya (7) + Elanor (8). These two
-- were completely invisible to the engine — registering now per Izzat.

-- Malam (id 66) — pregnant, hidden origin
INSERT INTO maya_rp.pregnancies
    (session_id, mother_id, mother_name, father_name, conceived_game_day, due_game_day,
     gestation_days, trimester, status, notes)
VALUES
    (3, 66, 'Malam', 'King Izzat', 160, 430, 270, 1, 'active',
     'Same-week impregnation wave as Cahaya + Elanor. Was TOTALLY hidden from system — GM correction 2026-08-10.'),
    (3, 61, 'Kiri',  'King Izzat', 160, 430, 270, 1, 'active',
     'Same-week impregnation wave as Cahaya + Elanor. The First Voice — hidden, now registered. GM correction 2026-08-10.')
ON CONFLICT DO NOTHING;

-- Event log
INSERT INTO maya_rp.events (session_id, event_type, title, description, happened_at)
VALUES (3, 'register',
        '⭐ GM CORRECTION — MALAM + KIRI PREGNANT (HIDDEN PAIR REGISTERED)',
        'Same-week impregnation wave as the births of Cahaya (Celestine) + Elanor (Maya Khatri). '
        'Malam (id 66, Third Gate expedition) + Kiri (id 61, The First Voice) were '
        'completely hidden from the system — both now registered as pregnant (T1, due ~D430).',
        now());