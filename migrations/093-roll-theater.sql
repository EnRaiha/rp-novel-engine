-- 093: Roll Theater — blessings, betting pools, hall of rolls (2026-08-14)

-- 1. Queen blessing tokens (one per session, refreshed on use interval)
CREATE TABLE IF NOT EXISTS maya_rp.roll_blessings (
  id serial PRIMARY KEY,
  session_id integer NOT NULL,
  character_name text NOT NULL,
  blessing text NOT NULL,
  effect text NOT NULL,
  charges integer DEFAULT 1,
  last_used_game_day integer
);

-- 2. Betting pools (Book 08 canon: the house bets on the King)
CREATE TABLE IF NOT EXISTS maya_rp.roll_pools (
  id serial PRIMARY KEY,
  session_id integer NOT NULL,
  pool_name text NOT NULL,
  odds text NOT NULL,
  credits_in_pool bigint DEFAULT 0,
  result text,
  status text DEFAULT 'open',
  opened_game_day integer
);

CREATE TABLE IF NOT EXISTS maya_rp.pool_bets (
  id serial PRIMARY KEY,
  pool_id integer NOT NULL,
  bettor_name text NOT NULL,
  bet_credits integer NOT NULL,
  bet_side text NOT NULL,
  payout integer DEFAULT 0
);

-- 3. Hall of legendary rolls (memorialized 100s and 1s)
CREATE TABLE IF NOT EXISTS maya_rp.roll_hall (
  id serial PRIMARY KEY,
  session_id integer NOT NULL,
  roll_name text NOT NULL,
  roll_value integer NOT NULL,
  domain text NOT NULL,
  game_day integer,
  story text
);

-- 4. Seed the five queen blessings
INSERT INTO maya_rp.roll_blessings (session_id, character_name, blessing, effect, charges)
VALUES
  (3,'Callista','forge_luck','+10 to any craft/build roll',1),
  (3,'Vera','navigator_reroll','Reroll any travel roll, keep the better',1),
  (3,'Aeliana','oracle_peek','Roll twice, choose either result',1),
  (3,'Rika','brace','Downgrade a fumble to a plain failure',1),
  (3,'Kira','whisper','Roll hidden — only the King sees the number',1);
