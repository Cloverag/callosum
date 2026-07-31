# Demo setup

From a fresh clone to a working authenticated web application. Every command here was
run end to end on 2026-08-01; the failures in **Troubleshooting** are ones that actually
happened, not ones imagined for the section.

Roughly 15 minutes, most of it waiting for containers.

---

## Prerequisites

| | |
|---|---|
| Docker + Docker Compose | Postgres, Neo4j, Keycloak |
| Python 3.12 | via `uv` |
| Node 20+ | the Next.js application |

Four ports must be free: **5432** Postgres · **7474/7687** Neo4j · **8080** Keycloak ·
**8000** API · **3000** web.

---

## 1. Start the infrastructure

```bash
docker compose up -d
```

Keycloak imports `keycloak/realm-dev.json` on its **first** start. Wait for it:

```bash
docker inspect --format='{{.State.Health.Status}}' callosum-keycloak
# healthy
```

> **If you change the realm file later**, a plain restart will not re-import it —
> Keycloak skips a realm that already exists. Recreate the container:
> ```bash
> docker compose rm -sf keycloak && docker compose up -d keycloak
> ```
> Dev mode keeps its state inside the container, so this is safe and loses nothing else.

---

## 2. Install and migrate

```bash
uv venv --python 3.12 && uv pip install -e ".[dev]"
cp .env.example .env
.venv/bin/alembic upgrade head
```

---

## 3. Configure the environment

`.env.example` carries working development values for everything below. **Only the
session secret must be changed**, and only because a shared secret is not a secret.

| Variable | Value for local demo | Why it matters |
|---|---|---|
| `MERIDIAN_OIDC_ISSUER` | `http://localhost:8080/realms/meridian` | Realm base URL; Authlib discovers the rest |
| `MERIDIAN_OIDC_CLIENT_ID` | `meridian-api` | Must match the client in the realm |
| `MERIDIAN_OIDC_CLIENT_SECRET` | `dev-client-secret-change-me` | Must match the realm's client secret |
| `MERIDIAN_OIDC_REDIRECT_URL` | `http://localhost:3000/auth/callback` | **Port 3000, not 8000** — see below |
| `MERIDIAN_SESSION_SECRET` | generate one | Sessions are not installed without it |
| `MERIDIAN_SESSION_HTTPS_ONLY` | `false` | The cookie is `Secure` by default and a browser will not send it over plain HTTP |

Generate the secret:

```bash
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Put it in `.env` as `MERIDIAN_SESSION_SECRET=…`. Not in the shell, not in
`.env.example`, not in the compose file.

### Why the redirect is port 3000

The browser talks only to Next, which proxies `/api`, `/auth` and `/health` through to
FastAPI. The session is a **same-origin httpOnly cookie** (ADR-009). A callback landing
on `:8000` would set the cookie on a second origin and the application on `:3000` would
never receive it — you would log in successfully and still be logged out.

---

## 4. Seed

Three steps, in order. Each is idempotent.

```bash
# 1. Principals, memberships, Neo4j constraints.
.venv/bin/callosum init

# 2. The document corpus. Sensitivity is the clearance gate — the compensation
#    review must be restricted or the withholding demo has nothing to withhold.
.venv/bin/callosum ingest-doc data/demo/board_meeting_12_transcript.txt --type transcript --sensitivity 1
.venv/bin/callosum ingest-doc data/demo/board_meeting_13_transcript.txt --type transcript --sensitivity 1
.venv/bin/callosum ingest-doc data/demo/board_meeting_14_transcript.txt --type transcript --sensitivity 1
.venv/bin/callosum ingest-doc data/demo/finance_fy27_forecast.txt       --type memo       --sensitivity 1
.venv/bin/callosum ingest-doc data/demo/compensation_review_CONFIDENTIAL.txt --type memo --sensitivity 4

