# Control matrix

**Not a certification.** This maps SOC 2 Trust Services Criteria (shaped),
GDPR/UK GDPR (lite), and board-OS / AI governance onto **code and tests that
exist**, plus residual risks that stay open. Status is `met`, `partial`, or
`not claimed`.

Callosum/Meridian is a **research/product prototype** with a **public synthetic
demo**. Demo identities (Raj Malhotra, Priya Nair, Marcus Webb) are **fictional**.
There is no real board, no real compensation, and no real emails. The identity
selector is an **authentication bypass**, allowed **only** because that database
is fabricated (`docs/deploy/DEMO_AUTH_SPEC.md`). Memory writes still require a
**human approve**; the model cannot write Neo4j.

Do not quote this file as “SOC 2 certified”, “ISO 27001 certified”, or “GDPR
compliant product”.

---

## Positioning (reuse this block)

- Prototype + public **synthetic** demo.
- Fictional principals; fabricated minutes.
- Selector = impersonation, demo-only.
- Human approval for every graph write.

---

## SOC 2 TSC (shaped, not certified)

| Criterion | Control | Evidence | Status |
|---|---|---|---|
| CC6 Access | OIDC + httpOnly signed session; session holds identity, never clearance | `meridian/api/auth.py`, `session.py`, ADR-009 | met |
| CC6 Access | Clearance re-derived from `membership.role` every request | `callosum.identity`, `meridian/api/deps.py` | met |
| CC6 Access | Postgres RLS ENABLE+FORCE; app role `NOSUPERUSER NOBYPASSRLS` | ADR-002/003, `0004_app_role` | met |
| CC6 Access | Client cannot send `workspace_id` or `clearance` | `tests/test_openapi_input_guard.py`, ADR-013 | met |
| CC6 Access | Pre-retrieval SQL/Cypher sensitivity filter, fail-closed | `src/callosum/retrieve.py` | met |
| CC6 Access | Unknown OIDC subject refused, never auto-provisioned | ADR-011 | met |
| CC6 Access | Dev auto-auth is an allowlist, fail-closed by default | `#192`, `deps.DEV_AUTH_ENVIRONMENTS` | met |
| CC6 Access | Per-object `acl_grant` is unused in retrieval | `AGENTS.md`, `#213` H5 | partial |
| CC7 Logging | Append-only `audit_event`; app cannot UPDATE/DELETE | `meridian/audit.py`, `0016_audit_event` | met |
| CC7 Logging | `query_log` records question, plan, hits, answer, `denied_count` | `schema/postgres.sql` | met |
| CC7 Logging | Not every mutating route writes an audit event | `#166`, `#168` | partial |
| CC7 Logging | No SIEM, no alerting, CP-F observability deferred | `#93` | not claimed |
| CC8 Change | Frozen core; eval/mechanism gates; PR + CI | `CONTRIBUTING.md`, `.github/workflows/ci.yml` | met |
| CC8 Change | Migration immutability checksums | `meridian/migrations/checksum.py` | met |
| CC8 Change | GitHub required reviews / no force-push | operator clicks; `docs/compliance/GITHUB.md` | partial |
| CC9 Vendor | Named processors | `docs/compliance/PROCESSORS.md` | met |
| A1 Availability | Manual dumps documented | `docs/deploy/DEPLOY.md` | not claimed as DR |
| C1 Confidentiality | HTTPS cookie on demo; tunnel; docs off in production | `docker-compose.demo.yml`, `docs_enabled()` | partial |
| C1 Confidentiality | Encryption at rest, customer KMS | `FEATURES.md` ⬜ | not claimed |

---

## GDPR / UK GDPR (lite — synthetic only)

Lawful basis for the demo: **no personal data of a natural person**. The
principals and minutes are authored fiction. If a visitor pastes real text into
the demo, treat it as accidental and delete on request (`docs/privacy.md`).

