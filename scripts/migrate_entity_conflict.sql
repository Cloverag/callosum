-- Migration: add entity_conflict table to an existing Callosum database.
--
-- Run this if you already have data in Postgres and do NOT want to wipe
-- volumes. The schema/postgres.sql already contains this table for fresh
-- installs; this script is for existing environments only.
--
-- Usage (PowerShell):
--   docker exec -i callosum-postgres-1 psql -U callosum -d callosum < scripts/migrate_entity_conflict.sql
--
-- Safe to run multiple times — all statements use IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS entity_conflict (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name_a          TEXT NOT NULL,
    type_a          TEXT NOT NULL,
    name_b          TEXT NOT NULL,
    type_b          TEXT NOT NULL,
    similarity      REAL NOT NULL,
    chunk_id_a      UUID REFERENCES chunk(id) ON DELETE SET NULL,
    chunk_id_b      UUID REFERENCES chunk(id) ON DELETE SET NULL,
    quote_a         TEXT,
    quote_b         TEXT,
    sensitivity     INT NOT NULL DEFAULT 1 REFERENCES sensitivity(level),
    status          TEXT NOT NULL DEFAULT 'pending',
    reviewed_by     UUID REFERENCES principal(id),
    reviewed_at     TIMESTAMPTZ,
    change_id       UUID REFERENCES proposed_change(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (name_a, type_a, name_b, type_b)
);

CREATE INDEX IF NOT EXISTS entity_conflict_status_idx ON entity_conflict (status);
CREATE INDEX IF NOT EXISTS entity_conflict_sensitivity_idx ON entity_conflict (sensitivity);
