-- ============================================================
-- RAG Schema for PubMed Cell Culture Media Literature
-- Adapted for FBS-free / xeno-free / defined medium queries
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Drop in correct order to respect foreign keys
DROP TABLE IF EXISTS messages CASCADE;
DROP TABLE IF EXISTS sessions CASCADE;
DROP TABLE IF EXISTS chunks CASCADE;
DROP TABLE IF EXISTS documents CASCADE;
DROP INDEX IF EXISTS idx_chunks_embedding;
DROP INDEX IF EXISTS idx_chunks_document_id;
DROP INDEX IF EXISTS idx_documents_metadata;
DROP INDEX IF EXISTS idx_chunks_content_trgm;

-- ============================================================
-- DOCUMENTS TABLE
-- One row per paper/PDF you ingest
-- Added: pmid, doi, journal, pub_year as dedicated columns
-- for easy filtering alongside the flexible metadata JSONB
-- ============================================================
CREATE TABLE documents (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title        TEXT NOT NULL,
    source       TEXT NOT NULL UNIQUE,          -- file path or PubMed URL
    content      TEXT NOT NULL,          -- full extracted text
    pmid         TEXT,                   -- PubMed ID, e.g. '12345678'
    doi          TEXT,                   -- e.g. '10.1016/j.stem.2023.01.001'
    journal      TEXT,                   -- e.g. 'Stem Cell Research'
    pub_year     INTEGER,                -- e.g. 2023
    -- JSONB for flexible fields: authors, cell_type, medium_type, fbs_free, etc.
    -- Example:
    -- {
    --   "authors": ["Smith J", "Lee K"],
    --   "cell_type": "iPSC",
    --   "medium_type": "defined",
    --   "fbs_free": true,
    --   "xeno_free": true,
    --   "keywords": ["serum-free", "chemically defined", "GMP"]
    -- }
    metadata     JSONB DEFAULT '{}',
    created_at   TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_fbs_free CHECK (
        (metadata->>'fbs_free' IS NULL) OR
        (metadata->>'fbs_free' IN ('true', 'false'))
    ),
    CONSTRAINT valid_xeno_free CHECK (
        (metadata->>'xeno_free' IS NULL) OR
        (metadata->>'xeno_free' IN ('true', 'false'))
    )
);

CREATE INDEX idx_documents_metadata    ON documents USING GIN (metadata);
CREATE INDEX idx_documents_created_at  ON documents (created_at DESC);
CREATE INDEX idx_documents_pmid        ON documents (pmid);
CREATE INDEX idx_documents_pub_year    ON documents (pub_year);
-- Lets you filter: WHERE metadata->>'fbs_free' = 'true'
CREATE INDEX idx_documents_fbs_free    ON documents ((metadata->>'fbs_free'));
CREATE INDEX idx_documents_xeno_free   ON documents ((metadata->>'xeno_free'));
CREATE INDEX idx_documents_medium_type ON documents ((metadata->>'medium_type'));

-- ============================================================
-- CHUNKS TABLE
-- Each document is split into overlapping text chunks.
-- embedding vector(1536) matches OpenAI text-embedding-3-small.
-- CHANGE to vector(768) if using Ollama nomic-embed-text,
-- or vector(3072) if using OpenAI text-embedding-3-large.
-- ============================================================
CREATE TABLE chunks (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id   UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content       TEXT NOT NULL,
    embedding     vector(1536),          -- <-- change dimension to match your model
    chunk_index   INTEGER NOT NULL,
    section       TEXT,                  -- e.g. 'abstract', 'methods', 'results'
    token_count   INTEGER,
    metadata      JSONB DEFAULT '{}',
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ivfflat index for fast approximate nearest-neighbor search
-- 'lists = 1' is fine for small collections (<10k chunks).
-- Increase to ~sqrt(row_count) once you have more data, e.g. lists = 100
CREATE INDEX idx_chunks_embedding      ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 1);
CREATE INDEX idx_chunks_document_id    ON chunks (document_id);
CREATE INDEX idx_chunks_chunk_index    ON chunks (document_id, chunk_index);
-- Full-text search index — important for exact scientific terms like 'FBS', 'xeno-free'
CREATE INDEX idx_chunks_content_trgm   ON chunks USING GIN (content gin_trgm_ops);
CREATE INDEX idx_chunks_section        ON chunks (section);

