# Callosum public demo — home server deploy

Target: `api.cloverag.dpdns.org` -> Cloudflare Tunnel -> home server (2 cores, 5.8GB).
Frontend on Vercel at `cloverag.dpdns.org`.

Files in this directory go to the repo root, except `entrypoint.sh` -> `docker/entrypoint.sh`
(the Dockerfile copies it from there).

---

## 0. Before anything: the auth bypass — FIXED, keep the pin anyway

**Historical, and resolved.** `meridian/api/deps.py` used to read `ENVIRONMENT` with a
`development` default and treat any non-production value as eligible for the
`MERIDIAN_DEV_AUTO_AUTH` bypass, which logged the caller in as the first principal — Raj
Malhotra, founder, clearance 4. That was issue #191, fixed in #192: the default is now
fail-closed and auto-auth requires `ENVIRONMENT` to be one of an explicit allowlist
(`development`, `test`, `local`) *and* the flag to be truthy.

`docker-compose.demo.yml` still pins `ENVIRONMENT=production` on the api service. It is now
genuine belt-and-braces rather than the only thing holding the line. Keep it — it costs
nothing and it means the deployment does not depend on the fix staying correct — and keep
verifying it (check 1 in step 6).

---

## 1. Build the image on your main machine

A Core 2 Duo compiling `psycopg` and `pydantic-core` wheels takes tens of minutes.

    docker build -f Dockerfile.api -t callosum-api:demo .
    docker save callosum-api:demo | gzip -1 > callosum-api-demo.tar.gz
    scp callosum-api-demo.tar.gz cloverssd@100.108.100.108:~/callosum-demo/dumps/
    ssh cloverssd@100.108.100.108 'gunzip -c ~/callosum-demo/dumps/callosum-api-demo.tar.gz | docker load'

**No swap needed.** `docker-compose.demo.yml` sets `image: callosum-api:demo` *and*
`build:`. Compose starts the tag when it exists and builds only when it does not, so the
server never builds and a dev machine still does — one file, no per-environment editing.

`.dockerignore` matters here. Without it the build context is **1.8 GB** (`.venv` 323 MB,
`frontend/node_modules` 786 MB, none of it COPYed by `Dockerfile.api`) and the build looks
hung before it runs an instruction. With it: 14 MB.

## 2. Precompute the data on your main machine

The server cannot run the scientific stack **at all** — see "The CPU is x86-64-v1" below.
It is not merely that it cannot embed. Ingest the corpus locally and ship the result.

Postgres dumps online:

    docker exec callosum-postgres pg_dump -U callosum -d callosum -Fc -f /tmp/callosum.dump
    docker cp callosum-postgres:/tmp/callosum.dump ./callosum.dump

**Neo4j does not.** `neo4j-admin database dump` on a running instance fails —

    Failed to dump database 'neo4j': The database is in use. Stop database 'neo4j' and try again.

— and Neo4j 5 **community** has no `STOP DATABASE`. Dumping to a host bind-mount fails
too (`AccessDeniedException: /dump`): the container is uid 7474, your directory is 1000.
Stop the container, dump from a one-shot container onto the volume, restart, copy out:

    docker stop callosum-neo4j
    docker run --rm -v callosum_neo4jdata:/data neo4j:5-community \
      neo4j-admin database dump neo4j --to-path=/data --overwrite-destination=true
    docker start callosum-neo4j
    docker run --rm -v callosum_neo4jdata:/data -v "$PWD":/out --user "$(id -u):$(id -g)" \
      busybox cp /data/neo4j.dump /out/neo4j.dump
    docker run --rm -v callosum_neo4jdata:/data busybox rm -f /data/neo4j.dump

Ship the dumps **and `schema/`** — `docker-compose.demo.yml` bind-mounts
`./schema/postgres.sql` as the Postgres init script. A bind mount whose source is missing
is created by Docker as an empty *directory*, and Postgres then fails to start with an
error that says nothing about a missing file.

    scp callosum.dump neo4j.dump cloverssd@...:~/callosum-demo/dumps/
    scp docker-compose.demo.yml .env.demo cloverssd@...:~/callosum-demo/
    scp -r schema cloverssd@...:~/callosum-demo/

