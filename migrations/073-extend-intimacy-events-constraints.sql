-- 073-extend-intimacy-events-constraints.sql
-- BUGFIX: intimacy_events was never written live (arcs were updated via raw SQL),
-- so its CHECK constraints were stale:
--   1) event_type lacked 'intimacy' (process_indulgence), 'scene_roll'/'aftercare'
--      (playbook), and playbook positions (peck/sandwich/doggy/piledriver/pool_deck).
--   2) intensity cap 1-5 blocked final_score values (up to 150+).
ALTER TABLE maya_rp.intimacy_events DROP CONSTRAINT IF EXISTS intimacy_events_event_type_check;
ALTER TABLE maya_rp.intimacy_events ADD CONSTRAINT intimacy_events_event_type_check CHECK (
    event_type = ANY (ARRAY[
        'embrace','kiss','cuddle','confession','shared_night','missionary','cowgirl',
        'reverse_cowgirl','doggystyle','mount','pile_drive','standing','against_wall',
        'oral_give','oral_receive','sixty_nine','dominate','submit','bondage','edge',
        'ritual','afterglow','jealousy_scene',
        'intimacy','scene_roll','aftercare','peck','sandwich','doggy','piledriver','pool_deck'
    ])
);
ALTER TABLE maya_rp.intimacy_events DROP CONSTRAINT IF EXISTS intimacy_events_intensity_check;
ALTER TABLE maya_rp.intimacy_events ADD CONSTRAINT intimacy_events_intensity_check CHECK (intensity >= 1);
