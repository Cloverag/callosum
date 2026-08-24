#!/usr/bin/env bash
# Deterministic mechanism gate — the REQUIRED release tier, run through the P1 tenancy stack.
#
# This is scripts/eval_tenant.sh with ONE change: the final step is `callosum eval-mechanism`
# instead of `callosum eval`. It makes ZERO cloud-LLM calls (no planner, no synthesis) — only
# candidate retrieval (local bge-m3), gold-seeded 2-hop traversal, and RBAC. So it is fast,
# free, reproducible byte-for-byte, and CI-safe. See
# docs/proposals/2026-07-20-eval-mechanism-split.md.
#
#   Run from anywhere:  bash scripts/eval_mechanism.sh
#
# GATE (hard — non-zero exit on any miss, vs eval-baseline-v3):
#   * Candidate recall          = 21/21 (100%)   — RLS/candidate regression if it drops
#   * Gold-seeded traversal      = 100% on every expect_facts item — traversal-engine regression
#   * RBAC fail-closed           = all forbid_answer items — a leak on either retrieval surface
# The planner grounding + answer-text tiers are OBSERVED, not gated — run them with
# scripts/eval_tenant.sh (needs the cloud model) when you want those numbers.

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

# On a fresh volume Postgres runs its init scripts and restarts once before it accepts
# TCP — connecting too early gets "server closed the connection unexpectedly". Probe the
# exact DSN alembic will use, over TCP, until a real connect+close succeeds.
hr "Waiting for Postgres to accept TCP connections (post-initdb)"
for i in $(seq 1 60); do
    if .venv/bin/python -c "import psycopg; from callosum.config import settings; psycopg.connect(settings().postgres_dsn, connect_timeout=2).close()" 2>/dev/null; then
        echo "postgres ready after ${i}s"
        break
    fi
    if [ "$i" -eq 60 ]; then echo "ERROR: postgres never became ready" >&2; exit 1; fi
    sleep 1
done

hr "Applying tenancy migrations (creates callosum_app + RLS) — BEFORE the app starts"
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

hr "Seeding the gold graph (deterministic — no LLM)"
$CLI seed-eval

hr "Running the deterministic mechanism gate — through RLS as callosum_app, NO cloud LLM"
$CLI eval-mechanism

hr "Done. Gate result printed above (non-zero exit here means a mechanism invariant regressed)."