-- ============================================================
-- SESSIONS + MESSAGES TABLES
-- Stores your conversation history so the chatbot remembers
-- what you asked earlier in the same session.
-- ============================================================
CREATE TABLE sessions (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id    TEXT,
    metadata   JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_sessions_user_id    ON sessions (user_id);
CREATE INDEX idx_sessions_expires_at ON sessions (expires_at);

CREATE TABLE messages (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content    TEXT NOT NULL,
    metadata   JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_messages_session_id ON messages (session_id, created_at);

-- ============================================================
-- FUNCTION: match_chunks
-- Pure vector (semantic) search.
-- Use for natural language queries like:
--   "chemically defined medium for neural differentiation"
-- The vector(1536) here must match your chunks table above.
-- ============================================================
CREATE OR REPLACE FUNCTION match_chunks(
    query_embedding  vector(1536),       -- <-- change if you changed chunks above
    match_count      INT DEFAULT 10,
    -- Optional filters: pass NULL to skip, or e.g. 'true' to filter fbs_free papers
    filter_fbs_free  BOOLEAN DEFAULT NULL,
    filter_xeno_free BOOLEAN DEFAULT NULL
)
RETURNS TABLE (
    chunk_id        UUID,
    document_id     UUID,
    content         TEXT,
    similarity      FLOAT,
    metadata        JSONB,
    document_title  TEXT,
    document_source TEXT,
    pmid            TEXT,
    pub_year        INTEGER,
    section         TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id                                          AS chunk_id,
        c.document_id,
        c.content,
        1 - (c.embedding <=> query_embedding)         AS similarity,
        c.metadata,
        d.title                                       AS document_title,
        d.source                                      AS document_source,
        d.pmid,
        d.pub_year,
        c.section
    FROM chunks c
    JOIN documents d ON c.document_id = d.id
    WHERE c.embedding IS NOT NULL
      -- Apply optional metadata filters
      AND (filter_fbs_free  IS NULL OR (d.metadata->>'fbs_free')::boolean  = filter_fbs_free)
      AND (filter_xeno_free IS NULL OR (d.metadata->>'xeno_free')::boolean = filter_xeno_free)
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- ============================================================
-- FUNCTION: hybrid_search
-- Combines vector similarity (semantic) + full-text keyword
-- matching. Best of both worlds:
--   - Vector catches "serum-free" even if the paper says
--     "no animal serum was used"
--   - Full-text catches exact terms like "FBS", "BSA", "xeno"
-- text_weight default 0.3 = 70% semantic, 30% keyword.
-- Raise text_weight (e.g. 0.5) if exact terminology matters more.
-- ============================================================
CREATE OR REPLACE FUNCTION hybrid_search(
    query_embedding  vector(1536),       -- <-- change if you changed chunks above
    query_text       TEXT,
    match_count      INT DEFAULT 10,
    text_weight      FLOAT DEFAULT 0.3,
    filter_fbs_free  BOOLEAN DEFAULT NULL,
    filter_xeno_free BOOLEAN DEFAULT NULL
)
RETURNS TABLE (
    chunk_id          UUID,
    document_id       UUID,
    content           TEXT,
    combined_score    FLOAT,
    vector_similarity FLOAT,
    text_similarity   FLOAT,
    metadata          JSONB,
    document_title    TEXT,
    document_source   TEXT,
    pmid              TEXT,
    pub_year          INTEGER,
    section           TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH vector_results AS (
        SELECT
            c.id      AS chunk_id,
            c.document_id,
            c.content,
            1 - (c.embedding <=> query_embedding) AS vector_sim,
            c.metadata,
            d.title   AS doc_title,
            d.source  AS doc_source,
            d.pmid,
            d.pub_year,
            c.section
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE c.embedding IS NOT NULL
          AND (filter_fbs_free  IS NULL OR (d.metadata->>'fbs_free')::boolean  = filter_fbs_free)
          AND (filter_xeno_free IS NULL OR (d.metadata->>'xeno_free')::boolean = filter_xeno_free)
    ),
    text_results AS (
        SELECT
            c.id      AS chunk_id,
            c.document_id,
            c.content,
            ts_rank_cd(
                to_tsvector('english', c.content),
                plainto_tsquery('english', query_text)
            ) AS text_sim,
            c.metadata,
            d.title   AS doc_title,
            d.source  AS doc_source,
            d.pmid,
            d.pub_year,
            c.section
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE to_tsvector('english', c.content) @@ plainto_tsquery('english', query_text)
          AND (filter_fbs_free  IS NULL OR (d.metadata->>'fbs_free')::boolean  = filter_fbs_free)
          AND (filter_xeno_free IS NULL OR (d.metadata->>'xeno_free')::boolean = filter_xeno_free)
    )
    SELECT
        COALESCE(v.chunk_id,     t.chunk_id)     AS chunk_id,
        COALESCE(v.document_id,  t.document_id)  AS document_id,
        COALESCE(v.content,      t.content)      AS content,
        (COALESCE(v.vector_sim, 0) * (1 - text_weight)
            + COALESCE(t.text_sim, 0) * text_weight) AS combined_score,
        COALESCE(v.vector_sim,   0)              AS vector_similarity,
        COALESCE(t.text_sim,     0)              AS text_similarity,
        COALESCE(v.metadata,     t.metadata)     AS metadata,
        COALESCE(v.doc_title,    t.doc_title)    AS document_title,
        COALESCE(v.doc_source,   t.doc_source)   AS document_source,
        COALESCE(v.pmid,         t.pmid)         AS pmid,
        COALESCE(v.pub_year,     t.pub_year)     AS pub_year,
        COALESCE(v.section,      t.section)      AS section
    FROM vector_results v
    FULL OUTER JOIN text_results t ON v.chunk_id = t.chunk_id
    ORDER BY combined_score DESC
    LIMIT match_count;
END;
$$;

-- ============================================================
-- FUNCTION: get_document_chunks
-- Retrieve all chunks for a specific paper in order.
-- Useful for reading a full paper's content once you've
-- identified it via search.
-- ============================================================
CREATE OR REPLACE FUNCTION get_document_chunks(doc_id UUID)
RETURNS TABLE (
    chunk_id    UUID,
    content     TEXT,
    chunk_index INTEGER,
    section     TEXT,
    metadata    JSONB
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        id          AS chunk_id,
        chunks.content,
        chunks.chunk_index,
        chunks.section,
        chunks.metadata
    FROM chunks
    WHERE document_id = doc_id
    ORDER BY chunk_index;
END;
$$;

-- ============================================================
-- TRIGGER: auto-update updated_at on row changes
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_sessions_updated_at
    BEFORE UPDATE ON sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- VIEW: document_summaries
-- Quick overview of all ingested papers and how many chunks
-- each was split into. Useful for checking your ingestion ran.
-- ============================================================
CREATE OR REPLACE VIEW document_summaries AS
SELECT
    d.id,
    d.title,
    d.source,
    d.pmid,
    d.doi,
    d.journal,
    d.pub_year,
    d.created_at,
    d.updated_at,
    d.metadata,
    d.metadata->>'fbs_free'   AS fbs_free,
    d.metadata->>'xeno_free'  AS xeno_free,
    d.metadata->>'medium_type' AS medium_type,
    d.metadata->>'cell_type'  AS cell_type,
    COUNT(c.id)               AS chunk_count,
    AVG(c.token_count)        AS avg_tokens_per_chunk,
    SUM(c.token_count)        AS total_tokens
FROM documents d
LEFT JOIN chunks c ON d.id = c.document_id
GROUP BY d.id, d.title, d.source, d.pmid, d.doi, d.journal,
         d.pub_year, d.created_at, d.updated_at, d.metadata;