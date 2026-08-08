#!/usr/bin/env bash
#
# dev.sh — bring the whole web application up in ONE terminal.
#
# The app needs three things running at once: the compose stack (Postgres,
# Neo4j, Keycloak), the FastAPI process, and the Next dev server. Starting only
# the last one is the classic mistake — every page loads and every panel errors,
# because `/api/...` resolves to the Next dev server, which has no such routes.
#
#   ./scripts/dev.sh            # start everything, stream both logs
#   ./scripts/dev.sh --no-docker  # assume the compose stack is already up
#
# Ctrl+C stops the API and the web app. The containers are left running,
# because they hold your ingested graph — stop them with `docker compose down`.

set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
ROOT="$PWD"

API_PORT=8000
WEB_PORT=3000
SKIP_DOCKER=0
[[ "${1:-}" == "--no-docker" ]] && SKIP_DOCKER=1

if [[ -t 1 ]]; then
  DIM=$'\033[2m'; RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'
  BLU=$'\033[34m'; MAG=$'\033[35m'; BLD=$'\033[1m'; OFF=$'\033[0m'
else
  DIM=""; RED=""; GRN=""; YEL=""; BLU=""; MAG=""; BLD=""; OFF=""
fi

say()  { printf '%s\n' "${BLD}${*}${OFF}"; }
warn() { printf '%s\n' "${YEL}!  ${*}${OFF}"; }
die()  { printf '%s\n' "${RED}✗  ${*}${OFF}" >&2; exit 1; }

port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && { exec 3>&-; return 0; } || return 1; }

# ---------------------------------------------------------------- preflight --
[[ -x .venv/bin/uvicorn ]] || die "no .venv/bin/uvicorn — run: uv venv --python 3.12 && uv pip install -e ."
[[ -d frontend/node_modules ]] || die "frontend deps missing — run: cd frontend && npm install"

for p in "$API_PORT:API" "$WEB_PORT:web app"; do
  if port_busy "${p%%:*}"; then
    die "port ${p%%:*} is already in use (${p##*:}). Stop that process first, or it will not be this script's."
  fi
done

# ------------------------------------------------------------------ docker --
if (( ! SKIP_DOCKER )); then
  command -v docker >/dev/null || die "docker not found. Re-run with --no-docker if the stores are up some other way."
  say "→ compose stack"
  docker compose up -d >/dev/null 2>&1 || die "docker compose up failed"

  printf '%s' "${DIM}   waiting for postgres, neo4j, keycloak to report healthy${OFF}"
  for _ in $(seq 1 90); do
    # A service with no healthcheck never prints "healthy", so treat "running"
    # as acceptable and only block on containers still starting.
    pending=$(docker compose ps --format '{{.Service}} {{.Status}}' 2>/dev/null | grep -ci 'starting' || true)
    up=$(docker compose ps --status running --format '{{.Service}}' 2>/dev/null | grep -c . || true)
    if [[ "$pending" == "0" && "$up" -ge 3 ]]; then printf '\n'; break; fi
    printf '.'; sleep 2
  done
  docker compose ps --format 'table {{.Service}}\t{{.Status}}' 2>/dev/null | sed 's/^/   /'
else
  say "→ compose stack ${DIM}(skipped)${OFF}"
fi

# ----------------------------------------------------------------- schema --
# An unmigrated database does not fail loudly. `/auth/context` resolves a
# principal by JOINing an ACTIVE MEMBERSHIP, so a missing `membership` relation
# raises a driver error rather than PrincipalNotFound -- which escapes as a 500
# on a page that otherwise renders. Checked here so it reads as the setup step
# it is, instead of as a broken application.
if (( ! SKIP_DOCKER )) || port_busy 5433; then
  schema_missing=$(docker compose exec -T postgres psql -U callosum -d callosum -tAc \
    "select to_regclass('public.membership') is null;" 2>/dev/null | tr -d '[:space:]')
  if [[ "$schema_missing" == "t" ]]; then
    printf '\n%s\n' "${RED}✗  the database has no product schema — migrations have not been run${OFF}"
    printf '%s\n'   "   Sign-in will fail with a 500 on /auth/context until you do:"
    printf '%s\n\n' "     ${BLD}.venv/bin/alembic upgrade head${OFF}   ${DIM}then see docs/demo-setup.md §4 for the seeds${OFF}"
    exit 1
  fi
  # Provisioned identities are a separate step from `callosum init`, and their
  # absence produces the same 500 for a different reason.
  if [[ "$schema_missing" == "f" ]]; then
    ids=$(docker compose exec -T postgres psql -U callosum -d callosum -tAc \
      "select count(*) from principal_identity;" 2>/dev/null | tr -d '[:space:]')
    if [[ "$ids" == "0" ]]; then
      warn "no principal_identity rows — Keycloak users are not linked to principals yet."
      warn "  sign-in will authenticate and then fail: .venv/bin/python scripts/seed_demo_identities.py"
    fi
  fi
fi

# ------------------------------------------------------------------ cleanup --
API_PID=""; WEB_PID=""

# Both servers fork: uvicorn --reload spawns a worker, `npm run dev` spawns
# next. Killing only the PID we captured orphans the child, which keeps the
# port bound and makes the next run fail its preflight. Walk the tree down and
# kill depth-first.
kill_tree() {
  local pid=$1 child
  for child in $(pgrep -P "$pid" 2>/dev/null); do kill_tree "$child"; done
  kill -TERM "$pid" 2>/dev/null
}

cleanup() {
  trap - INT TERM EXIT
  printf '\n%s\n' "${BLD}→ stopping${OFF}"
  for pid in "$WEB_PID" "$API_PID"; do
    [[ -n "$pid" ]] && kill_tree "$pid"
  done
  # Give them a moment to release the ports before the shell prompt returns.
  for _ in $(seq 1 20); do
    port_busy "$API_PORT" || port_busy "$WEB_PORT" || break
    sleep 0.25
  done
  printf '%s\n' "${DIM}   containers left running — 'docker compose down' to stop them too${OFF}"
}
trap cleanup INT TERM EXIT

# ---------------------------------------------------------------- processes --
# Output goes through process substitution rather than a pipe, so `$!` is the
# SERVER's pid. Behind a pipe it would be sed's, and the cleanup above would
# have been killing the log formatter while the server carried on.
say "→ api    ${DIM}:$API_PORT${OFF}"
.venv/bin/uvicorn meridian.api.main:app --reload --port "$API_PORT" \
  > >(sed -u "s/^/${BLU}api${OFF} /") 2>&1 &
API_PID=$!

say "→ web    ${DIM}:$WEB_PORT${OFF}"
( cd frontend && exec npm run dev ) \
  > >(sed -u "s/^/${MAG}web${OFF} /") 2>&1 &
WEB_PID=$!

# ------------------------------------------------------------------- banner --
( for _ in $(seq 1 60); do
    port_busy "$API_PORT" && port_busy "$WEB_PORT" && break
    sleep 1
  done
  sleep 1
  printf '\n%s\n' "${GRN}${BLD}  ready${OFF}"
  printf '%s\n'   "  ${BLD}http://localhost:${WEB_PORT}${OFF}   ${DIM}← open this one${OFF}"
  printf '%s\n'   "  ${DIM}http://localhost:${API_PORT}/health/engine   api${OFF}"
  printf '%s\n'   "  ${DIM}sign in as 'raj'  ·  workspace 00000000-0000-0000-0000-000000000001${OFF}"
  printf '%s\n\n' "  ${DIM}Ctrl+C stops the api and the web app${OFF}"
) &

wait "$API_PID" "$WEB_PID"
