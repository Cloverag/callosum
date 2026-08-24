# P4 exit gate — evidence packet

**Pinned master SHA:** `5010282` · **Date:** 2026-08-24 · **Migration head:** `0025_meeting_document`
**Assembled by:** the author of the P4 leak-prevention work. **Not signed.** See *Standing and conflict*.

This packet contains evidence and gaps. **It contains no verdict.** `rules.md` §4: an author
may assemble evidence for work they wrote and may not sign the attestation for it. Whether
this evidence is sufficient is the maintainer's judgement, and nothing below should be read
as recommending an answer.

---

## 0. Figures, and that they derive at the pin

Every figure derives at `5010282`. The command beside each reproduces it — not a moving ref.

| | | Derivation |
|---|---|---|
| Commits | **506** | `git rev-list --count 5010282` |
| Migrations | **25**, head `0025_meeting_document` | `git ls-tree -r --name-only 5010282 -- meridian/migrations/versions/` |
| ADRs | **18** | `git show 5010282:docs/ARCHITECTURE_DECISIONS.md \| grep -c '^## ADR-'` |
| Product API | **69 operations** across **51 paths** | `app.openapi()`, `/auth` excluded |
| Backend tests | **788** passed, 5 deselected | `CALLOSUM_RUN_INTEGRATION=1 pytest -q`, real Postgres 16 + Neo4j |
| Frontend tests | **294** passed, 21 suites | `npx jest`, with `tsc --noEmit` clean |

The two test figures are a **real run**, not a collection. They are not derivable from the
SHA alone and are therefore the one class of figure in this packet a reader must take on
the record of the run rather than reproduce from git.

---

## 1. The criteria, verbatim

Quoted from `ROADMAP.md:441-442` exactly. A paraphrased criterion is a criterion the packet
chose for itself.

> **Exit:** membership is authorized/audited; document lifecycle is visible; restricted titles,
> text, quotes, graph facts, and hints cannot leak.

Three clauses, taken separately below. **They are not the same kind of claim**, and the
difference decides how much the evidence can carry — see §5.

---

## 2. Criterion 1 — "membership is authorized/audited"

### Authorized — evidence

| Evidence | Where |
|---|---|
| Clearance is re-derived from the caller's **active membership on every request**, never from the session | `meridian/api/deps.py` — `current_principal` |
| `workspace_id` and `clearance` are **never request inputs**; the build fails if either name appears anywhere in the schema, including nested in a body | `tests/test_openapi_input_guard.py` — **21 tests** |
| Cross-workspace access is refused at the database, not only in the domain | `tests/test_tenancy_guard.py` — **16 tests** |
| Session/identity resolution | `tests/test_auth_session.py` — **24 tests** |
| RLS `ENABLE` + `FORCE`, runtime connects as non-superuser `callosum_app` | `schema/postgres.sql`, every migration's `tenant_isolation` policy |

### Audited — two gaps, stated as findings rather than as evidence

**Board-member mutation is unaudited.** Two files, deliberately named separately — an
earlier draft of this packet conflated them, and a citation a reader can follow to a
contradiction is the defect class this packet exists to avoid:

- **Routes** live in `meridian/api/board_members.py` — **4** mutating
  (`POST` :93, `PATCH /{id}` :111, `POST /{id}/deactivate` :130, `POST /{id}/reactivate` :148).
  `grep -cE '@router\.(post|patch|put|delete)' meridian/api/board_members.py` → **4**.
- **Domain logic** lives in `meridian/board_members.py`, which contains **0** audit writes.
  `grep -c 'record_audit_event' meridian/board_members.py` → **0**. The domain module is the
  right place to look: every aggregate that *is* audited writes from its domain module, not
  its router — the sole exception, `meridian/api/conflicts.py`, appears in the enumeration
  below.

So a board member can be created, have their role or voting status changed, be deactivated
and be reactivated, and the append-only trail records none of it — even though
`audit.AGGREGATE_TYPES` already contains `"board_member"`.

**The `membership` table has no product writer at all.** It is the access-control row —
principal, workspace, role, **clearance** — and the only writer in the repository is
`src/callosum/cli.py:125`. There is no API, and therefore no audited path, by which a
principal's clearance in a workspace is granted, changed or revoked.

Audit events present in a live workspace, for contrast:

```
document    created      41
document    superseded   15
meeting     item_added    5
resolution  status_changed 6
```

Document and meeting lifecycle is audited. Membership is not, on either reading of the word.

**Which reading applies is a judgement this packet does not make.** `membership` (the
access-control row) and `board_member` (the domain object — a person on the board) are
different tables. The criterion says "membership". Both are unaudited, so the gap exists
under either reading, but their severity differs and that difference is the maintainer's
to weigh.

---

## 3. Criterion 2 — "document lifecycle is visible"

Every state a document can be in, and the surface that shows it:

