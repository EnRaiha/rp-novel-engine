-- 088: seed events across ALL channels (2026-08-14)
-- Fills every event channel with fresh, staggered world-noise so the
-- briefing/ML-importance layer has a living universe to rank.
INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance)
VALUES
  -- pirate channel
  (3, NOW() - INTERVAL '6 hours', 'pirate', 'Maw Teeth Fleet raids border convoy',
   'A Setia freight convoy lost three hulls to the Maw Teeth Fleet near the rim. Survivors report the raiders flying a new black-and-bone pennant.', '["pirate","wild","raid"]', 4),
  (3, NOW() - INTERVAL '30 hours', 'pirate', 'Starlight Reavers sell captured cargo',
   'Starlight Reavers auctioned stolen cargo in a Free Port back alley. Buyers came and went, hooded, in the same hour.', '["pirate","trade","rumour"]', 2),
  (3, NOW() - INTERVAL '3 days', 'pirate', 'Nightfall Butchers leave a calling card',
   'A butchered probe returned to us, its hull carved with the Nightfall mark and a single word: SOON.', '["pirate","threat","nightfall"]', 5),
  -- military channel
  (3, NOW() - INTERVAL '8 hours', 'military', 'Offensive Fleet completes readiness exercise',
   'The readiness exercise closed with a 92% pass rate. General of the North wants a live-fire drill next.', '["military","fleet","north"]', 3),
  (3, NOW() - INTERVAL '2 days', 'military', 'Legion Paladin hull inspection',
   'Legion Paladin passed its hull inspection — two turret mounts flagged for refit at Heaven Yard.', '["military","legion","paladin"]', 2),
  -- economy channel
  (3, NOW() - INTERVAL '10 hours', 'economy', 'Luxury goods price spike',
   'Luxury goods traded 18% above base on Free Port exchanges. Analysts blame a wedding season in the north.', '["economy","market","luxury"]', 2),
  (3, NOW() - INTERVAL '26 hours', 'economy', 'He-3 fuel glut',
   'A He-3 surplus depressed fuel prices 9%. Smugglers are reportedly stockpiling in expectation of a war premium.', '["economy","fuel","market"]', 2),
  -- beauty channel
  (3, NOW() - INTERVAL '12 hours', 'beauty', 'New beauty catalog entry: Sanguis Shoal',
   'Scouts forwarded a catalog draft on Sanguis Shoal, pirate queen of the Crimson Shoals. The Forge has requested the file.', '["beauty","catalog","pirate"]', 3),
  -- rumour channel
  (3, NOW() - INTERVAL '5 hours', 'rumour', 'The King shot something in the dark',
   'Dock workers swear the Nebular Sniper Ray fired at a point behind the royal shuttle. The rumors are already better than the truth.', '["rumour","sniper","king"]', 1),
  (3, NOW() - INTERVAL '20 hours', 'rumour', 'A pirate king died this week',
   'Free Port chatter: a pirate king fell to a long-range lance. Nobody agrees on which one. Somebody is quietly hiring mourners.', '["rumour","pirate","death"]', 1),
  -- geopolitics channel
  (3, NOW() - INTERVAL '9 hours', 'geopolitics', 'Iron Concord borders stay quiet',
   'Concord patrols remain withdrawn behind their frontier. Our listening posts hear more repair crews than gun drills.', '["geopolitics","concord","quiet"]', 3),
  -- policy channel
  (3, NOW() - INTERVAL '14 hours', 'policy', 'New standing order drafted',
   'The Adjutant''s office drafted a standing order tightening private-channel keys after the relay incident.', '["policy","security","palace"]', 3),
  -- government channel
  (3, NOW() - INTERVAL '1 day', 'government', 'Acting governors file Mastika census',
   'Aina Merpati and Azlan Perak filed the capital census: 7.13 billion souls. Births up; the palace wing matters.', '["government","mastika","census"]', 2),
  -- decree channel
  (3, NOW() - INTERVAL '22 hours', 'decree', 'Crown decree: dock security review',
   'A royal decree ordered a full security review of Perdana''s gangways after the splice was found.', '["decree","dock","security"]', 3),
  -- population channel
  (3, NOW() - INTERVAL '2 days', 'population', 'Refugees settle the Far East',
   'Another 4,000 refugees reached the 6xx corridor. Governor Megat reports the foundry town is at 80% housing capacity.', '["population","refugees","east"]', 2),
  -- operation channel
  (3, NOW() - INTERVAL '16 hours', 'operation', 'Deep-cover agent reports in',
   'A coded burst from the Rimward Perimeter: the agent is intact, the cover holds, and something is watching the watching.', '["operation","intel","nyx"]', 4),
  -- diplomacy channel
  (3, NOW() - INTERVAL '11 hours', 'diplomacy', 'Free Ports weigh the net',
   'Free Port syndics debate whether to fish the war-nets — and who pays the toll for safe anchorage.', '["diplomacy","freeports"]', 2),
  (3, NOW() - INTERVAL '3 days', 'diplomacy', 'Vein Collective envoy requests audience',
   'A Vein envoy asked for a quiet audience. Their communique mentions only "the cave network," twice.', '["diplomacy","vein","request"]', 3),
  -- social channel
  (3, NOW() - INTERVAL '7 hours', 'social', 'Crew morale rises after holiday pay',
   'Crew rosters show a small morale bump. The galley served real protein and the betting pools reopened.', '["social","morale","crew"]', 1),
  -- intel channel
  (3, NOW() - INTERVAL '13 hours', 'intel', 'Barnacle memory core extracted',
   'The dock-splice memory core is out of its housing and cooling in a shielded box. Analysis pending.', '["intel","leak","barnacle"]', 4),
  -- anomaly channel
  (3, NOW() - INTERVAL '1 day', 'anomaly', 'Bisik subsurface readings repeat',
   'Bisik instruments logged the same subsurface echo three nights running — same depth, same tone.', '["anomaly","bisik","subsurface"]', 3),
  -- phenomenon channel
  (3, NOW() - INTERVAL '2 days', 'phenomenon', 'Meteor shower over the Far East',
   'A meteor shower lit the 6xx corridor. Governor Megat declared it a good omen and taxed it anyway.', '["phenomenon","east","sky"]', 1),
  -- household channel
  (3, NOW() - INTERVAL '6 hours', 'household', 'The Oracle asks for honey at breakfast',
   'The Oracle has discovered honey. The kitchen has been ordered to keep a pot warm at all hours.', '["household","oracle","kitchen"]', 2),
  -- narrative channel
  (3, NOW() - INTERVAL '4 hours', 'narrative', 'Aeliana does not read the baby name',
   'The Oracle saw the baby''s name in the threads and chose not to speak it. Some futures, she said, deserve to be lived.', '["narrative","oracle","baby"]', 5),
  -- faction channel
  (3, NOW() - INTERVAL '1 day', 'faction', 'Echo Nest Wraiths take a contract',
   'The Echo Nest Wraiths signed a convoy escort contract with a Free Port syndic. Their nesting grounds are suddenly polite.', '["faction","pirate","hired"]', 2),
  -- archaeology channel
  (3, NOW() - INTERVAL '2 days', 'archaeology', 'Dig site yields Forge-era alloy',
   'The team at the far dig pulled a Forge-era alloy plate — the maker''s mark matches nothing in the archives.', '["archaeology","forge","dig"]', 3),
  -- construction channel
  (3, NOW() - INTERVAL '20 hours', 'construction', 'Heaven Yard completes refit slot',
   'Heaven Yard finished a refit slot ahead of schedule. The queue advances; the yard crews collect their bonus.', '["construction","heaven","yard"]', 1),
  -- resource channel
  (3, NOW() - INTERVAL '15 hours', 'resource', 'Alloy stockpiles at capacity',
   'Alloy stockpiles sit at capacity after the foundry''s quarterly pour. Smelting lines throttled to 60%.', '["resource","alloy","foundry"]', 1),
  -- intimacy channel
  (3, NOW() - INTERVAL '5 hours', 'intimacy', 'Perdana sleeps four to a bed',
   'The royal suite reported four queens and one King this morning. Housekeeping has ordered extra blankets.', '["intimacy","household","perdana"]', 2),
  -- story channel
  (3, NOW() - INTERVAL '8 hours', 'story', 'The voice is dust, the silence holds',
   'The Ghost Signal hum has not returned. The silence where it used to be is the loudest thing on the rim.', '["story","ghost signal","silence"]', 4),
  -- science channel
  (3, NOW() - INTERVAL '1 day', 'science', 'Pool research notes a pressure anomaly',
   'The Pool team logged an unexplained pressure anomaly in the lower chambers. Sierra wants a second instrument run.', '["science","pool","anomaly"]', 2),
  -- trade channel
  (3, NOW() - INTERVAL '9 hours', 'trade', 'Trade route reopens after weather',
   'The 6xx route reopened after the ion storm. Backlog caravans are moving again; toll booths are smiling.', '["trade","route","east"]', 1),
  -- festival channel
  (3, NOW() - INTERVAL '1 day', 'festival', 'Hari Api Menggila preparations begin',
   'Colonies begin preparing for Hari Api Menggila. Fireworks contracts tripled overnight.', '["festival","calendar"]', 1),
  -- prison channel
  (3, NOW() - INTERVAL '2 days', 'prison', 'Brig intake: three raiders',
   'Three captured raiders entered the brig. One claims to know where the Den''s hoard was buried before the end.', '["prison","brig","den"]', 3),
  -- quest channel
  (3, NOW() - INTERVAL '10 hours', 'quest', 'A salvage contract appears',
   'A Free Port broker posted a salvage contract for a derelict warship drifting past the rim — payment in clean alloy.', '["quest","salvage","rim"]', 2);
