# R8-R13 handover

**Original handover:** 2026-07-16 08:24:44 IST
**Consolidated through:** 2026-07-16 10:47 IST
**Repository:** Callosum
**Branch:** `master`
**Last pushed commit:** `a68a8ae docs: add governed Meridian workflow prototype`

## Current status

R8-R11 are implemented and deterministically verified, but are **not formally accepted**.
R12 is implemented with deterministic and live-store RBAC coverage, but its live retrieval
metrics are not yet recorded. R13 has a prepared handoff package, but cannot be formally
approved before the clean R8-R12 evaluation is reviewed. **P0 is not authorized.**

The only blocking dependency is the live Ollama environment: Ollama is unavailable at
`http://localhost:11434`, so embeddings and the clean seeded benchmark cannot run. Do not
manufacture CSV rows, acceptance marks, or a baseline tag to bypass that gate.

## Completed work

### R8-R11 benchmark and corpus work

- R8: Meeting 14 exercises reviewed aliases (`Raj`, `Rajesh Malhotra`, `R. Malhotra`) and a
  same-name negative control; `ALIAS_OF` remains evidence-backed and never auto-merges.
- R9: Finance and Sales FY27 forecasts preserve conflicting `$12.0M` and `$11.6M` claims
  with separate sources; no unsupported winner is seeded.
- R10: Meeting 16 has an explicit reference and a deliberately ambiguous no-link case.
- R11: TXT, Markdown, VTT, DOCX, PDF, and restricted fixtures are covered. Two additional
  realistic noisy email records add source-backed `messy_email` cases for vendor-security and
  SOC 2 follow-up ownership.
- Every `eval/gold.jsonl` question now has machine-readable `source_documents`; see
  `eval/gold-traceability.md`. The evaluation report renders those source stems per question.

### R12 candidate grounding and RBAC

- Runtime grounding receives canonical candidates only from clearance-filtered vector hits.
- Neo4j repeats the chunk-clearance predicate before names reach the planner, and names outside
  the candidate list are discarded before traversal.
- `tests/test_candidate_rbac_integration.py` is an opt-in live Postgres/Neo4j test. It creates
  isolated sensitivity-1 and sensitivity-3 chunks, proves low clearance receives only the
  public candidate, proves high clearance receives both, verifies Neo4j defence in depth, and
  cleans up without resetting Docker volumes.

### R13 handoff and evaluation controls

- `docs/research-handoff.md` records the named baseline, reproducibility commands, readiness
  matrix, frozen-core exception process, and P0 decision gate.
- `docs/templates/r8-r12-evaluation-review.md` standardizes baseline comparison and reviewer
  approval evidence.
- `docs/findings.md`, `ROADMAP.md`, and this handover distinguish implemented work from
  accepted research evidence.

### DOCX visual QA

- LibreOffice 26.2.4 is installed locally.
- `scripts/render_docx_qa.ps1` renders the DOCX risk-memo fixture to PDF; the 2026-07-16
  visual review at 150 DPI found a readable one-page layout with no clipping, overlap, or
  unexpected page break. See `docs/docx-visual-qa.md`.
- The local LibreOffice command emits a benign library-prefix warning but returns exit code 0
  and creates the PDF; a missing PDF or non-zero exit is a QA failure.

### Meridian design research (not product implementation)

- Reviewed the supplied Meridian Dashboard prototype for its board-workspace shell, persistent
  Ask Meridian framing, and source badges.
- Added `design/meridian-governed-workflows.html`, a standalone clickable artifact for grounded
  chat, individual approval review, and citation inspection.
- Added `design/README.md` and `docs/ux/meridian-governed-workflows.md`, including PRD
  traceability and open questions for P0/P3.
- The artifact is static/local only: it has no API, persistence, identity, authorization,
  telemetry, graph write, or external action. Its simulated approval buttons alter browser
  state only and explicitly say that no graph change occurs.

## Verification

- `.venv\Scripts\pytest.exe -q`: `36 passed, 1 skipped, 5 deselected`.
- `CALLOSUM_RUN_INTEGRATION=1 .venv\Scripts\pytest.exe -m integration -q`:
  `1 passed, 41 deselected`.
- `node --check C:\tmp\meridian-governed-workflows.js` passed after extracting the static
  prototype's inline script.
- `git diff --check` passed before each committed change.
- Current local Docker Postgres and Neo4j services were healthy during integration testing.

## Immediate next action

Restore Ollama **without changing application code**, then run only the health check:

```powershell
ollama serve
# In another terminal:
ollama pull bge-m3
.venv\Scripts\callosum.exe doctor
```

Record the exact provider/model result in a new timestamped handover. If `doctor` succeeds,
obtain confirmation that local Docker volumes may be deleted before running the destructive
`scripts/eval.sh` benchmark.

## What follows after the immediate action

1. Run the clean seeded R8-R12 benchmark and append (never overwrite) `eval/results.csv`.
2. Complete `docs/templates/r8-r12-evaluation-review.md` with aliases, conflicts,
   coreference, document-type, candidate recall/precision/latency/traversal, and RBAC results.
3. Compare against `eval-baseline-v2`; update findings and roadmap only with recorded evidence.
4. Obtain review to accept/reject R8-R12, then decide R13 and P0 authorization.

## Guardrails

- Do not weaken quote verification, human approval, provenance, RBAC, or audit behavior.
- Do not alter `ingest.py`, `extract.py`, `retrieve.py`, `store.py`, or the Postgres schema
  without measured evidence and a reviewed exception.
- `scripts/eval.sh` destroys local Docker volumes; never run it against data that must be kept.
- Do not call a static design artifact a web product or treat it as P0 authorization.
- Treat uncommitted changes as user-owned until inspected.
