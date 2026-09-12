#!/usr/bin/env bash
# One-command end-to-end demo. Resets both stores, ingests the two board
# documents, shows the quarantine, approves, and runs the two golden queries.
#
# Run from anywhere:  bash scripts/demo.sh
# (Works from fish too — `bash` runs it in bash regardless of your shell.)

set -euo pipefail
cd "$(dirname "$0")/.."

CLI=".venv/bin/callosum"
ALEMBIC=".venv/bin/alembic"
BOARD="data/demo/board_meeting_12_transcript.txt"
COMP="data/demo/compensation_review_CONFIDENTIAL.txt"

hr() { printf '\n\033[1;36m━━━ %s ━━━\033[0m\n' "$1"; }

hr "Resetting Postgres + Neo4j (fresh volumes)"
docker compose down -v
docker compose up -d

# Fresh volumes only apply schema/postgres.sql — no membership table, no
# workspace_id. callosum init needs both (#183). Probe TCP until Postgres has
# finished initdb and bounced; connecting earlier gets a closed connection.
hr "Waiting for Postgres to accept TCP connections (post-initdb)"
for i in $(seq 1 60); do
    if .venv/bin/python -c "import psycopg; from callosum.config import settings; psycopg.connect(settings().postgres_dsn, connect_timeout=2).close()" 2>/dev/null; then
        echo "postgres ready after ${i}s"
        break
    fi
    if [ "$i" -eq 60 ]; then echo "ERROR: postgres never became ready" >&2; exit 1; fi
    sleep 1
done

hr "Applying product migrations (membership, RLS, callosum_app) — BEFORE init"
$ALEMBIC upgrade head

hr "Init (waits for Neo4j to accept connections)"
$CLI init

hr "Ingesting board transcript (sensitivity 1 — investors may read)"
$CLI ingest-doc "$BOARD" --type transcript --sensitivity 1

hr "Ingesting compensation review (sensitivity 3 — founder/exec only)"
$CLI ingest-doc "$COMP" --type transcript --sensitivity 3

hr "Quarantine — edges the verifier refused"
$CLI failures

hr "Approving all proposed edges into the graph"
$CLI approve --all

hr "Q1 — as Raj (founder, clearance 4): Why did we reject Pricing Model B?"
$CLI query "Why did we reject Pricing Model B?" --as Raj

hr "Q2 — as Marcus (investor, clearance 1): What is Priya's compensation?"
$CLI query "What is Priya's compensation?" --as Marcus

hr "Done. Graph: http://localhost:7474  (neo4j / callosum123)"
