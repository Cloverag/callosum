# Release process

How a Callosum product baseline is cut. Each release is an immutable tag with a matching
release-notes file in this directory. The cadence is fixed so that **every knowledge graph and
every published doc corresponds to a tagged release, not an arbitrary point in development.**

## A release is an immutable historical artifact

Every release is the *same self-contained bundle*, captured at the tag so it stays reproducible
years later. The annotated tag freezes the whole tree — so the ADR log, evaluation CSVs, and graph
output at that commit *are* the release's snapshots; the surrounding records complete the bundle:

```
Release (meridian-pN)
├── Tag              — annotated, immutable, never moves
├── Freeze note      — docs/reviews/<date>-meridian-pN-freeze.md
├── Release notes    — docs/releases/meridian-pN.md
├── ADR snapshot     — docs/ARCHITECTURE_DECISIONS.md @ tag
├── Evaluation nums  — eval/*.csv @ tag + acceptance metrics in the release notes
├── Graph snapshot   — graphify output rebuilt from the tag (step 4 below)
├── Acceptance record— docs/reviews/<date>-*-acceptance.md
└── Postmortem       — docs/releases/meridian-pN-postmortem.md (step 6 below)
```

## Cadence

```
merge → freeze → tag → graphify → publish → postmortem
```

1. **Merge** — land the PRs that make up the baseline; sync `master`; verify the diff scope is clean.
2. **Freeze** — write a freeze note under `docs/reviews/` (rules: fix only real reproduced bugs, no
   refactors, no churn) and stop advancing code on `master`.
3. **Tag** — create an annotated tag (`meridian-pN`) on the freeze commit. The tag is immutable and
   never moves; all future work builds *on* it. Verify single-tenant retrieval still reproduces the
   research baseline `eval-baseline-v3` (candidate recall 21/21, traversal 100%).
4. **Graphify** — rebuild the knowledge graph *from the tagged tree* so the graph maps exactly to the
   release. Run in Kitty (fish; claude-cli backend; text/code scope, not media). `--backend claude-cli`
   is **required** (without it graphify errors "no LLM API key"), and `GRAPHIFY_CLAUDE_CLI_MODEL=haiku`
   pins the cheap model — the default is **Opus**, which silently drains subscription credit:
   ```
   git checkout <tag>
   GRAPHIFY_CLAUDE_CLI_MODEL=haiku graphify . --backend claude-cli --obsidian --obsidian-dir "/home/clover/Documents/Obsidian Vault/Meridian"
   git checkout master
   ```
   Do a clean full rebuild at the tag, not mid-development — an arbitrary rebuild produces a graph that
   corresponds to nothing. If a chunk fails with `claude -p exited 1:` and empty stderr, the real error
   (usually a usage limit) is on stdout — Haiku both cuts cost and avoids the limit.
5. **Publish** — write the release notes (`docs/releases/meridian-pN.md`: commit, tag, research
   baseline, capabilities, acceptance metrics, known limitations, deferred RFCs, ADR + freeze links)
   and add the row to the index below. Release-notes and graph commits may land *after* the tag —
   they describe the tag, so the tagged code tree stays untouched.
6. **Postmortem** — write `docs/releases/meridian-pN-postmortem.md` **even if nothing failed.** Five
   questions: (1) What surprised us? (2) What was harder than expected? (3) What almost went wrong?
   (4) What should become a rule? (5) What should we never do again? Answers to (4) feed back into
   this checklist — this is where the process improves, release over release.

## Standing rules from postmortems

Step 6 says answers to "what should become a rule?" feed back into this checklist. Until now they
had nowhere to land, so they didn't — p1.0.4's rules stayed in p1.0.4's postmortem. This is that
place. Add to it when a postmortem produces a rule; keep each one short and link the release it
came from.

**Migrations and schema**

- Keep Alembic revision ids **≤ 32 chars** (`alembic_version.version_num` is `varchar(32)`). It fails
  loudly but late: the DDL runs, then the version-record update overflows and the whole migration
  rolls back. — *p1.0.4*
- **Never `DROP CONSTRAINT IF EXISTS <guessed-name>`.** Read the real name from `pg_constraint` first;
  `IF EXISTS` on a wrong name is a silent no-op that leaves the old constraint in force. — *p1.0.4*
- **Run the regression test immediately after applying a migration, on the same database.** It is the
  only thing that distinguishes "applied" from "rolled back but DDL echoed". — *p1.0.4*
