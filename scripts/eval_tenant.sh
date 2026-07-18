#!/usr/bin/env bash
# Brick 2b.5 — the frozen evaluation, run through the FULL P1 tenancy stack.
#
# This is scripts/eval.sh with ONE addition: `alembic upgrade head` after the DB comes
# up, so the tenancy schema + the non-superuser `callosum_app` role exist before the app
# (which now connects as callosum_app) starts. The frozen eval.sh is left untouched.
#
# The point: every ingest/retrieval call below goes through store.pg() -> callosum_app,
# with Row-Level Security ENABLED and FORCED. All rows land in the Default Workspace, and
# the session is scoped to the Default Workspace, so the RLS predicate matches every row.
# If retrieval is truly single-tenant-invariant, the numbers must equal eval-baseline-v3.
#
#   Run from anywhere:  bash scripts/eval_tenant.sh
#
# ACCEPTANCE (vs eval-baseline-v3), two tiers:
#   REQUIRED (hard gate — a change here means an RLS regression, STOP):
#     * Candidate recall           = 21/21 (100%)
#     * Traversal-given-grounding  = 100%
#   OBSERVED (recorded in eval/results.md, NOT a gate — do not ignore, do not gate on):
#     * Grounding recall / precision (~17/21, ~50%) — LLM-dependent (gpt-oss cloud)
#     * Any 429s / planner failures — note them in the run record so eval history stays honest
# Grounding is downstream of retrieval: with candidate recall held at 21/21, any grounding
# movement is model noise (429s, sampling), not tenancy. Record it; don't gate on it.

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
$CLI ingest-doc "$COMP" --type transcript --sensitivity 3 --no-extract

hr "Seeding the gold graph (deterministic — no LLM)"
$CLI seed-eval

hr "Running the stratified eval (hybrid vs vector-only) — through RLS as callosum_app"
$CLI eval

hr "Done."
echo "REQUIRED gate: candidate recall must be 21/21 and traversal 100% (vs eval-baseline-v3)."
echo "OBSERVED (record, don't gate): grounding recall/precision + any 429s in eval/results.md."
