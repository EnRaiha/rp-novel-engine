-- 052-wiki-articles.sql
-- Wiki RAG — structured lore articles with vector embeddings for semantic search.
-- GTX 1060 generates embeddings via Ollama (nomic-embed-text:768d).
-- Deepseek queries this via Kilo Bridge at runtime — no static 50K PDFs.
-- ============================================================

-- 1. The Wiki Table
CREATE TABLE IF NOT EXISTS maya_rp.wiki_articles (
    id              SERIAL PRIMARY KEY,
    session_id      INT NOT NULL DEFAULT 3,
    title           VARCHAR(200) NOT NULL,
    category        VARCHAR(50),       -- 'faction', 'technology', 'location', 'history', 'character', 'species', 'rules', 'procedural_history'
    tags            TEXT[],            -- e.g. '{den, enemy, military}'
    content         TEXT NOT NULL,     -- The 200-800 word chunk of lore
    source_file     VARCHAR(100),      -- 'setting-bible.md', 'game_history' (for procedural)
    embedding       vector(768),       -- nomic-embed-text output
    is_procedural   BOOLEAN DEFAULT false,  -- true = written by engine at runtime
    relevance_end_day INT,             -- NULL = forever. Set to expire procedural lore after N game days
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- 2. HNSW index for lightning-fast vector search (cosine distance)
CREATE INDEX IF NOT EXISTS idx_wiki_articles_embedding
    ON maya_rp.wiki_articles USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 200);

-- 3. Index for category filtering + session scoping
CREATE INDEX IF NOT EXISTS idx_wiki_articles_session_cat
    ON maya_rp.wiki_articles (session_id, category);
