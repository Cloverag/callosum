-- Meridian Institutional Memory — relational + vector store
-- Postgres holds: source-of-truth records, RBAC, version history, and embeddings.
-- Neo4j holds: relationships. The two are joined on the shared UUIDs below.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------------------------------------------------------------------------
-- People & access control
-- ---------------------------------------------------------------------------

-- Clearance ladder. A principal may read any object whose sensitivity is at or
-- below their clearance. Ordering is what makes the comparison cheap, so the
-- integer values matter more than the labels.
CREATE TABLE sensitivity (
    level       INT PRIMARY KEY,
    label       TEXT UNIQUE NOT NULL
);
INSERT INTO sensitivity (level, label) VALUES
    (0, 'public'),        -- press releases, public metrics
    (1, 'investor'),      -- board packs, cap table, KPIs shared with the board
    (2, 'internal'),      -- team-wide docs, product decisions
    (3, 'confidential'),  -- salary, legal, M&A, termination discussions
    (4, 'restricted');    -- founder-only

CREATE TABLE principal (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL,
    email       TEXT UNIQUE,
    role        TEXT NOT NULL,      -- founder | exec | employee | investor | advisor
    clearance   INT  NOT NULL REFERENCES sensitivity(level),
    org         TEXT,               -- e.g. 'Sequoia' for an investor
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Escape hatch: grant one principal access to one object regardless of clearance
-- (e.g. an advisor invited into a single confidential legal thread).
CREATE TABLE acl_grant (
    principal_id UUID NOT NULL REFERENCES principal(id) ON DELETE CASCADE,
    object_id    UUID NOT NULL,     -- document.id or a graph node id
    granted_by   UUID REFERENCES principal(id),
    granted_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (principal_id, object_id)
);

-- ---------------------------------------------------------------------------
-- Raw documents — the source of truth. Everything else is derived and can be
-- rebuilt by re-running the pipeline over these.
-- ---------------------------------------------------------------------------

CREATE TABLE document (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title        TEXT NOT NULL,
    doc_type     TEXT NOT NULL,     -- board_deck | transcript | email | memo | contract | minutes
    source_uri   TEXT,              -- original file path / gdrive link
    raw_text     TEXT NOT NULL,
    content_hash TEXT UNIQUE NOT NULL,   -- dedupe: same bytes never ingested twice
    sensitivity  INT  NOT NULL REFERENCES sensitivity(level) DEFAULT 2,
    authored_by  UUID REFERENCES principal(id),
    authored_at  TIMESTAMPTZ,       -- when the doc was written, not when ingested
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX ON document (doc_type);
CREATE INDEX ON document (sensitivity);
CREATE INDEX ON document USING gin (metadata);

-- ---------------------------------------------------------------------------
-- Chunks + embeddings. The chunk is the bridge between the vector store and the
-- graph: every chunk id here also exists as a (:Chunk) node in Neo4j, wired to
-- the entities it mentions. That is what makes a hit in one store traversable
-- into the other.
-- ---------------------------------------------------------------------------

CREATE TABLE chunk (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id  UUID NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    ordinal      INT  NOT NULL,     -- position within the document
    text         TEXT NOT NULL,
    -- Denormalised from document so the permission filter stays a single-table
    -- WHERE clause on the hot retrieval path.
    sensitivity  INT  NOT NULL REFERENCES sensitivity(level),
    embedding    VECTOR(1024),
    UNIQUE (document_id, ordinal)
);
CREATE INDEX ON chunk (sensitivity);
-- HNSW beats IVFFlat here: the corpus is small and grows continuously, and HNSW
-- needs no retraining as rows land.
CREATE INDEX chunk_embedding_hnsw ON chunk
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

-- ---------------------------------------------------------------------------
-- Version history. Append-only. Nothing in this system is ever destructively
-- updated: a superseded decision stays queryable, which is the entire point of
-- institutional memory for a company that pivots every quarter.
-- ---------------------------------------------------------------------------

CREATE TABLE node_version (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    node_id      UUID NOT NULL,     -- the graph node this describes
    node_label   TEXT NOT NULL,     -- Decision | Person | Meeting | ...
    version      INT  NOT NULL,
    properties   JSONB NOT NULL,    -- full snapshot at this version
    change_reason TEXT,
    valid_from   TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to     TIMESTAMPTZ,       -- NULL = current
    created_by   UUID REFERENCES principal(id),
    UNIQUE (node_id, version)
);
CREATE INDEX ON node_version (node_id, valid_to);

-- ---------------------------------------------------------------------------
-- Human-in-the-loop approval queue. The LLM never writes to the graph directly.
-- It proposes; a founder approves; only then does the memory mutate.
-- ---------------------------------------------------------------------------

CREATE TABLE proposed_change (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id  UUID REFERENCES document(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL,     -- add_entity | add_relationship | supersede_decision
    payload      JSONB NOT NULL,    -- the exact graph mutation to apply
    evidence     JSONB NOT NULL DEFAULT '[]'::jsonb,  -- chunk ids backing this claim
    confidence   REAL,              -- extractor's self-reported confidence
    status       TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
    reviewed_by  UUID REFERENCES principal(id),
    reviewed_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ON proposed_change (status, created_at);

-- ---------------------------------------------------------------------------
-- Query audit log. Doubles as the evaluation dataset later: every question, the
-- context that was retrieved, and what the LLM said.
-- ---------------------------------------------------------------------------

CREATE TABLE query_log (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    principal_id  UUID REFERENCES principal(id),
    question      TEXT NOT NULL,
    plan          JSONB,            -- what the planner decided to do
    graph_hits    JSONB,
    vector_hits   JSONB,
    denied_count  INT DEFAULT 0,    -- results withheld by the permission filter
    answer        TEXT,
    latency_ms    INT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
