-- 097-adjutant-prompts.sql — Adjudant prompt queue for King escalation (Day 1384, Izzat rule).
-- Ministries do their jobs autonomously. Any action beyond their authority,
-- or touching Mastika (capital), is queued as a PROMPT to the King — delivered
-- via Maya or any adjutant (Hanum Voss, Sara Valdez, Maria).

CREATE TABLE IF NOT EXISTS maya_rp.adjutant_prompts (
    id            SERIAL PRIMARY KEY,
    session_id    INTEGER NOT NULL,
    ministry      TEXT NOT NULL,                 -- e.g. 'Lord of War'
    holder        TEXT NOT NULL,                 -- e.g. 'Kapten Rizwan Aziz'
    action        TEXT NOT NULL,                 -- what they want to do
    target        TEXT,                          -- territory/system/fleet
    impact        TEXT,                          -- expected impact summary
    urgency       TEXT NOT NULL DEFAULT 'normal', -- normal / high / critical
    status        TEXT NOT NULL DEFAULT 'pending', -- pending / accepted / rejected / done
    routed_via    TEXT NOT NULL,                 -- adjutant: Maya / Hanum / Sara / Maria
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    resolved_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_adjprompt_status ON maya_rp.adjutant_prompts (session_id, status, urgency);