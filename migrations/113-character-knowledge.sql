-- 113 — knowledge ledger: what a character has actually witnessed (M4, data layer).
-- Owner: maya. Apply by hand:
--   PGPASSWORD=$POSTGRES_PASS psql -h $OC_PG_HOST -U maya -d maya_memory -f <this>

CREATE TABLE IF NOT EXISTS maya_rp.character_knowledge (
    id bigserial PRIMARY KEY,
    session_id integer NOT NULL,
    character_id integer NOT NULL REFERENCES maya_rp.characters(id) ON DELETE CASCADE,
    fact_key text NOT NULL,
    source text,
    learned_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT character_knowledge_unique UNIQUE (session_id, character_id, fact_key)
);

COMMENT ON TABLE maya_rp.character_knowledge IS
    'Fact keys one character has witnessed; the audit rule that enforces knowledge blindness is follow-up (M4).';
