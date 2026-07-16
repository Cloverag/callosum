# R8-R13 handover

Timestamp: 2026-07-16 08:24:44 IST
Repository: Callosum
Branch: master
Last pushed commit: `8702d3c feat: add scoped grounding candidates and research handoff`

## Short status

R8-R11 are implemented and deterministically verified. They are **not formally accepted**:
the roadmap requires a clean live Ollama evaluation and reviewed metrics before acceptance.

R12 is implemented in commit `8702d3c` and has deterministic coverage, but its live
candidate-recall, grounding-precision, latency, and traversal-impact measurements are still
missing. R13 has a prepared handoff package, but cannot be formally approved until the
live R8-R12 evidence is reviewed. P0 is therefore not authorized.

## What was done

### R8 - aliases and resolution benchmark

- Added Meeting 14 with real aliases for Rajesh Malhotra and a negative same-name control.
- Added source-backed, reviewable `ALIAS_OF` links; no automatic merge is performed.
- Added gold cases and deterministic checks for alias provenance and false merges.

### R9 - conflicting evidence benchmark

- Added independent Finance and Sales FY27 forecasts ($12.0M and $11.6M).
- Both claims remain separately sourced and permission-filtered; no synthetic winner is
  written into the graph.
- Added gold cases that require both claims and reject an unsupported approved target.

### R10 - coreference limits

- Added Meeting 16 with one explicit reference and one deliberately ambiguous reference.
- The ambiguous case is a no-link / abstention gold case; no automatic coreference writer
  was added.

### R11 - messy-document benchmark

- Added TXT, Markdown, VTT, DOCX, PDF, and restricted Markdown fixtures.
- Deterministic loader checks pass. DOCX visual rendering is still locally unverified
  because LibreOffice/soffice is unavailable.

### R12 - candidate grounding and abstention

- Replaced full graph-vocabulary prompting with candidates reached through the caller's
  clearance-filtered vector hits.
- Neo4j repeats the chunk clearance predicate before candidate names enter the planner.
- The planner now has an explicit empty-list abstention policy; model-emitted names outside
  the candidate list are discarded before graph traversal.
- Added deterministic tests for the output guard, abstention, and clearance predicate.

### R13 - research handoff

- Added `docs/research-handoff.md` with the named baseline, reproducibility commands,
  readiness/limitations matrix, frozen-core exception process, and P0 decision gate.
- Updated `ROADMAP.md` and `docs/findings.md` to distinguish implemented work from accepted
  research findings.

## Verification already performed

- `python -m compileall -q src tests` completed successfully.
- `.venv\Scripts\pytest.exe -q` passed: `30 passed, 5 deselected`.
- `git diff --check` passed before commit.
- Commit `8702d3c` was pushed to `origin/master`.

## What is left and why

The required live provider is unavailable locally. `.venv\Scripts\callosum.exe doctor`
fails because Ollama is not running at `http://localhost:11434`. Without Ollama and the
`bge-m3` embedding model, ingestion cannot create embeddings and the benchmark cannot
produce valid R8-R12 measurements. Do not invent CSV rows, acceptance marks, or a baseline
tag to bypass this gate.

Remaining evidence:

1. Reproduce the clean seeded evaluation after restoring Ollama.
2. Measure aliases (precision/recall/GER/false positives), conflicts, coreference,
   document-type failures, R12 candidate recall/precision/latency/traversal, and RBAC.
3. Compare results to `eval-baseline-v2`; append, never overwrite, `eval/results.csv`.
4. Review the results and formally accept or reject R8-R12.
5. Approve R13 only after the evidence review; then explicitly authorize P0.

## Recommended next action

Start Ollama, make sure `bge-m3` is installed, then run the destructive clean benchmark:

```powershell
ollama serve
# In another terminal:
ollama pull bge-m3
.venv\Scripts\callosum.exe doctor
bash scripts/eval.sh
.venv\Scripts\pytest.exe -q
git show eval-baseline-v2
```

`bash scripts/eval.sh` deletes local Docker volumes. Do not run it against data that must
be retained.

## Other useful work while the provider is unavailable

- Prepare a review template for the R8-R12 result comparison (metric, baseline, new value,
  corpus, model, decision, reviewer).
- Review and tighten gold-question/source traceability; this is safe dataset work and does
  not alter the frozen core.
- Create UX/design artifacts for Meridian's approval queue and grounded-answer experience,
  but do not begin P0 implementation or claim the product track is authorized.
- Restore DOCX visual QA by installing/using a local LibreOffice renderer, then document
  the outcome.

## Guardrails for the next person

- Do not weaken evidence verification, human approval, provenance, or RBAC.
- Do not change `ingest.py`, `extract.py`, `retrieve.py`, `store.py`, or the Postgres schema
  without measured evidence and a reviewed exception.
- Treat any uncommitted changes as belonging to the current user until inspected.
- Refer to `AGENTS.md`, `ROADMAP.md`, and `docs/research-handoff.md` before continuing.

## Ordered continuation prompts

Use these tasks in order. Do not begin P0 unless the R13 handoff is explicitly approved.

### Task 1 - Restore the evaluation environment

```text
Work in C:\Users\devgu\OneDrive\Desktop\callosum.

Restore the live evaluation environment without changing application code. Start Ollama,
ensure bge-m3 is available, run `callosum doctor`, and report the exact provider/model
status. Check Docker Postgres and Neo4j health. Do not run destructive scripts yet. Record
commands and results in a new timestamped handover note.
```

### Task 2 - Reproduce the clean benchmark

```text
In the Callosum repository, run the documented clean evaluation baseline for R8-R12. First
confirm local data may be deleted because `scripts/eval.sh` resets Docker volumes. Run the
script, then run pytest. Append results only; never overwrite eval/results.csv. Report
commit SHA, provider/model, corpus, pass/fail by stratum, grounding metrics, latency, and
any errors. Do not modify frozen core code.
```

### Task 3 - Analyze R8-R11

```text
Analyze the newest evaluation rows against the eval-baseline-v2 tag. Assess R8 aliases, R9
conflicting evidence, R10 coreference, and R11 document-type/messy-input behavior. State
each exit criterion as pass, fail, or inconclusive, with exact evidence. Update
`docs/findings.md` and `ROADMAP.md` only when supported by the recorded run. Do not claim
formal acceptance without explicit review.
```

### Task 4 - Analyze R12

```text
Evaluate R12 grounding candidates and abstention against eval-baseline-v2. Report candidate
recall, grounding accuracy, GER, false positives/precision, latency, traversal impact, and
RBAC outcomes. Confirm low-clearance users cannot receive private entity names through
candidate selection. Add or improve deterministic tests only if a concrete gap is found. Do
not weaken retrieval RBAC or provenance.
```

### Task 5 - Complete the R13 approval package

```text
Review `docs/research-handoff.md`, `ROADMAP.md`, `AGENTS.md`, `PRD.md`,
`CONTRIBUTING.md`, `docs/findings.md`, and `eval/results.csv` after the live R8-R12 run.
Reconcile any contradictions. Produce a concise R13 decision record stating whether the
research handoff is approved, which baseline/tag is authoritative, remaining risks, and
whether P0 is formally authorized. Do not authorize P0 if any required measurement or
review is missing.
```

### Task 6 - Begin P0 only after authorization

```text
Begin Meridian P0 only if ROADMAP.md explicitly records approved R13 handoff and P0
authorization. Create the product contract and delivery controls required by P0: decision
record format, ownership, security/review gates, acceptance criteria, and delivery sequence.
Keep product code isolated from the frozen Callosum core. Commit documentation and tests
separately from any product implementation.
```
