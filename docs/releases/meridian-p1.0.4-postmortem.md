# Postmortem — Meridian P1.0.4

**Release:** `meridian-p1.0.4` (`6b0d3a0`) · **Date:** 2026-07-20 · **Outcome:** shipped clean; one
migration defect caught by the regression test before merge.

## 1. What surprised us?

- **Alembic revision ids have a hard 32-char limit** (`alembic_version.version_num varchar(32)`),
  and it fails *loudly but late* — the `upgrade()` DDL runs, then the version-record UPDATE
  overflows and the whole migration rolls back transactionally. The first id
  (`0006_entity_conflict_workspace_uq`, 33) tripped it. Descriptive ids are fine, but budget the length.

## 2. What was harder than expected?

- **Nothing was hard; the value was in *proving* it.** The fix is one DDL statement. The work was
  evidence: fresh-volume migrate, reversibility, both regression directions, and confirming the
  mechanism gate + integration suite were undisturbed by a schema change.

## 3. What almost went wrong?

- **A silently half-applied constraint.** Had the regression test not run right after the migration,
  the 33-char overflow could have been mistaken for success (the DDL *did* execute before the record
  update failed). The test failing on the still-old constraint is what surfaced it in seconds.
- **Dropping the wrong constraint name.** The 0005 unique key was auto-named. Guessing it wrong with
  `DROP CONSTRAINT IF EXISTS` would have been a silent no-op, leaving the old key enforced and the
  fix ineffective. Reading the real name from the live schema first removed that risk.

## 4. What should become a rule?

- **Keep Alembic revision ids ≤ 32 chars.** Cheap constraint, expensive-to-debug failure.
- **Never `DROP CONSTRAINT IF EXISTS <guessed-name>`.** Read the actual constraint name from
  `pg_constraint` (or drop by column-set dynamically) before writing the migration. `IF EXISTS` on a
  wrong name is a silent no-op that leaves the old constraint in force.
- **Run the regression test immediately after applying a migration, on the same DB.** It is the only
  thing that distinguishes "applied" from "rolled back but DDL echoed."

## 5. What should we never do again?

- **Never trust a migration that printed its DDL as proof it applied.** Transactional DDL means the
  echo can appear and the change still roll back. Verify the *resulting schema*, not the log line.

---

*The p1 two-store tenant-isolation hardening line (p1.0.1 → p1.0.4) is complete. §4 rules feed
`docs/releases/README.md`. Next work is product-forward (ROADMAP P2), not more hardening.*
