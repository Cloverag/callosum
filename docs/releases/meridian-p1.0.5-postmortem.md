# Postmortem — Meridian P1.0.5

**Release:** `meridian-p1.0.5` (`64f643b`) · **Date:** 2026-07-28 · **Outcome:** shipped clean; two
isolation defects found and fixed before the tag, neither of which was visible in the code.

Three migrations that only make sense together: `0011_control_plane_rls`, `0012_board_member`
(CP5a), `0013_principal_rls` (CP5b). The release exists in that shape because of what §1 describes.

## 1. What surprised us?

- **`membership` was empty, and nothing had ever written to it.** `0011` set out to put RLS on the
  control plane. The correct policy for `principal` is membership-derived — you can see a person if
  you share a workspace with them — so the policy was written against a table that turned out to
  contain no rows in any environment. The policy was correct and would have denied everything.

  Nothing in the code said so. `membership` was declared in the frozen schema, referenced in
  migrations, and typed correctly throughout. It was empty because `callosum init` never populated
  it, and no test asserted otherwise. **It was found by querying the table, not by reading the code
  that uses it.**

- **The reason `init` could write `principal` at all was that `principal` had no RLS.** `init` was
  running as `callosum_app`, and succeeded only because that table was unprotected with full write
  grants. The bootstrap path had been silently depending on the exact gap the release was closing.
  Fixing one broke the other, which is how the two became one release.

- **Postgres validates foreign keys as the table owner, which bypasses RLS.** A single-column
  `REFERENCES board_member(id)` validates happily against a row the caller cannot see. Reproduced
  directly: a `decision_stance` in workspace A successfully referenced a director in workspace B.

  This is documented Postgres behaviour, not a bug, and it is easy to read past. A referential
  constraint looks like the most trustworthy thing in a schema. It operates *below* the isolation
  boundary.

## 2. What was harder than expected?

- **Proving the clearance reroute changed nothing.** `0013` moved clearance from
  `principal.clearance` to `membership.clearance`, and clearance is the input to the frozen RBAC gate
  in `retrieve.py`. The code change is small; the burden was showing it was a change of plumbing and
  not of behaviour. The evidence that carried it: the 30 rows appended to `eval/mechanism.csv` were
  **byte-identical** to the previous deterministic run. An unchanged deterministic tier is what
  separates "we moved where this is read from" from "we changed who can see what".

- **Writing a test that could actually fail.** `test_clearance_comes_from_membership_not_the_legacy_column`
  seeds the two values **in deliberate disagreement** — membership `1`, legacy column `4`. Seeding
  them identically, which is the natural thing to do, produces a test that passes while still reading
  the old column. That is precisely the bug being fixed. The test only has value because the fixture
  is contradictory.

- **Choosing `RESTRICT` took longer than writing the constraint.** `SET NULL` was the reflex, and it
  cannot work: `decision_stance.workspace_id` is `NOT NULL`, so a composite `SET NULL` would try to
  null it and fail at runtime. `RESTRICT` also happens to match the deactivate-never-delete rule the
  directory already follows, but it was forced by the column definition first.

## 3. What almost went wrong?

- **Shipping `0011` alone as a finished fix.** It was ready, it passed, and it closed the issue it was
  written for. It would have published a documented half-measure as complete: `principal` could not be
  scoped until `membership` was populated. `0013` is what makes `0011` true. Releasing them separately
  would have left a release note claiming an isolation guarantee the schema did not provide.

- **Accepting the other nine foreign keys as safe for the wrong reason.** Every other domain module
  does an RLS-scoped existence check before insert (`add_pack_item` selects the document through
  `store.pg` first, so a cross-workspace id looks like a missing row). That is a real defence — but it
  is a defence **by convention**, holding only as long as every future author remembers it. It was
  briefly tempting to record the other relationships as fine. They are protected by discipline, not by
  construction, and that distinction is now written down as **#41** rather than assumed.

- **A commit message ate a word.** `git commit -m` with backticks in the body ran shell command
  substitution and silently removed the word `principal` from the message. Caught only by reading
  `git log -1 --format=%B` afterwards and amending.

- **The release index recorded the wrong commit.** The `meridian-p1.0.5` row pointed at `710669d`, the
  `chore(eval)` commit two before the tag; the tag is at `64f643b`. Found while writing this
  postmortem, by resolving the tag rather than trusting the table. Corrected in the same PR.

## 4. What should become a rule?

- **Probe the data, don't just read the schema.** Both findings in this release came from *querying* —
  counting rows in `membership`, and attempting a cross-workspace insert — not from reading the code
  that declares them. A table can be correctly declared, correctly typed, correctly referenced, and
  empty. Before relying on a table in a policy, `SELECT count(*)` from it in a real environment.

- **Constraints operating below the isolation boundary need explicit handling.** This is the second
  instance of the same defect class: p1.0.4's `entity_conflict` unique key and p1.0.5's foreign-key
  validation both enforced correctly while ignoring tenancy. **Composite `(id, workspace_id)` is now
  the standing rule for new tenant-scoped relationships** (recorded in `CONTRIBUTING.md`). When adding
  any constraint, ask which role evaluates it — if the answer is the table owner, RLS is not involved.

- **Assert isolation through the connection that bypasses the policy.** The cross-workspace regression
  test asserts a `ForeignKeyViolation` through the **superuser** connection on purpose. Superuser
  bypasses RLS, so a rejection there proves the *constraint* is doing the work rather than the policy.
  A test that only passes as `callosum_app` cannot distinguish the two.

- **Seed security fixtures in deliberate disagreement.** When a fix moves where a value is read from,
  set the old and new sources to *different* values. Identical seeds produce a test that passes
  against the bug.

- **Use `-F -` with a heredoc for commit messages containing backticks.** `-m` is shell-interpreted;
  command substitution will quietly delete text.

- **Resolve a tag before citing it.** `git rev-list -n 1 <tag>` — release-index rows and freeze notes
  should carry a verified commit, not the one that was HEAD when the row was drafted.

## 5. What should we never do again?

- **Never write a policy against a table without checking it has rows.** An empty table makes a
  membership-derived policy deny everything, and it fails in exactly the way that looks like correct
  strictness.

- **Never treat a foreign key as a tenancy boundary.** It is validated as the table owner and sees
  rows the caller cannot. A single-column reference to a tenant-scoped table is an unscoped reference.

- **Never ship half of a two-part isolation fix as complete**, even when the half is green and closes
  its issue. Release notes are read as guarantees.

---

*Three limitations ship with this release and are stated in the freeze note so they are not
rediscovered as surprises: `app.workspace_id` is an ordinary GUC (RLS guards application bugs, not a
compromised role); composite-FK protection covers 1 relationship of 10 (#41); `principal.clearance`
is retained as a deprecated bootstrap seed because it is declared in the frozen schema, demoted with
`COMMENT ON COLUMN` so `\d+ principal` tells the next reader — the difference between documented and
discoverable.*

*§4 rules feed `docs/releases/README.md`. Next work is product-forward (P2 CP6 onward), not more
hardening.*