- **Composite `(id, workspace_id)` foreign keys for new tenant-scoped relationships.** Postgres
  validates foreign keys as the table owner, which bypasses RLS, so a single-column reference to a
  tenant-scoped table is an unscoped reference. Also in `CONTRIBUTING.md`. — *p1.0.5*
- **Never pin a migration number in a spec, issue or plan — claim the slot at implementation time.**
  Every checkpoint from CP3 onward has had its planned number taken by something else: #21 pinned
  `0009_board_pack` and CP4 got there first; the CP5–CP9 proposal pinned `0011`–`0015` and all five
  were claimed. Alembic linearises on `down_revision`, so nothing corrupts — the cost is confusion
  and rework. Refer to checkpoints by name. Also in `CONTRIBUTING.md`. — *CP3/CP4, CP5–CP7*
- **When adding any constraint, ask which role evaluates it.** If the answer is the table owner, RLS
  is not involved and tenancy must be enforced in the constraint itself. — *p1.0.5*

**Verification**

- **Probe the data, don't just read the schema.** A table can be correctly declared, typed and
  referenced, and empty. `SELECT count(*)` before relying on one in a policy. — *p1.0.5*
- **Assert isolation through the connection that bypasses the policy.** A rejection observed through
  the superuser connection proves the constraint is doing the work, not the policy. — *p1.0.5*
- **Seed security fixtures in deliberate disagreement.** When a fix moves where a value is read from,
  give the old and new sources *different* values — identical seeds pass against the bug. — *p1.0.5*
- **Never trust a migration that printed its DDL as proof it applied.** Verify the resulting schema,
  not the log line. — *p1.0.4*

**Release hygiene**

- **Never ship half of a two-part isolation fix as complete**, even when the half is green and closes
  its issue. Release notes are read as guarantees. — *p1.0.5*
- **Resolve a tag before citing it** (`git rev-list -n 1 <tag>`). Index rows and freeze notes should
  carry a verified commit, not whatever was HEAD when the row was drafted. — *p1.0.5*
- **Use `-F -` with a heredoc for commit messages containing backticks.** `-m` is shell-interpreted
  and command substitution will quietly delete text. — *p1.0.5*

## Releases

| Tag | Commit | Date | Notes | Postmortem |
|-----|--------|------|-------|-----------|
| `meridian-p1` | `04dfd2f` | 2026-07-19 | [meridian-p1.md](meridian-p1.md) — P1 multi-tenancy (Postgres RLS + Neo4j entity partitioning) + entity_conflict + Next.js frontend shell |
| `meridian-p1.0.1` | `43d64f3` | 2026-07-20 | [meridian-p1.0.1.md](meridian-p1.0.1.md) — patch: scope entity-conflict detection to workspace (F2); restores the P1 Cypher-isolation invariant |
| `meridian-p1.0.2` | `4c375b7` | 2026-07-20 | [meridian-p1.0.2.md](meridian-p1.0.2.md) — hardening: Neo4j query gateway (P2-RFC-001) closes Defect Class D-001; CI ban-test enforces no raw session outside gateway/allowlist | [postmortem](meridian-p1-postmortem.md) |
| `meridian-p1.0.3` | `ebf2849` | 2026-07-20 | [meridian-p1.0.3.md](meridian-p1.0.3.md) — infra: deterministic mechanism eval gate (`callosum eval-mechanism`) splits reproducible mechanism metrics from LLM-noisy answer metrics; candidate 22/22, traversal 21/21 (100%), RBAC 1/1, no cloud LLM | [postmortem](meridian-p1.0.3-postmortem.md) |
| `meridian-p1.0.4` | `6b0d3a0` | 2026-07-20 | [meridian-p1.0.4.md](meridian-p1.0.4.md) — schema: migration 0006 scopes the `entity_conflict` unique key to workspace `(workspace_id, name_a, type_a, name_b, type_b)`, closing a latent cross-tenant collision; integration 10/10, no code change | [postmortem](meridian-p1.0.4-postmortem.md) |
| `meridian-p1.0.5` | `64f643b` | 2026-07-28 | [meridian-p1.0.5.md](meridian-p1.0.5.md) — tenancy: **0011** RLS on the control plane (`membership`, `workspace`) + runtime write grants revoked; **0012** composite FK `(id, workspace_id)` makes cross-workspace references impossible by construction (FK checks bypass RLS); **0013** clearance resolves through `membership`, `principal` scoped and writes revoked. Clean-volume verify: 13 migrations, 176 passed, mechanism gate 22/22 · 21/21 · RBAC 1/1 byte-identical | [postmortem](meridian-p1.0.5-postmortem.md) |