### The CPU is x86-64-v1

The host is an **Intel Core 2 Duo E7500**: `ssse3 sse4_1`, no `sse4_2`, no `popcnt`. NumPy's
manylinux wheels are built with an **x86-64-v2** baseline and refuse to import:

    RuntimeError: NumPy was built with baseline optimizations:
    (X86_V2) but your machine doesn't support: (X86_V2).

That is a `RuntimeError`, not an `ImportError`, so the `try/except ImportError` around
`neo4j._optional_deps`' optional numpy import does not catch it. **Importing the Neo4j
driver kills the process and the API crash-loops before serving a request.**

`Dockerfile.api` therefore builds numpy from source for a baseline target before installing
the project. Do not "fix" this by uninstalling numpy — it would work, since nothing in
`src/callosum` or `meridian` imports it and its only hard dependant is `voyageai` (which
this deployment never calls), but removing a wheel to dodge an ISA mismatch leaves every
other extension module's baseline unverified.

## 3. Secrets

    cp .env.demo.example .env.demo
    # fill every blank; generate with:
    python -c "import secrets; print(secrets.token_urlsafe(32))"

`.env*` is gitignored and `.env.demo.example` is re-included by a negation, so the
template is tracked and the real file is not. Confirm with `git check-ignore .env.demo`
before committing anything — the pattern was an exact-match `.env` until this change,
which left `.env.demo` committable.

## 4. Cloudflare Tunnel

Dashboard > Zero Trust > Networks > Tunnels > Create tunnel > **Cloudflared**.
Copy the token into `CLOUDFLARE_TUNNEL_TOKEN` in `.env.demo`.

Add one public hostname on that tunnel:

| Field | Value |
|---|---|
| Subdomain | `api` |
| Domain | `cloverag.dpdns.org` |
| Service | `http://api:8000` |

`http://api:8000` — the container name on the compose network, not `localhost`.
cloudflared runs inside the stack, so nothing is published to the host and no inbound
firewall rule is needed anywhere.

**Or skip the dashboard entirely.** The whole tunnel can be created from the CLI:

    cloudflared tunnel login                 # browser, pick cloverag.dpdns.org
    cloudflared tunnel create callosum-demo
    cloudflared tunnel route dns callosum-demo api.cloverag.dpdns.org
    cloudflared tunnel token callosum-demo   # -> CLOUDFLARE_TUNNEL_TOKEN

A tunnel made this way is **locally-managed and has no remote ingress configuration**, so
a `--token` run has no route: the connector registers cleanly — four QUIC connections, no
errors — and the edge answers **503 on every path**. It reads as a backend fault and is
not one. `docker-compose.demo.yml` passes `--url http://api:8000` for exactly this reason,
which also makes the dashboard public-hostname step optional. Adding one anyway is
harmless; remote configuration takes precedence over `--url`.

`route dns` creates a **proxied** CNAME, so it flattens at the edge: `dig CNAME` returns
`NOERROR` with zero answers while `dig A` returns Cloudflare addresses. The record is
there. A local resolver that already cached the NXDOMAIN will keep failing for its TTL —
check against the zone's own nameserver before concluding the record is missing.

## 5. Bring it up

    docker compose -f docker-compose.demo.yml up -d
    docker compose -f docker-compose.demo.yml logs -f api

Expect the entrypoint to log: migrations, principal seed, `no MERIDIAN_OIDC_ISSUER —
skipping OIDC identity seed`. That last line is correct, not a warning.

## 5b. The demo selector

`MERIDIAN_DEMO_SELECTOR=true` in `.env.demo` is what makes `/demo` work. It is an
impersonation endpoint by design: any visitor may become any of the three seeded
identities. Safe here **only** because this stack serves fabricated minutes from
`data/demo/` and nothing else. Absent means off, and off answers 404.

Set `NEXT_PUBLIC_DEMO_PACK_ID` on Vercel from the seeded database — it is regenerated
by every seed and must never be hardcoded:

    docker compose -f docker-compose.demo.yml exec postgres \
      psql -U callosum -d callosum -tAc "SELECT id FROM board_pack LIMIT 1"

