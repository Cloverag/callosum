# Callosum public demo — home server deploy

Target: `api.cloverag.dpdns.org` -> Cloudflare Tunnel -> home server (2 cores, 5.8GB).
Frontend on Vercel at `cloverag.dpdns.org`.

Files in this directory go to the repo root, except `entrypoint.sh` -> `docker/entrypoint.sh`
(the Dockerfile copies it from there).

---

## 0. Before anything: the auth bypass

`meridian/api/deps.py:78` reads `ENVIRONMENT` with a **`development` default** and treats
any non-production value as eligible for the `MERIDIAN_DEV_AUTO_AUTH` bypass, which logs
the caller in as the first principal — Raj Malhotra, founder, clearance 4.

`docker-compose.demo.yml` pins `ENVIRONMENT=production` on the api service. **That line is
the only thing standing between this deploy and anonymous founder access.** Verify it
after every compose edit (step 6 has the check). The real fix — inverting the default to
fail-closed — is a backend change and belongs to Devguru.

---

## 1. Build the image on your main machine

A Core 2 Duo compiling `psycopg` and `pydantic-core` wheels takes tens of minutes.

    docker build -f Dockerfile.api -t callosum-api:demo .
    docker save callosum-api:demo | gzip | ssh cloverssd@100.108.100.108 'gunzip | docker load'

Then in `docker-compose.demo.yml`, swap `build:` for `image: callosum-api:demo` so the
server never tries to build.

## 2. Precompute the data on your main machine

No AVX on the server: nothing may embed there. Ingest the corpus locally, then ship the
result.

    # local
    callosum init && callosum ingest-doc ...        # whatever the demo corpus is
    pg_dump "$POSTGRES_DSN" -Fc -f callosum.dump
    docker exec callosum-neo4j neo4j-admin database dump neo4j --to-path=/data
    scp callosum.dump  cloverssd@100.108.100.108:~/
    scp neo4j.dump     cloverssd@100.108.100.108:~/

Restore on the server after step 4 brings the volumes up.

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

    # 4. nothing is listening on the LAN
    ss -tlnp | grep -E '5433|7687|8000'    # => no output

    # 5. memory headroom under load
    free -h    # available should stay above ~1GB with the stack warm

    # 6. the RBAC gate actually differs by principal — ask the same question as
    #    Marcus (investor, clearance 1) and Raj (founder, clearance 4) and confirm
    #    the answers differ. THIS IS THE DEMO. If it does not differ, nothing else matters.

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
3. **CORS.** The API and frontend are now different origins. `meridian/api/main.py` needs
   `https://cloverag.dpdns.org` in its allowed origins, and `MERIDIAN_SESSION_HTTPS_ONLY=true`
   (set in compose) means the session cookie also needs `SameSite=None` to survive a
   cross-site XHR — otherwise login appears to succeed and every subsequent call is 401.

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
