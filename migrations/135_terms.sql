-- Terms: what a character asked of Izzat, and what was agreed.
--
-- THE GAP IS NOT EMOTION, IT IS OBLIGATION. `characters` carries six columns for how someone feels:
-- `bond`, `bond_level`, `affection`, `loyalty`, `aggro`, `relationship_to_player`. Eight more tables
-- hold relationships, romance arcs and faction standing. Nothing anywhere holds what a character
-- ASKED FOR. So a character can be furious for forty turns and the engine cannot say why.
--
-- THE LIVE CASE, from turn 75. Zulaikha Nadira writes back to the proposal and sets two terms:
--
--   "Perkara satu kamu tidak boleh diukur, jadi saya tidak akan menerimanya sebagai janji. Saya akan
--    menerimanya sebagai niat, dan saya akan mencatatnya."
--   "Perkara dua kamu: saya bersetuju, dengan satu tambahan. Apa yang kamu tidak boleh jelaskan,
--    kamu tidak akan jelaskan — tetapi kamu akan memberitahu saya BAHAWA ada sesuatu yang kamu tidak
--    jelaskan. Saya tidak mahu jawapan."
--
-- She demotes the first promise from a promise to an intention because it cannot be measured, and she
-- adds a condition to the second. Those are standing terms. The character will not forget them; the
-- story will, and nothing would have noticed.
--
-- THE `quote` COLUMN IS VERBATIM AND THAT IS THE DESIGN. The engine finds where the terms are and what
-- they say word for word. It does not paraphrase them into a schema, because a paraphrase of an
-- obligation is a second version of it, and the two would drift. `kind` is inferred from the marker
-- that introduced it and is a label, not an interpretation.
--
-- `status` IS OPEN OR RESOLVED, and only a human moves it. The engine cannot tell whether a term was
-- honoured, and a check that guessed would be worse than none.

CREATE TABLE IF NOT EXISTS maya_rp.terms (
    id          SERIAL PRIMARY KEY,
    session_id  INTEGER NOT NULL REFERENCES maya_rp.sessions(id),
    turn_id     BIGINT,
    speaker     TEXT,
    kind        TEXT NOT NULL,
    quote       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS terms_session_status_idx
    ON maya_rp.terms (session_id, status);

-- One term per passage per session, so re-reading the same turn is idempotent.
CREATE UNIQUE INDEX IF NOT EXISTS terms_session_turn_quote_idx
    ON maya_rp.terms (session_id, COALESCE(turn_id, 0), md5(quote));

COMMENT ON TABLE maya_rp.terms IS
    'What a character asked of Izzat and what was agreed, quoted verbatim from the turn that stated '
    'it. Sentiment lives in the characters columns and the relationship tables; this holds the '
    'obligations, which had no home before it.';
COMMENT ON COLUMN maya_rp.terms.kind IS
    'janji (a promise made), syarat (a condition set), persetujuan (an agreement given), perjanjian '
    '(the whole instrument). Inferred from the marker that introduced the passage, not from reading it.';
COMMENT ON COLUMN maya_rp.terms.status IS
    'open or resolved. Only a human moves it: whether a term was honoured is a judgement the engine '
    'does not make.';
