# Entity conflict review — handover

**Timestamp:** 2026-07-17 22:02 IST  
**Repository:** Callosum  
**Branch:** `master` (uncommitted)  
**Topic:** Human-in-the-loop entity name conflict review feature

---

## Status

Implementation complete and deterministically tested. **Not yet committed.**  
Docker was not running during development so the live integration path (actual Postgres insert
of entity_conflict rows, full approve-conflict → Neo4j write) has not been exercised end-to-end.
That must be done before committing.

---

## What was built

### New files (3)
| File | Purpose |
|---|---|
| `src/callosum/conflicts.py` | Detection module: similarity scan, queue, approve, reject |
| `tests/test_conflicts.py` | 18 deterministic unit tests — all pass |
| `scripts/migrate_entity_conflict.sql` | Migration for existing DB environments (no volume wipe needed) |

### Modified files (4)
| File | Change |
|---|---|
| `pyproject.toml` | Added `rapidfuzz>=3.9` dependency |
| `schema/postgres.sql` | Added `entity_conflict` table (additive, at end of file) |
| `src/callosum/store.py` | Added `pending_entity_conflicts()` and `conflict_stats()` queries (additive) |
| `src/callosum/cli.py` | Added `detect-conflicts`, `review-conflicts`, `approve-conflict`, `reject-conflict` commands; conflict scan hook in `ingest-doc` |

### Frozen core boundary — respected
- `ingest.py`, `extract.py`, `retrieve.py`: **untouched**
- `store.py`: only **additive** query functions added; no existing function modified
- `schema/postgres.sql`: only **additive** table added; no existing table modified

---

## Verification evidence

```
.venv\Scripts\pytest.exe -q
54 passed, 1 skipped, 5 deselected in 0.81s

git diff --check   → clean (no whitespace errors)
git diff --stat    → 4 files changed, 278 insertions(+), 1 deletion(-)
```

New conflicts tests: 18/18 pass. The 3 that initially failed revealed the correct
threshold calibration: `DEFAULT_THRESHOLD = 75.0` (not 80) — at 80, the real alias
pair `Rajesh Malhotra`/`R. Malhotra` (score ~77) would be missed.

---

## Key design decisions

1. **Threshold 75 not 80** — measured from rapidfuzz token-sort scores on the actual
   corpus names. "R. Malhotra" vs "Rajesh Malhotra" = 77. "Raj Malhotra" vs "Raj Patel" = 57.
   
2. **Approval routes through `proposed_change` → `store.approve()`** — no new graph write
   path was introduced. The ALIAS_OF edge has full provenance (chunk_id, ontology_version).

3. **Sensitivity = max of the two source chunks** — a low-clearance reviewer cannot see
   a conflict involving a confidential entity.

4. **Graceful degradation** — if `entity_conflict` table doesn't exist (pre-migration env),
   `ingest-doc` prints a hint and continues rather than crashing.

---

## Immediate next action

1. **Start Docker Desktop** if not running, then:
```powershell
docker compose up -d
.venv\Scripts\callosum.exe doctor   # should pass all three: Ollama ✓ Postgres ✓ Neo4j ✓
```

2. **Apply the migration** (if using existing volumes):
```powershell
docker exec -i callosum-postgres-1 psql -U callosum -d callosum < scripts/migrate_entity_conflict.sql
```
  OR use fresh volumes (recommended for eval):
```powershell
docker compose down -v
docker compose up -d
.venv\Scripts\callosum.exe init
```

3. **End-to-end smoke test**:
```powershell
callosum ingest-doc data/demo/board_meeting_14_transcript.txt --type transcript --sensitivity 1
# Expected: "⚠ N potential entity name alias(es) flagged. Run: callosum review-conflicts"

callosum review-conflicts
# Expected: table showing Raj Malhotra / R. Malhotra with source quotes

# Approve or reject as appropriate:
callosum approve-conflict <short-id>    # writes ALIAS_OF to Neo4j
callosum reject-conflict <short-id>     # marks as distinct
```

4. **Commit** after the smoke test passes:
```powershell
git add pyproject.toml schema/postgres.sql scripts/migrate_entity_conflict.sql \
        src/callosum/conflicts.py src/callosum/store.py src/callosum/cli.py \
        tests/test_conflicts.py
git commit -m "feat: human-in-the-loop entity conflict review (ALIAS_OF workflow)

Adds detect-conflicts, review-conflicts, approve-conflict, reject-conflict CLI
commands. Detection uses rapidfuzz token-sort at threshold=75. Approval routes
through proposed_change → store.approve() — no new graph write path.
Adds entity_conflict Postgres table and migrate script for existing envs.
54 passed, 1 skipped in fast suite.

Calibrated threshold: Rajesh/R. Malhotra ~77, Raj Malhotra/Raj Patel ~57."
```

---

## Guardrails

- Do NOT lower threshold below 70 without measuring false positive rate on the demo corpus.
- The `approve_conflict()` function requires entity nodes to already exist in Neo4j. If
  called before the ingest proposals are approved, the `MATCH (a:Entity)` in apply_relationship
  will silently no-op. Approve entity proposals first.
- `scripts/migrate_entity_conflict.sql` is idempotent (`IF NOT EXISTS`) — safe to run twice.
- `scripts/eval.sh` destroys local Docker volumes; always run it with fresh volumes.