## 6. Verify — all six, before you share the link

    # 1. the bypass is unreachable
    docker compose -f docker-compose.demo.yml exec api printenv ENVIRONMENT   # => production
    docker compose -f docker-compose.demo.yml exec api printenv | grep -c DEV_AUTO_AUTH  # => 0

    # 2. anonymous request is refused
    curl -s -o /dev/null -w '%{http_code}\n' https://api.cloverag.dpdns.org/api/documents  # => 401

    # 3. memberships actually exist (fail-closed means no membership = no answers)
    docker compose -f docker-compose.demo.yml exec postgres \
      psql -U callosum -d callosum -c 'select count(*) from membership where active'   # => 3

    # KNOWN RED: this reports 15, not 3, after the entrypoint runs `callosum init`.
    # `cli.py:123` inserts a membership for EVERY row in `principal`, not the three it
    # seeds, so the 12 board members from seed_demo_board.py — deliberately membership-
    # less — are all granted access. Tracked in #201. Not a live exposure (the selector
    # answers 422 to anything but the three symbols) and check 6 is unaffected, but do
    # not edit this expectation to 15 to make it green.

    # 4. nothing is listening on the LAN
    ss -tlnp | grep -E '5433|7687|8000'    # => no output

    # 5. memory headroom under load
    free -h    # available should stay above ~1GB with the stack warm

    # 6. the RBAC gate actually differs by principal — ask the same question as
    #    Marcus (investor, clearance 1) and Raj (founder, clearance 4) and confirm
    #    the answers differ. THIS IS THE DEMO. If it does not differ, nothing else matters.

---

## Verified on the deployed stack — 2026-09-06, master `f21e00d`

Postgres, Neo4j and the API running on the home server; tunnel not yet attached, so the
HTTP checks were made from inside the compose network.

| # | check | result |
|---|---|---|
| 1 | bypass unreachable | `ENVIRONMENT=production`, `APP_ENV=production`, `DEV_AUTO_AUTH` vars: **0** |
| 2 | anonymous refused | `/api/documents` **401**, `/api/packs/<pack>` **401** |
| 3 | memberships | **15, expected 3 — RED, see #201** |
| 4 | nothing on the LAN | `ss -tlnp` empty; 0 published ports |
| 5 | headroom | 3.8 Gi available, full stack warm |
| 6 | RBAC differs | **reproduces the baseline exactly** |

    founder   visible=3  withheld_items=0  provider=demo-selector
    exec      visible=3  withheld_items=0  provider=demo-selector
    investor  visible=2  withheld_items=1  provider=demo-selector

Containment held: `'admin'`, `'raj@callosum.inc'` and `'FOUNDER'` all answered **422**, and
the select response carried only `['identity', 'provider']` — no role, no clearance.

Restored state matched the dump exactly: pack `66875926-64d0-495d-ba56-ba6d30462d8f`,
13 documents, alembic `0029_workspace_bootstrap`, `document` RLS `relrowsecurity=true`
`relforcerowsecurity=true` with 1 policy, Neo4j 263 nodes.

### Two traps that cost time

**`docker compose exec -T` consumes stdin.** Piping a script to `ssh bash -s` means the
first `exec -T` swallows the rest of it; the script stops silently and looks like it
succeeded. Put `</dev/null` on every `exec -T` that is not deliberately being fed.

