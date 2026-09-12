#!/usr/bin/env bash
# Reproducible Phase 7 eval. Unlike demo.sh, the graph here is SEEDED, not extracted,
# so the result is identical every run — the whole point of run 6's finding: retrieval
# is measured against a fixed gold graph, extraction is measured separately.
#
#   Run from anywhere:  bash scripts/eval.sh
#
# Flow: reset → wait for Postgres → alembic upgrade head → init → ingest
#       (chunks + embeddings only, --no-extract) → seed gold graph → run the
#       stratified eval. No LLM extraction, so no run-to-run graph variance.
#       Alembic is load-bearing: schema/postgres.sql has no membership table,
#       so init fails on a fresh volume without it (#183).

set -euo pipefail
cd "$(dirname "$0")/.."

CLI=".venv/bin/callosum"
ALEMBIC=".venv/bin/alembic"
BOARD="data/demo/board_meeting_12_transcript.txt"
BOARD13="data/demo/board_meeting_13_transcript.txt"
BOARD14="data/demo/board_meeting_14_transcript.txt"
BOARD15="data/demo/board_meeting_15_transcript.txt"
BOARD16="data/demo/board_meeting_16_transcript.txt"
FINANCE="data/demo/finance_fy27_forecast.txt"
SALES="data/demo/sales_fy27_forecast.txt"
COMP="data/demo/compensation_review_CONFIDENTIAL.txt"

hr() { printf '\n\033[1;36m━━━ %s ━━━\033[0m\n' "$1"; }

hr "Resetting Postgres + Neo4j (fresh volumes)"
docker compose down -v
docker compose up -d

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

hr "Init (waits for Neo4j)"
$CLI init

hr "Ingesting docs — chunks + embeddings only (--no-extract)"
$CLI ingest-doc "$BOARD" --type transcript --sensitivity 1 --no-extract
$CLI ingest-doc "$BOARD13" --type transcript --sensitivity 1 --no-extract
$CLI ingest-doc "$BOARD14" --type transcript --sensitivity 1 --no-extract
$CLI ingest-doc "$FINANCE" --type memo --sensitivity 1 --no-extract
$CLI ingest-doc "$SALES" --type memo --sensitivity 1 --no-extract
$CLI ingest-doc "$BOARD15" --type transcript --sensitivity 1 --no-extract
$CLI ingest-doc "$BOARD16" --type transcript --sensitivity 1 --no-extract
$CLI ingest-doc data/demo/messy_operations_notes.txt --type notes --sensitivity 1 --no-extract
$CLI ingest-doc data/demo/messy_customer_email.md --type email --sensitivity 1 --no-extract
$CLI ingest-doc data/demo/messy_customer_call.vtt --type transcript --sensitivity 1 --no-extract
$CLI ingest-doc data/demo/messy_operational_risk_memo.docx --type memo --sensitivity 1 --no-extract
$CLI ingest-doc data/demo/messy_board_appendix.pdf --type appendix --sensitivity 1 --no-extract
$CLI ingest-doc data/demo/messy_board_followup_email.md --type email --sensitivity 1 --no-extract
$CLI ingest-doc data/demo/messy_audit_followup_email.md --type email --sensitivity 1 --no-extract
$CLI ingest-doc data/demo/messy_restricted_email.md --type email --sensitivity 3 --no-extract
$CLI ingest-doc data/demo/messy_board_meeting_17_transcript.txt --type transcript --sensitivity 1 --no-extract
$CLI ingest-doc data/demo/messy_vendor_followup_email.md --type email --sensitivity 1 --no-extract
$CLI ingest-doc "$COMP" --type transcript --sensitivity 3 --no-extract
# The only sensitivity-4 document in the corpus, and the only thing that
# distinguishes founder (clearance 4) from exec (clearance 3): every other
# document is 1 or 3, so without this Raj and Priya see identical material.
$CLI ingest-doc data/demo/board_governance_note_FOUNDER_ONLY.txt --type memo --sensitivity 4 --no-extract

hr "Seeding the gold graph (deterministic — no LLM)"
$CLI seed-eval

hr "Running the stratified eval (hybrid vs vector-only)"
$CLI eval

hr "Done. Table above; full breakdown in eval/results.md"
