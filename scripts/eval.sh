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
$CLI ingest-doc "$COMP" --type transcript --sensitivity 3 --no-extract

hr "Seeding the gold graph (deterministic — no LLM)"
$CLI seed-eval

hr "Running the stratified eval (hybrid vs vector-only)"
$CLI eval

hr "Done. Table above; full breakdown in eval/results.md"
