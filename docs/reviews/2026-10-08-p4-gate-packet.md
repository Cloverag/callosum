# P4 exit gate — evidence packet (second attempt) — ACCEPTED 2026-10-08

| | |
|---|---|
| **Phase** | P4 — Board workspace, members, and source intake |
| **Pinned master SHA** | `7f8a84ba57820981af4eb968cdfd1b1c2c3873d5` (merge of #223) — every figure below is measured at this commit |
| **Assembled by** | Claude Code session, 2026-10-08. This session wrote #223, which this packet cites as evidence for criterion 3 — so it may assemble, not sign (`rules.md` §4) |
| **Previous attempt** | [2026-08-24 packet](./2026-08-24-p4-gate-packet.md) — **REFUSED** 2026-08-25: *"#166 is still unresolved, and criterion 1 explicitly requires membership to be both authorized and audited."* |
| **Signed by** | Maintainer, 2026-10-08 — see §5 |

## 1. Criteria and evidence

Criteria verbatim from `ROADMAP.md` (P4): **"Exit:** membership is authorized/audited; document lifecycle is visible; restricted titles, text, quotes, graph facts, and hints cannot leak."

| # | Criterion (verbatim) | Kind | Evidence at the pin | Verdict |
|---|---|---|---|---|
| 1 | "membership is authorized/audited" | positive | **Authorized:** `POST /api/membership` and `POST /api/membership/{id}/revoke` (`meridian/api/workspaces.py`). Workspace comes from the session, never the body; the actor's clearance is resolved from the DB; a grant above the actor's own clearance is refused (`EscalationDeniedError`, `meridian/workspaces.py:262`); the last active member cannot be revoked (409). **Audited:** each grant, revoke and workspace bootstrap writes an `audit_event` naming the actor. Tests: `test_workspace_membership_api.py` (7, incl. `test_a_signed_in_founder_can_grant_through_the_route` asserting the audit row, `test_a_workspace_id_field_in_the_body_does_not_exist_to_supply`, cross-workspace refusals), `test_workspace_bootstrap.py::test_the_bootstrap_itself_is_audited` + refusal-leaves-no-audit, `test_board_member_audit.py` (7). Landed via #180, #181, #186, #189, #190, #207 — the #166 work the August refusal named | **met** |
| 2 | "document lifecycle is visible" | positive | Intake (#128), sensitivity ceiling (#144), tenant-scoped duplicate detection (`0022`), quarantine (`GET /api/documents/quarantine`), versions by supersession (`0024`, ADR-017), meeting assignment (`0025`). All visible on `/documents`. Unchanged since the August packet, which found this criterion met | **met** |
| 3 | "restricted titles, text, quotes, graph facts, and hints cannot leak" | **negative** | **API:** `tests/test_p4_leak_sweep.py` walks `app.openapi()` over **every** product router (discovered by `pkgutil`, so new routes join automatically), calls every reachable GET **and write** as a low-clearance caller, and asserts no confidential title, text, quote or **document id** (derivable `uuid5` → "hints") appears in the raw response body. It includes a test proving the sweep fails when something leaks, and one proving the low reader still sees what they're entitled to. `test_withheld_discipline.py` makes every clearance-filtered collection declare count-or-erase (ADR-018). `test_openapi_input_guard.py` makes `workspace_id`/`clearance` unsuppliable. **Client bundle:** #223 removed the restricted graph fact and confidential title that shipped to every visitor (#213 C2); `frontend/__tests__/graph-bundle-public.test.ts` fails on the pre-#223 code (2/2) and passes at the pin | **met, within §4's limits** |

**How the criterion-3 probes were chosen:** the API sweep is generated from the OpenAPI schema rather than a hand list, because the August leak (`superseded_by_id`) arrived in a *new field*. The bundle test exists because #213 found the one leak path the API sweep cannot see: data compiled into the frontend.

## 2. Test run at the pin

CI run [37671422015](https://github.com/Cloverag/callosum/actions/runs/37671422015) on `7f8a84b`, all **success**:

```text
Backend CI, gated tier (CALLOSUM_RUN_INTEGRATION=1, Postgres 16 + Neo4j)  → 959 passed, 0 failed, 5 deselected (llm), 0 skipped
Frontend CI (Jest)                                                       → 310 passed / 24 suites
callosum eval-mechanism                                                   → NOT RUN at the pin (not in CI; see §4)
```

0 skipped matters: the leak sweep and membership tests skip at module level without the integration flag, so a skip count of 0 shows they ran.

## 3. Migration drill (clean volume)

The `migration-chain` job in the same CI run (fresh Postgres container): `alembic upgrade head` → `alembic downgrade base` → `alembic upgrade head` — **success**. Head `0029_workspace_bootstrap`.

## 4. Not covered by this evidence

**Criterion 1**
- **Who may grant is anti-escalation only, not founder-only.** Any active member can grant or revoke roles at or below their own clearance — an investor can add another investor. The code does what the ruling says; whether that is the *authorization policy you want* is a judgement for the signer.
- `callosum init` (CLI) seeds memberships for every `principal` row with **no audit event** — explicitly ruled out of #166 (no actor exists to attribute). #201: it grants to more principals than it seeds.
- The demo identity selector (`/auth/demo/select`) was not examined as a membership path. It resolves only already-active memberships, per its docstring.
- 28 other mutating routes write no audit event (#168) — **ruled out of P4**, not evidence either way.

**Criterion 3**
- The sweep reads **response bodies** of one low-clearance caller in the caller's own workspace. Not probed by it: response headers, timing, status-code differences beyond the 404-not-403 pairs already tested, and cross-workspace callers (covered by P1 tenancy tests, not by this sweep).
- **The answer path (`retrieve.ask`) has no HTTP route**, so the sweep cannot reach it. It is filtered before retrieval in SQL and Cypher (frozen core), but `eval-mechanism` (the RBAC stratum) was **not run at this pin**. Its last recorded run predates it.
- **Prompt injection into answers** (#220, fix in open PR #219, with a known fence-escape defect) — not a leak path for restricted content, since restricted rows are never fetched, but unmeasured.
- **Client bundle:** the new test guards `graph.ts` and `insights.ts` only. Other local `frontend/src/lib/*` modules and the built JS were not scanned.
- The **live demo deployment** (Vercel → tunnel → server) was not probed. Evidence is CI only.
- #198: `packs.ts` header forbids rendering the withheld count ADR-018 requires — the API returns it; the UI may under-disclose. This is a disclosure gap, not a leak.

**The packet itself**
- Assembled by a session that wrote #223, which this packet uses as evidence. No independent reviewer has checked this packet.
- #223 was merged by the maintainer without a separate review.
- Open PR #215 touches the same frontend files and must be rebased onto the pin.

## 5. Decision

Filled in by the signer only. The author of the work may not sign.

- **Verdict: ACCEPTED.** P4 is accepted at `7f8a84b`. The product track moves from 3 / 13 to **4 / 13** (P0, P1, P2, P4; P3 stays frozen and unaccepted).
- **The maintainer's words (chat, 2026-10-08):** *"pass, investors adding investors is fine but also need permisoon drom another person like manger of this workspace"*
- **What that means, clarified with the maintainer in the same session:**
  - The §4 point on who may grant is **accepted**: a non-admin member may grant at or below their own clearance.
  - **New requirement, not a condition of this gate:** such a grant must also be approved by an active **founder or admin** of the workspace. Founders and admins grant directly. Not built at the pin; tracked in **#225**.
  - The maintainer chose "pass now, build it later" over "fail until built".
- **Gaps from §4 accepted as known:** all of them as listed. None is a known leak.
- **Signed:** maintainer (Raghav, `Cloverag`), 2026-10-08, given in chat and recorded here by the assembling session. Per `rules.md` §5 a recorded comment is not proof of who decided: the maintainer's merge of this PR is the act of signing.