# 3. Link Keycloak users to principals, then create the board data.
.venv/bin/python scripts/seed_demo_identities.py
.venv/bin/python scripts/seed_demo_board.py
```

**What each seed does, and why it is separate:**

- `callosum init` creates the three principals and their memberships. It does **not**
  create `principal_identity` rows, which is why login alone is not enough.
- `seed_demo_identities.py` links each Keycloak user's subject to a principal.
  `stranger` is deliberately **not** linked — it exists to demonstrate that an
  authenticated but unprovisioned identity is refused (ADR-011).
- `seed_demo_board.py` creates meetings, agendas, decisions, stances, a resolution with
  votes, a commitment, a published pack and finalised minutes. Everything is written
  **through the domain modules**, so the status machines, version counters and audit
  events all hold — seeding by raw SQL would produce a state the application itself
  cannot reach.

---

## 5. Run

Two processes, two terminals. Both must stay running.

```bash
# terminal 1 — the API, from the repository root
.venv/bin/uvicorn meridian.api.main:app --reload --port 8000

# terminal 2 — the web application
cd frontend && npm install && npm run dev
```

Confirm before opening a browser:

```bash
curl -s localhost:8000/health/engine
# {"status":"ok","engine":"callosum","engine_version":"0.1.5"}

curl -s -o /dev/null -w "%{http_code}\n" localhost:3000/api/meetings
# 401  ← correct: the proxy reached the API, and you are not signed in yet
```

A **404** there means the proxy is not working. A **000** means the API is not running.

---

## 6. Log in

Open <http://localhost:3000>, which redirects to Keycloak.

| User | Password | Clearance | Sees |
|---|---|---|---|
| `raj` | `raj` | 4 — founder | everything: 16 documents, 3 pack items |
| `priya` | `priya` | 3 — exec | most things |
| `marcus` | `marcus` | 1 — investor | 14 documents, 2 pack items |
| `stranger` | `stranger` | — | **403.** Authenticated, not provisioned |

After sign-in you must select a workspace — that is ADR-012, not a bug. Until you do,
API calls answer `409 workspace_not_selected`.

---

## Troubleshooting

Each of these happened during the build-out.

**Every page shows an error; the terminal logs an unhandled rejection.**
The API is not running, or only the frontend was started. `lib/http.ts` fetches `/api/…`
relative to the page, so without the API behind the proxy it resolves to the Next dev
server, which has no such routes.

**`fish: Unknown command: .venv/bin/uvicorn`**
You are in `frontend/`. That path is relative to the repository root.

**Every authenticated endpoint returns 503 `session_not_configured`.**
`MERIDIAN_SESSION_SECRET` is empty or absent. Sessions are installed only when it is
set — deliberately, because handing out forgeable cookies is worse than refusing to
start the feature.

**Login succeeds, then every request reads as logged out.**
`MERIDIAN_OIDC_REDIRECT_URL` points at `:8000`. The cookie was set on the wrong origin.

**Keycloak is `unhealthy` after editing the realm file.**
Check `docker logs callosum-keycloak` for `Unrecognized field`. An invalid realm aborts
startup entirely. Post-logout URIs, for instance, are a client **attribute**
(`post.logout.redirect.uris`), not a top-level field.

**Login returns 403 "Your identity is not provisioned for this workspace."**
Either you signed in as `stranger` — in which case this is the demo working — or
`seed_demo_identities.py` has not been run.

**The realm has the old users after you edited `realm-dev.json`.**
`--import-realm` skips a realm that already exists. Recreate the container (step 1).

**Pages load but every list is empty.**
`seed_demo_board.py` has not run. `callosum init` seeds principals, not board data.

---

## Verifying without a browser

The whole flow can be driven with curl, which is how it was checked here:

```bash
# 1. Start login, capture the Keycloak form action
FORM=$(curl -s -c jar.txt -L http://localhost:3000/auth/login \
  | grep -oE 'action="[^"]*"' | head -1 | sed 's/action="//; s/"$//' \
  | python3 -c "import sys,html; print(html.unescape(sys.stdin.read().strip()))")

# 2. Sign in
curl -s -b jar.txt -c jar.txt -o /dev/null -L \
  --data-urlencode "username=raj" --data-urlencode "password=raj" "$FORM"

# 3. Select the workspace
curl -s -b jar.txt -c jar.txt -X POST -H "Content-Type: application/json" \
  -d '{"workspace_id":"00000000-0000-0000-0000-000000000001"}' \
  http://localhost:3000/auth/workspace

# 4. Read something
curl -s -b jar.txt http://localhost:3000/api/documents | head -c 200
```

Swap `raj` for `marcus` and compare the document count: **16 against 14**.