| State | API | UI |
|---|---|---|
| Ingested | `POST /api/documents/intake` → `GET /api/documents` | `/documents` list |
| Refused extraction (quarantined) | `GET /api/documents/quarantine` | `/documents` → Quarantine tab, with count |
| Superseded / current | `superseded_by_id`, `revision` on the document | `Superseded` badge; `v2`/`v3` badges; current revision marked |
| Full revision history | `GET /api/documents/{id}/versions` | `History` disclosure per row |
| Assigned as meeting material | `GET /api/meetings/{id}/material` | `Material` panel on `/meetings` |
| Withheld above clearance | `withheld` count on the chain and on material | `N withheld` via `FieldValue` |

Tests bearing on this clause: `test_documents_api.py` **39**, `test_document_versions.py`
**20**, `test_meeting_material.py` **14**.

**Two visibility limits, measured rather than asserted:**

- `/meetings` renders only **scheduled** meetings (`scheduledOnly` in `app/meetings/page.tsx`),
  so material assigned to a `draft` meeting is reachable by API and **not reachable in the UI**.
- Intake is **text-only** (`raw_text`); there is no upload path. `FEATURES.md` lists
  PDF/DOCX/PPTX and OCR as future work, so this is recorded scope, not omission — but a
  document that arrives as a file has no lifecycle in this product at all.

---

## 4. Criterion 3 — "restricted titles, text, quotes, graph facts, and hints cannot leak"

### What is enforced

| Control | Evidence |
|---|---|
| Filter-before-retrieval: the clearance predicate is in the SQL `WHERE`, never applied in Python | `documents.py`, `packs.py`, `meetings.py` |
| Every clearance-filtered collection **declares** count-or-erase, or the build fails | `tests/test_withheld_discipline.py` — **15 tests**, ungated |
| No document-bearing endpoint returns confidential material to a low-clearance caller | `tests/test_p4_leak_sweep.py` — **6 tests**, sweeping **26 GET** and **101 write** operations |
| A withheld successor's id is **nulled per caller** — ids are `uuid5` over a public namespace, so an id is a content-confirmation oracle | ADR-017; `_DOCUMENT_SELECT` |
| Existence oracles answer **404, not 403**, and a hidden document answers **identically** to an absent one | `test_document_versions.py`, `test_meeting_material.py` |
| A server error string reaches a screen through **one function**; a source scan fails the build otherwise | `frontend/__tests__/error-text-discipline.test.ts` |
| Quarantine rows (quote + proposed graph fact + document id) are clearance-filtered by INNER JOIN | `documents.list_quarantine` |

### How the probes were chosen — stated because it is the judgement

This clause is a **negative** claim. It is never proven by evidence; what is actually
asserted is that the probes chosen would have found a leak had there been one. **I chose
them, for defences I wrote.** That conflict cannot be resolved inside the packet, so the
method is made visible instead, and a reader who can see how the list was arrived at can
disagree with it.

1. **Endpoints were not enumerated by hand.** The sweep walks `app.openapi()` and calls
   what it finds. A route added later joins by existing.
2. **Routers were not enumerated by hand either** — added 2026-08-24 after the sweep was
   found to be building its schema from a hand-written list of 3 routers out of 12, so it
   had been walking a quarter of the product while every assertion passed.
3. **Request bodies are synthesised from the schema**, so an endpoint that gains a required
   field keeps reaching the domain instead of silently 422ing and passing by never arriving.
4. **Needles are specific confidential material** — a title, a body string, a document id, a
   withheld revision id — not arbitrary strings. A sweep that fired on any unfamiliar text
   would fire on every error message and be disabled within a week.
5. **Assertions are against the raw response body**, not parsed fields, because the leak that
   actually happened in this phase (`superseded_by_id`, three surfaces at once) was in a
   field nobody was checking.
6. **Every control above was mutation-tested**: the defence was disabled, the test was
   confirmed to fail, the defence was restored. A test never watched failing may assert nothing.

**What that method does not cover is §6.** The probes are chosen by walking the schema, so
the sweep is complete with respect to *reachable HTTP operations* and says nothing about any
disclosure that does not travel through one.

---

## 5. Clean-volume full-chain migration drill

Run against a **freshly created empty database** (`callosum_gate`) on the project's Postgres
16 image, so the dev volume was neither destroyed nor reused. Base schema applied by
`psql -f schema/postgres.sql` (0 errors), then:

| Leg | Result |
|---|---|
| **Forward**, empty → head | **PASS** — 25 upgrades, `0001` → `0025_meeting_document` |
| **Reverse**, head → base | **FAIL** — 7 downgrades, then `0019_composite_tenant_fks` aborts |
| Forward again | not reached |

```
psycopg.errors.DependentObjectsStillExist: cannot drop constraint
decision_id_workspace_uq on table decision because other objects depend on it
```

**Root cause, traced rather than guessed.** `0014_resolution` and `0015_commitment` each
create a *composite* FK onto `decision(id, workspace_id)` — `resolution_decision_fk` and
`commitment_decision_fk`, both `ON DELETE RESTRICT`. `0019_composite_tenant_fks` then adds a
**second** composite FK on the same columns of the same tables —
`resolution_decision_workspace_fk` and `commitment_decision_workspace_fk`, both
`ON DELETE CASCADE`. Its `downgrade()` drops the pair it created and then drops
`decision_id_workspace_uq`, which the 0014/0015 pair still depends on.