**Testing over loopback HTTP cannot hold the session.** The cookie is `secure`, and clients
that honour that (Python's `http.cookiejar`, curl) will not send it over `http://`, so every
authenticated call returns 401 and looks like an authorization failure. Either go through
the tunnel or clear the flag **client-side** — never by turning off
`MERIDIAN_SESSION_HTTPS_ONLY`, which changes what the server issues.

### `callosum_app`'s password is a literal

`0004_app_role.py:33` hardcodes `APP_PASSWORD = "callosum_app"`, guarded by
`IF NOT EXISTS`, so `POSTGRES_APP_PASSWORD` in `.env.demo` has no effect through the normal
path — and because roles are cluster-level, a per-database dump does not carry the role at
all, so `pg_restore` fails on its 41 ACL entries if you do not create it first. Create it
explicitly, with the generated password, before restoring:

    CREATE ROLE callosum_app LOGIN PASSWORD '<POSTGRES_APP_PASSWORD>'
        NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;

`NOSUPERUSER` and `NOBYPASSRLS` are the load-bearing attributes: a superuser bypasses
`FORCE` RLS unconditionally.

---

## Frontend (Vercel)

Import `frontend/`, set `NEXT_PUBLIC_API_URL=https://api.cloverag.dpdns.org`, point
`cloverag.dpdns.org` at Vercel via CNAME.

Three known traps, all previously hit on this project:

1. **`NEXT_PUBLIC_*` is not inlined by Turbopack** — it compiles to a runtime lookup, so a
   build-time value can silently fail to land. After deploying, grep the built bundle for
   the literal `api.cloverag.dpdns.org`. If it is absent, the var did not take.
2. **Lightning CSS drops unprefixed `backdrop-filter`** in production builds, collapsing it
   to `-webkit-` which current Chrome rejects. This is the first prod build of the glass UI.
   Check it in a real browser, not just `next build`.
3. **CORS.** The API and frontend are different origins, so `meridian/api/main.py` needs
   `https://cloverag.dpdns.org` in its allowed origins.

   **`SameSite=None` is not needed** for the production hostnames, contrary to what this
   doc said before it was checked. The cookie is issued as
   `httponly; samesite=lax; secure` (verified on the deployed stack), and
   `cloverag.dpdns.org` and `api.cloverag.dpdns.org` are **same-site** — Lax is sent. It
   *is* needed if you test from a `*.vercel.app` preview URL, which is cross-site and
   fails exactly as described: login appears to succeed and every later call is 401.

---

## The cache question is moot — verified, not assumed

I proposed caching generation keyed by (question, principal). **That was wrong, and the
inspection you asked for is why.** Traced against master:

| Stage | Where it lives | Reached by the API? |
|---|---|---|
| Authorization | `deps.current_principal` -> `identity.resolve_principal_by_id` (JOIN on active membership, per request, never cached) | **yes** |
| Clearance enforcement | in-SQL `d.sensitivity <= %s` in `meridian/meetings.py:459,512` | **yes** |
| Tenancy | `store.pg(workspace_id)` + Postgres RLS | **yes** |
| Retrieval | `retrieve.graph_search` / `vector_search` | only via `retrieve.ask()` |
| Generation | `retrieve.ask()` -> `llm` synthesis | **no** |

`callosum.retrieve.ask()` is called from `cli.py:346` and `evaluate.py` only. **No HTTP
route reaches it.** The Meridian API is a board-governance surface — agenda, decisions,
minutes, packs, prep — and it does no LLM generation whatsoever. The single `llm.embed`
call sits in `intake_document`, a POST.

**So there is no generation on the API path to cache**, and the cache-key leakage
question does not arise. A read-only demo is fully live end to end: every result is
produced by the real authorization path against the real database, with no precomputed
prose anywhere and nothing to label as cached.

That also deletes three problems at once: no Ollama, no API key or spend cap, and no
dependency on your main machine being awake.

## The demo surface: `GET /api/meetings/{meeting_id}/material`

Existing route, `meridian/api/meetings.py:186`. **No new backend surface.**

```python
@router.get("/{meeting_id}/material")
def get_meeting_material(meeting_id: uuid.UUID, principal: CurrentPrincipal) -> domain.MeetingMaterial:
    return domain.meeting_material(str(meeting_id),
                                   workspace_id=principal.workspace_id,
                                   clearance=principal.clearance)
```

It returns `{documents: [...], withheld: N}` — the rows this caller may read, **and a
count of the ones they may not**.

### Why this one

Every other candidate filters rows and lets them vanish. Absence is not evidence: a
viewer cannot tell whether the investor sees fewer documents because of clearance or
because the demo data differs. This route *states the difference*:

**Measured**, 2026-09-05, master `b325e6a`, empty volume, migrations to head `0029`,
`callosum init`, four-document corpus ingested, `seed_demo_board.py`.

Pack "Board Meeting 14 — pack", published, 3 items. Route: `GET /api/packs/{pack_id}`.

**The pack id is regenerated by every seed and must not be hardcoded.** Two independent
clean-volume runs produced `6c43d827-f95f-4f24-9e2b-cac1413479e5` and then
`66875926-64d0-495d-ba56-ba6d30462d8f`. The counts below were identical across both,
which is the part that is stable. Set `NEXT_PUBLIC_DEMO_PACK_ID` from the seeded
database; the demo page refuses to guess and says it is unconfigured instead.

| principal | membership.role | HTTP | visible | withheld_items | returned |
|---|---|---|---|---|---|
| Raj Malhotra | founder | 200 | 3 | **0** | bm14_transcript, finance_fy27_forecast, compensation_review_CONFIDENTIAL |
| Priya Nair | exec | 200 | 3 | **0** | bm14_transcript, finance_fy27_forecast, compensation_review_CONFIDENTIAL |
| Marcus Webb | investor | 200 | 2 | **1** | bm14_transcript, finance_fy27_forecast |

Document sensitivities, as ingested: `board_meeting_14_transcript` 1,
`finance_fy27_forecast` 1, `compensation_review_CONFIDENTIAL` 3.

**Two distinct outcomes, not three.** Founder and exec are identical, because the
restricted document is sensitivity 3 and exec clearance is 3 — the filter is
`d.sensitivity <= clearance`, inclusive. The demo's visible split is
founder/exec vs investor. Do not frame it as three different results.

The response field is `withheld_items`, not `withheld`.

**How the sessions were established:** only the identity assertion was injected, via the
same `session.establish()` call the OIDC callback makes at `auth.py:154`. Authorization,
membership lookup, `ROLE_TO_CLEARANCE`, RLS and the sensitivity filter all ran as the
product's own code. `MERIDIAN_SESSION_HTTPS_ONLY=false` was set so the test client over
http would keep the cookie; it is a transport setting and does not touch authorization.

`withheld_items` is the whole demo in one number. The system is not merely hiding rows — it
knows what it is hiding and says so, without putting a restricted title on the wire.
That is ADR-018, and `meridian/meetings.py:487` explains why the count is aggregated in
a second SQL query rather than taken from the first.

Everything in that response is live:

| Stage | Code |
|---|---|
| session -> identity | `deps.current_session` |
| principal + clearance | `identity.resolve_principal_by_id` — JOIN on **active** membership, per request |
| clearance derivation | `membership.role` -> `ROLE_TO_CLEARANCE` (never `principal.clearance`) |
| tenancy | `store.pg(principal.workspace_id)` + RLS |
| row filter | `d.sensitivity <= %s`, `meetings.py:459` |
| withheld count | `d.sensitivity > %s`, `meetings.py:523` |

Nothing precomputed, nothing cached, no model call.

**The client cannot spoof it.** `clearance` is not a request parameter, and
`tests/test_openapi_input_guard.py` fails the build if it ever becomes one. So the demo
cannot be dismissed as "you just passed a different number" — the only input that
changes is who you are.

It also reuses `documents._DOCUMENT_SELECT`, which carries the per-caller
`superseded_by_id` redaction from migration `0024` — so one request demonstrates two
independent authorization behaviours.

### Cost

One extra request to obtain a meeting id (`GET /api/meetings`, pick the first), or the
frontend pins the demo meeting id. That is the entire setup.

### Runner-up, if a zero-parameter route is wanted

`GET /api/documents` (`meridian/api/documents.py:100`) — no path parameter at all,
filters at `documents.py:315`. Rejected as the primary because it has no `withheld`
field, so it cannot prove the filtering happened. Both are correctly workspace-scoped
via `principal.workspace_id`; neither has a tenancy gap.

### What this costs

There is no HTTP endpoint that answers a free-text question, so the demo cannot be
"ask the same question as Raj and as Marcus" over the web. That interaction exists only
in the CLI. The demo must instead show a **clearance-gated domain route** returning
different material to different principals — `meetings.py`'s document listing is the
natural one, since it filters `d.sensitivity <= clearance` in SQL.

Same proof, different surface: one request, two principals, different rows.

Building a real `/ask` endpoint is backend work and belongs to Devguru's half. Do not
let it into demo scope.
