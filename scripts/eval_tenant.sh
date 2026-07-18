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
# COMPARE against eval-baseline-v3:
#   * Candidate recall        MUST be 21/21 (100%)   <- the RLS-sensitive metric
#   * Traversal-given-ground. MUST be 100%
#   * Grounding recall ~17/21 and precision ~50% are LLM-dependent (gpt-oss cloud);
#     429s / small wobble there are model noise, NOT an RLS regression. STOP only if
#     CANDIDATE RECALL or TRAVERSAL drops.

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

hr "Done. Compare CANDIDATE RECALL (must be 21/21) + traversal (100%) to eval-baseline-v3."