The failure rolled back cleanly; the database remained at `0025`. **The drill is
non-destructive, and the reverse leg does not pass.**

**A second, live consequence.** Verified on the working database, not only the drill copy:

```
commitment.commitment_decision_fk            ON DELETE RESTRICT
commitment.commitment_decision_workspace_fk  ON DELETE CASCADE
resolution.resolution_decision_fk            ON DELETE RESTRICT
resolution.resolution_decision_workspace_fk  ON DELETE CASCADE
```

Duplicate composite foreign keys with **contradictory** delete semantics. `RESTRICT` is the
stricter and therefore governs, so deleting a decision that has a resolution or a commitment
is refused — which is the behaviour `0021_fix_composite_fk_cascades` exists to have removed.
`0021` restored cascade semantics on the constraints it knew about and did not remove the
older duplicates.

Neither of these is named by P4's criteria. Both were found by assembling this packet, and
both are filed as **#165**.

---

## 6. Not covered by this evidence

`rules.md` §4: *a packet whose "not covered" section is empty is not a stronger packet — it
is an unfinished one.* This section is the honest list, and it is the part of the packet most
worth reading adversarially.

### On criterion 1

1. **Membership changes are unaudited.** Not a coverage gap — a **gap in the criterion
   itself**, stated in §2. There is no evidence that "audited" holds, because the writes do
   not exist. Filed as **#166**.
2. **No evidence is offered that a clearance grant is authorized**, because there is no
   product path that performs one. `cli.py` is operator-only and unaudited.

### On criterion 3

3. **This is detection, not prevention.** Nothing structurally stops a domain exception
   carrying restricted content — `meridian/api/errors.py:170` passes any unregistered
   exception's `str()` to the client. The sweep catches a leak *only when the leaked content
   matches a needle in its scene*. A leak of confidential material not represented in the
   scene passes.
4. **The frontend chokepoint constrains composition, not emission.** `lib/error-text.ts`
   cannot filter and does not try; the client has no way to know which strings are restricted.
   Its value is that policy lives in one place.
5. **Only `application/json` request bodies are swept.** Nothing uses multipart today; this
   stops being true the day upload lands.
6. **The sweep is HTTP-only.** No probe covers the CLI (`callosum ask`), direct database
   access, logs, tracebacks, or the Neo4j gateway. `retrieve.py` discloses a withheld count
   by design and is out of P4's scope, but nothing in this packet demonstrates that.
7. **The sweep's scene contains one confidential document and one withheld revision.** Leak
   classes requiring a richer fixture — several documents at different levels, a chain longer
   than two, cross-workspace material — are not exercised.
8. **No adversarial testing by anyone other than the author.** Every probe here was written
   by the person who wrote the defences. §5 makes the selection method visible precisely
   because it cannot make it independent.

### On the packet itself

9. **The reverse migration leg does not pass** (§5, **#165**). A required element of a gate
   packet is present and failing.
10. **Duplicate composite FKs with contradictory delete semantics are live** (§5, **#165**),
    defeating `0021`'s intent on two tables.
11. **`scripts/eval.sh` has not been run.** It is deliberately the maintainer's to spend, so
    no retrieval-quality figure appears anywhere in this packet.
12. **The two test figures cannot be derived from the pin.** They are the record of a run.
13. **CI's `CALLOSUM_POSTGRES_DSN` is ignored.** `src/callosum/config.py:21` sets
    `SettingsConfigDict(env_file=".env", extra="ignore")` with **no** `env_prefix`, so the
    settings read `POSTGRES_DSN` / `POSTGRES_APP_DSN` and the two `CALLOSUM_`-prefixed
    variables the workflow exports (`ci.yml:22-23`) are silently discarded. **Follow the
    right file:** `meridian/api/config.py:20` *does* set `env_prefix="MERIDIAN_"` — it is a
    separate settings class for the web application, and it is not the one being described.

    CI passes because its own service block publishes the database on **both** ports
    (`ci.yml:34-36`, `5432:5432` and `5433:5432`) while the default DSN points at `5433`,
    so the discarded variable and the default happen to reach the same database.
    (`docker-compose.yml:10` publishes only `5433`; the dual mapping is CI's alone.)

    **Calibrated:** this is configuration that lies, not a weakened test. Both discarded
    variables name the same two roles the defaults already encode — `callosum` superuser and
    `callosum_app` non-superuser against the same database — so the RLS distinction the
    gated suite depends on is intact. What is lost is the ability to point CI at a different
    database by setting the documented variable, and any confidence that the workflow's
    `env:` block means what it appears to.

---

## Standing and conflict

I assembled this. I also wrote `0024`, `0025`, ADR-017, ADR-018, the version chain, meeting
material, the withheld-discipline test, and the write-path extension of the leak sweep —
which is to say, most of what §4 offers as evidence for criterion 3.

`rules.md` §4 forbids me signing it, and that rule exists for this exact shape. The two
findings in §5 and the two in §2 were found by reading the criteria adversarially against
the code, which is the closest an author can get to reviewing themselves — and it is not
close enough to substitute for a second reader.

**The maintainer signs or refuses.** Nothing in this document is a recommendation.
