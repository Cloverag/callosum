#!/usr/bin/env bash
# Container entrypoint: bring the databases to a usable state, then exec the server.
#
# These steps exist because they are the documented difference between "the app is
# broken" and "the app was never set up" — a deploy that skips them produces errors
# that look like application bugs and are not. Doing them here means they cannot be
# forgotten. All three are idempotent, so this is safe on every restart.
set -euo pipefail

log() { printf '[entrypoint] %s\n' "$*"; }

# compose's `depends_on: service_healthy` already gates on pg_isready, but a restart
# can race it, and libpq's default is to wait forever rather than error.
log "waiting for postgres"
for i in $(seq 1 60); do
    pg_isready -d "${POSTGRES_DSN}" >/dev/null 2>&1 && { log "postgres ready (${i}s)"; break; }
    [[ $i -eq 60 ]] && { log "FATAL: postgres not ready in 60s"; exit 1; }
    sleep 1
done

# 1/3 — schema. Alembic owns it; the compose init-script only seeds an empty
# database on first boot and does nothing on an existing volume.
log "running migrations"
alembic upgrade head

# 2/3 — principals and memberships. THE ESSENTIAL ONE. `callosum.identity` is
# fail-closed: a principal with no active membership does not resolve at all, so
# without this the API is up, correct, and answers nothing. Idempotent via
# ON CONFLICT DO NOTHING on both inserts.
log "seeding principals and memberships"
callosum init

# 3/3 — OIDC subject links, only when there is an IdP to link to. This demo runs
# without Keycloak, so `principal_identity` has nothing to point at and the script
# is skipped rather than run against a provider that does not exist.
if [[ -n "${MERIDIAN_OIDC_ISSUER:-}" ]]; then
    log "seeding OIDC identities for ${MERIDIAN_OIDC_ISSUER}"
    python scripts/seed_demo_identities.py
else
    log "no MERIDIAN_OIDC_ISSUER — skipping OIDC identity seed (expected for the demo)"
fi

log "starting: $*"
exec "$@"
