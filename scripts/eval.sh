#!/usr/bin/env bash
# Reproducible Phase 7 eval. Unlike demo.sh, the graph here is SEEDED, not extracted,
# so the result is identical every run — the whole point of run 6's finding: retrieval
# is measured against a fixed gold graph, extraction is measured separately.
#
#   Run from anywhere:  bash scripts/eval.sh
#
# Flow: reset → ingest (chunks + embeddings only, --no-extract) → seed gold graph →
#       run the stratified eval. No LLM extraction, so no run-to-run graph variance.

set -euo pipefail
cd "$(dirname "$0")/.."

CLI=".venv/bin/callosum"
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

hr "Running the stratified eval (hybrid vs vector-only)"
$CLI eval

hr "Done. Table above; full breakdown in eval/results.md"