| Article | Control | Evidence | Status |
|---|---|---|---|
| 5 / 6 | No real personal data in the demo corpus | `data/demo/`, this matrix | met (synthetic) |
| 13 / 14 | Public notice + cookie explanation | `docs/privacy.md`, `/privacy` | met |
| 17 | Erasure path for accidental real text | contact in `docs/privacy.md` | partial (manual) |
| 28 | Processors named | `docs/compliance/PROCESSORS.md` | met |
| 30 | Records of processing | this matrix + processors file | partial |
| 32 | Transport via Cloudflare; session `Secure` on demo | `DEPLOY.md`, compose | partial |
| 32 | Encryption at rest | `FEATURES.md` ⬜ | not claimed |
| 33 / 34 | Incident process | `docs/compliance/INCIDENT_RESPONSE.md` | partial (process only) |
| Retention | `query_log` / `audit_event` intent: volume reset or 90 days | `docs/privacy.md` | partial (no automated TTL) |

A production tenant with real board documents would need a DPA, residency,
deletion engine, and a ban on `MERIDIAN_DEMO_SELECTOR`. That is **not this
deployment**.

---

## Board-OS / AI governance

| Invariant | Evidence | Status |
|---|---|---|
| No LLM write path to Neo4j | extraction → `proposed_change` only; `store.approve()` is the mutation | met |
| No relationship without a located verbatim quote | `ingest.locate()`, `extract.verify()` | met |
| Rejected extractions quarantined, never dropped | `extraction_failure` | met |
| Human approves every memory update | CLI `approve`, conflicts UI | met |
| Permission filter before retrieval, not after | SQL + Cypher in `retrieve.py` | met |
| Withheld **count** vs withheld **title** contracts | ADR-018, `tests/test_withheld_discipline.py` | met |
| Membership re-checked per request | `deps.current_principal` | met |
| EU AI Act high-risk | Not claimed. No automated legal, credit, or hiring decision. Graph writes are human-approved. | not claimed |

---

## Residual risks (do not paper over)

| Risk | Tracker | Notes |
|---|---|---|
| `acl_grant` unused in retrieval | `#213` H5 | Table exists; predicates do not use it |
| `callosum init` over-grant | `#201` | **Addressed:** membership INSERT is `WHERE p.email = ANY(%s)` over `DEMO_PRINCIPALS` (`src/callosum/cli.py`, `tests/test_init_membership_scope.py`) |
| `schema/postgres.sql` global `UNIQUE` on `content_hash` | `#195` | Fresh volume vs `0022` composite |
| `upsert_document` Default-Workspace-only | `#196` | Frozen ingest path |
| Session GUC not `SET LOCAL` | `#10` | `set_config(..., false)` is session-scoped |
| Demo selector is an auth bypass | `DEMO_AUTH_SPEC.md` | Fabricated data only |
| `query_log` stores full Q&A, no TTL | this matrix | Synthetic; still a log of whatever a visitor typed |
| Supply-chain CI | Dependabot, CodeQL, `pip-audit`, frontend `npm audit` | met as files; GitHub must enable scanning alerts |
| No `LICENSE` historically | `LICENSE` | MIT as of this stack |
| Branch protection | `docs/compliance/GITHUB.md` | Not encoded in git |

---

## Access inventory (people, not code)

Fill names. Rotate when someone leaves.

| System | Purpose | Operator (fill in) |
|---|---|---|
| GitHub `Cloverag/callosum` | Source, CI, advisories | |
| Vercel | Demo frontend | |
| Cloudflare | Tunnel / DNS | |
| Home SSH / demo host | API + Postgres + Neo4j | |
| Ollama Cloud | Default LLM | |
| Keycloak (local only) | Dev IdP | n/a on public demo |

---

## Related files

- `docs/privacy.md` — public notice
- `docs/compliance/PROCESSORS.md` — vendors
- `docs/compliance/INCIDENT_RESPONSE.md` — break-glass
- `docs/compliance/GITHUB.md` — settings you must click
- `SECURITY.md` — vulnerability disclosure
