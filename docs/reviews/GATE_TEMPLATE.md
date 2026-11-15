# P? exit gate — evidence packet

<!--
Copy to docs/reviews/YYYY-MM-DD-pN-gate-packet.md. Target: one page.
Every section is required. Delete these comments, not the sections.
Rules: rules.md §4. Worked example: 2026-07-29-p2-acceptance.md.
-->

| | |
|---|---|
| **Phase** | P? — <name from ROADMAP.md> |
| **Pinned master SHA** | `<sha>` — every figure below is measured at this commit |
| **Assembled by** | <session / person> on <date> |
| **Signed by** | _blank until signed — see §5_ |

## 1. Criteria and evidence

Criterion text is copied **verbatim** from `ROADMAP.md`. One row per criterion.

| # | Criterion (verbatim) | Kind | Evidence at the pin | Verdict |
|---|---|---|---|---|
| 1 | "…" | positive / negative | test file::name, route, row count, PR # | met / partial / not met |
| 2 | "…" | | | |

- **Positive** claim (X works): point at tests/rows.
- **Negative** claim (X cannot leak/happen): list the probes, and say how they were chosen.

## 2. Test run at the pin

```text
CALLOSUM_RUN_INTEGRATION=1 .venv/bin/python -m pytest   → <passed> / <failed> / <skipped>
cd frontend && npx jest                                    → <passed> / <failed>
.venv/bin/callosum eval-mechanism                          → <result>
```

Or link the green CI run for the pinned SHA.

## 3. Migration drill (clean volume)

```text
alembic upgrade head    → <ok / error>   head = <revision>
alembic downgrade base  → <ok / error>
alembic upgrade head    → <ok / error>
```

Or link the `migration-chain` CI job (`.github/workflows/`) for the pinned SHA — it runs this drill.

## 4. Not covered by this evidence

**Must not be empty.** List what the evidence never exercised: surfaces, methods, paths, data shapes, environments. An empty section means the packet is unfinished.

- …

## 5. Decision

Filled in by the signer only. The author of the work may not sign.

- **Verdict:** ACCEPTED / REFUSED
- **Gaps from §4 accepted as known:** …
- **Signed:** <name>, <date>
