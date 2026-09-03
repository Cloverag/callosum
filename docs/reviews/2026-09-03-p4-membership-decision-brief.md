# P4 criterion 1 — decision brief for #166

**Written for the maintainer, 2026-09-03.** Everything below marked ✅ was verified
against `HEAD` (`454f77b`) by reading the code, not by trusting the issue text. Two
claims in the tracker did not survive that check and are flagged in §8.

~~You are asked for **four decisions** (§6).~~ **ANSWERED 2026-09-03 — see §11.**
Everything else here is the context those answers were given against.

---

## 1. What is actually blocked

`ROADMAP.md:441`, verbatim:

> **Exit:** membership is authorized/audited; document lifecycle is visible;
> restricted titles, text, quotes, graph facts, and hints cannot leak.

**P4 sits at 3/13 accepted.** Criterion 1 fails on the word *audited*.

| half | state |
|---|---|
| `board_member` mutations audited | **done** — merged in #169, 4/4 routes now audit |
| `membership` mutations audited | **not started** — there is no product path to audit |

The second half is not "add audit calls to existing routes". **No route exists.**
`membership` is the access-control row, and the only writer of it anywhere in the
product is a CLI helper. So the work is: design a route that grants/changes/revokes
workspace access, then audit it. Creating that route expands security surface, which
is why it is a design call rather than a follow-on.

---

## 2. The data model as it actually is today

This is the part that decides everything else. It is not what the earlier discussion
assumed.

### The authorization lookup that runs on every authenticated request

`src/callosum/identity.py:65-74` ✅ — this exact SQL:

```sql
SELECT p.id, p.name, p.role, m.clearance
  FROM principal p
  JOIN membership m ON m.principal_id = p.id
 WHERE {match}
   AND m.workspace_id = %s
   AND m.active
 LIMIT 1
```

Read it carefully:

- **`role` comes from `principal`** — it is global, one value per person, the same in
  every workspace.
- **`clearance` comes from `membership`** — it is per-workspace.
- **`membership.role` is not selected.**

### `membership.role` is written and never read ✅

`meridian/migrations/versions/0001_workspace_and_membership.py:46` declares it
`TEXT NOT NULL`. `src/callosum/cli.py:125` writes it. **Nothing anywhere reads it** —
a repo-wide grep for `m.role` / `membership.role` returns zero hits outside that
INSERT. It is a dead column today.

### The design intent recorded in `0001`, verbatim ✅

> `membership` — which principal belongs to which workspace, and at what clearance
> (**clearance is per-workspace: a founder in their own workspace may be
> only an observer in another**)

`0012_board_member.py:11` reinforces it: *"Deliberately carries NO clearance column.
Clearance belongs to `membership`."* And `api/packs.py:8` depends on it: clearance is
*"resolved from the caller's active membership on every request"*.

### What already holds, and needs no work

`meridian/api/deps.py:143` `current_principal` rebuilds the caller's clearance from
the database on **every request**, from session identity only. Fail-closed: a revoked
or deactivated membership stops resolving immediately, no cache to invalidate. The
403 is deliberately uniform so it cannot be used to probe which workspaces exist.

**The "authorized" half of criterion 1 already holds and is well covered.** Nothing
in this brief proposes changing it.

---

## 3. The decision already made, and what it left open

Option **(c)** was chosen for §4: the request carries `role` only, and a server-side
table maps role → clearance. `clearance` never enters the OpenAPI schema.

The load-bearing reason it was chosen — still valid — is that option (b) would have
required overriding a written instruction in
`test_no_endpoint_accepts_workspace_id_or_clearance`:

> *"do not add an exemption — take the value from the session instead… growing it is
> how the rule stops meaning anything."*

One reason originally offered for (c) **was withdrawn**: the observed 1:1 correlation
between role and clearance in live rows is an artefact. `src/callosum/cli.py:123`
writes both columns from the same `principal` row in one `INSERT ... SELECT`, so a
perfect correlation was the only possible outcome. That measurement could not have
come out any other way and proves nothing.

**Consequence: there is no evidence in this database, either way, about whether role
and clearance vary independently.** Choosing (c) accepts that they do not, on
judgement about how boards work rather than on anything observed here.

---

## 4. The central conflict — this is the real question

Your ruling stated: **`principal.role` is authoritative; membership supplies
tenant-specific clearance.**

Under (c), clearance is *derived from role*. If role is global, then clearance derived
from it is also global — **the same in every workspace**.

That removes exactly the property `membership` was created to hold. The founder who
is "only an observer in another workspace" becomes unrepresentable, because their one
global role maps to one clearance everywhere.

So (c) and "role is global" cannot both be true without dropping per-workspace
clearance. The fork:

### Option (i) — role is global, clearance becomes derived

- `principal.role` is authoritative, exactly as your ruling says.
- The mapping produces clearance; `membership.clearance` becomes denormalised cache
  or is dropped.
- **Cost:** per-workspace clearance ends as a capability. `0001`'s stated intent is
  reversed, and that reversal should be written down as a deliberate change rather
  than left as drift.
- **Benefit:** simplest possible model. One role per person, one mapping, done.
- Affects: `identity.py`'s JOIN, `0012`'s rationale, `packs.py`'s comment.

### Option (ii) — role moves to the membership row

- `membership.role` becomes authoritative and is finally *read*; the mapping runs per
  membership, so clearance stays per-workspace.
- `principal.role` becomes display/global-default only.
- **Cost:** two role columns exist during migration and one must be explicitly
  demoted; `identity.py:66` changes `p.role` → `m.role`, which is a frozen-core edit
  under the tenancy exception.
- **Benefit:** `0001`, `0012` and `packs.py` all keep meaning what they say. The dead
  column becomes the load-bearing one.

**My recommendation: (ii).** Per-workspace clearance is a tenancy property, and this
codebase's one consistent rule is that tenancy is not compromised for convenience.
(ii) is also what makes `membership` a real aggregate worth auditing — under (i) the
interesting mutation is on `principal`, and the criterion says *membership*.

**This is yours to decide. I have not written code either way.**

---

## 5. The vocabulary problem

Your example used `viewer / member / advisor / editor / admin` and clearances
`READ / READ_WRITE / REVIEW / WRITE / ADMIN`. **Neither matches this system.** ✅

### Clearance is an ordered integer ladder, not names

`schema/postgres.sql:15-24` — the ordering is load-bearing (`a principal may read any
object whose sensitivity is at or below their clearance`):

```
0  public         press releases, public metrics
1  investor       board packs, cap table, KPIs shared with the board
2  internal       team-wide docs, product decisions
3  confidential   salary, legal, M&A, termination discussions
4  restricted     founder-only
```

### The role vocabulary is a comment, not a constraint

`0001:46`, the entire definition:

```sql
role TEXT NOT NULL,   -- founder | admin | exec | director | observer | advisor
```

- **There is no CHECK, no enum, no lookup table.** ✅ Under (c) this column is the
  security boundary and its key is currently unconstrained free text.
- **`investor` is used but not listed.** ✅ `cli.py:86` seeds
  `("Marcus Webb", "marcus@sequoia.com", "investor", 1, "Sequoia")`. Either the
  comment is wrong or `investor` is an undocumented seventh role. Note `investor` is
  also a *clearance label* (level 1) — the two vocabularies may have been conflated.
- `director` is real and used in `tests/test_p4_leak_sweep.py:169`.

### The table you need to rule on

Seven candidate roles. Values below are **a proposal, not a measurement** — under (c)
this table *is* the security boundary, so it needs your explicit ruling rather than
inheritance from an example:

| role | proposed clearance | reasoning |
|---|---|---|
| `founder` | 4 restricted | matches seeded `Raj Malhotra` |
| `admin` | ? | **the role §1's authorisation rule depends on** — see §6 Q3 |
| `exec` | 3 confidential | matches seeded `Priya Nair` |
| `director` | 3 confidential | board member, sees legal/M&A |
| `advisor` | 2 internal | proposed; no live row exists |
| `investor` | 1 investor | matches seeded `Marcus Webb` |
| `observer` | 0 public | proposed; no live row exists |

Only `founder`, `exec` and `investor` have any live row to check against, and those
three agree by construction (§3), so **four of seven values rest on judgement alone.**

---

## 6. The four decisions

**Q1 — the fork.** Option (i) global role with derived clearance, or (ii) role moves
to `membership` and clearance stays per-workspace? (§4. I recommend (ii).)

**Q2 — the mapping table.** Confirm or amend the seven values in §5. Specifically
including `advisor` and `observer`, which have no live row.

**Q3 — `admin`.** What clearance does it get, and is `admin` an *authorisation* role
(may grant membership) or a *clearance* role (may read restricted material), or both?
These are different questions and the current model has one column for both. This is
the role the new route's own authorisation check depends on.

**Q4 — `investor`.** Undocumented seventh role, or a comment that should be corrected?
If it stays, `0001`'s comment needs amending in the same migration that adds the CHECK.

---

## 7. Two things that must land regardless of Q1–Q4

These are prerequisites, not decisions:

1. **`membership` is not in `AGGREGATE_TYPES`.** ✅ `meridian/audit.py:43` holds
   exactly 10 values — `meeting, agenda_item, document, decision, board_pack, minutes,
   board_member, resolution, commitment, audit`. `record_audit_event` raises
   `AuditValidationError` on anything else (`audit.py:128`). **A migration widening
   that CHECK is the first commit of this work**, whichever way Q1 goes.

2. **`membership.role` has no CHECK.** ✅ Under (c) the mapping's key must be
   constrained *before* the route exists, not after — an unconstrained key to a
   security lookup is the failure mode (c) was chosen to avoid.

Also reported (measured by another session at head, **not re-verified by me**):
`membership` has no `version` and no `updated_at` column, which an audited mutable
row generally wants.

---

## 8. Corrections — two tracker claims that are false ✅

**A mitigation is cited that has never existed.** #176's body states
*"`scripts/eval.sh` now pins the chain at `alembic upgrade 0021_fix_composite_fk_cascades`"*,
and #166's second-reader comment cites it as `scripts/eval.sh:73`.

- `scripts/eval.sh` is **59 lines long** — there is no line 73.
- It contains no `alembic` line at all.
- `git log --all -S'alembic' -- scripts/eval.sh` returns **nothing**: the word has
  never appeared in that file, on any branch, in any commit.

Consequence: #176 reads as "we have a workaround, here is the decision to make". There
is no workaround. The eval path is broken and in a different place than described —
`callosum init` seeds `membership`, which `schema/postgres.sql` does not create at
all, so a run fails before ever reaching the `ON CONFLICT` bug.

**#159 is half-fixed and does not say so.** Its second symptom — master's parenthetical
naming a moving ref — is gone. `README.md:149` now reads
``| Commits | 495 (`git rev-list --count 8dd2d3d`) |``. Verified: 495 commits at that
SHA, 25 migrations at that SHA, both exact. What remains is only the missing guard —
`grep -rln README tests/` still returns nothing.

---

## 9. The other open issues, in one line each

| # | state | blocked on you? |
|---|---|---|
| **#166** | P4 criterion 1. Board-member half done, membership half unstarted. | **yes — Q1–Q4** |
| **#176** | `store.upsert_document`'s `ON CONFLICT (content_hash)` broken by `0022`. Real. Underneath it: **two schema sources** (`schema/postgres.sql` and `meridian/migrations/`) with nothing asserting they agree. `0022` is the first drift to surface, not the last. | yes — is the frozen-core edit inside the tenancy exception, and is `ingest-doc` still supported? |
| **#168** | 28 unaudited mutating routes, correctly split out of P4 so it is scheduled work. `deleted`, `recorded`, `reordered` are declared actions that no code path has ever emitted. | no |
| **#159** | README guard never built. Half the issue is already fixed (§8). | no |
| **#150** | Retrospective review of six self-merged PRs. **Says "no further merges until this review happens"** — that constraint is still on the record. | yes, if you want it lifted |
| **#178** | Recorded git trap (`rebase` reports "up to date" while keeping commits). No work attached. | no |

---

## 10. On wording — accepted, with one distinction the design needs

You objected to describing role as *"the sole client-supplied input to a security
decision"*, on the grounds that it implies the client is trusted to supply role. Taken;
your wording is better and I will use it.

The distinction that still has to be explicit in the design, because the implementer
will otherwise conflate them:

- **The caller's own role and clearance** — from the session, never the request.
  Already enforced (`deps.py:143`, `identity.py:65`). Your invariant covers this.
- **The grantee's role on a membership-grant route** — necessarily arrives *in the
  request body*. An admin granting someone else access must name the role being
  granted. That value is untrusted input to be validated against the vocabulary and
  mapped server-side. It is not a claim about the caller.

Your test matrix maps onto the first. The second is where the new route's risk lives:
the check is not "is the supplied role the caller's role" but "is the caller
authorised to grant *this* role to *this* principal in *this* workspace".


---

## 11. Decisions — answered 2026-09-03

Posted to #166 as
[issue comment 5519539953](https://github.com/Cloverag/callosum/issues/166#issuecomment-5519539953),
transcribed verbatim and flagged as a session transcribing rather than independently
verifiable.

| | decision |
|---|---|
| **Q1** | **Option (ii).** `membership.role` becomes authoritative and workspace-scoped; `principal.role` demoted to legacy/display with an explicitly documented purpose. |
| **Q2** | Mapping approved as proposed, with `admin` → **4 restricted**. |
| **Q3** | `admin` carries clearance 4 **and** membership-management authority, as two separate grants. |
| **Q4** | `investor` is a real role. `0001:46`'s comment is wrong and is amended in the migration that adds the CHECK. |

**An earlier ruling was revised.** The 2026-08-25 decision that `principal.role` stays
authoritative is superseded — it cannot coexist with option (c) without making `0001`'s
per-workspace clearance unimplementable (§4).

### Two things the ruling raises and does not settle

1. **May a caller grant a role whose clearance exceeds their own?** This determines
   whether Q2's `admin` row enforces anything. If an `admin` may grant `founder`, an
   admin can escalate to clearance 4 regardless of the table, and the table becomes
   descriptive. `authorize(caller_role, operation, requested_role)` is the right shape;
   the policy inside it is unspecified and is not implementable without an answer.

2. **Q3 separates two permissions and then couples them.** The ruling states that
   "can read restricted things" and "can grant anyone anything" are separate — and then
   sets `admin` to clearance 4 on the grounds that the role managing membership should
   be able to inspect the highest-sensitivity material. Managing access does not require
   reading content; under least privilege an operator role can administer membership at
   clearance 2. Flagged once, not blocking: under (ii) the grant is workspace-scoped, so
   the blast radius is one workspace rather than the product, and question 1 above
   matters more than this value does.

### Verified while transcribing

- `tests/test_openapi_input_guard.py:46` bans `{"workspaceid", "workspace", "clearance"}`.
  **`role` is not banned**, so the grant route needs no exemption and
  `test_no_endpoint_accepts_workspace_id_or_clearance` stays unamended — the load-bearing
  reason (c) was preferred over (b). ✅
- `aggregate_type`'s CHECK lives in `0016_audit_event.py:70`, generated from a duplicated
  tuple, and `0016:31` records that `tests/test_audit.py` asserts it agrees with
  `meridian/audit.py`. Adding `membership` therefore touches two places and cannot drift
  silently. ✅
- `membership.role` already exists (`0001:46`, `NOT NULL`) and is already populated
  (`cli.py:125`). The backfill is a no-op; only the lookup changes. ✅

---

## 12. Escalation policy — answered 2026-09-03

Posted as [issue comment 5519623435](https://github.com/Cloverag/callosum/issues/166#issuecomment-5519623435).

```
mapped_clearance(requested_role) <= caller_clearance
```

No break-glass override at this stage. `admin = 4` stands, but that clearance value is
**not** the justification for membership-management authority — the two are separate
grants on the same role. Target workspace comes from session context, never the client.

### Three consequences, recorded

1. **No route can create the first membership in a new workspace.** Caller authority
   requires an active membership in the target workspace and `identity.py:130` fails
   closed, so a memberless workspace has no possible caller. `cli.py:125` is now the
   load-bearing bootstrap path and the route's docstring must say so — otherwise the
   gap gets closed later by the override this ruling declined.
2. **`admin` may grant `founder`** (4 <= 4). Correct consequence of `admin = 4`, not an
   oversight. The rule caps escalation above the caller, not laterally at the ceiling.
3. **Open: does `caller_clearance` read stored `membership.clearance` or
   `mapped_clearance(membership.role)`?** Nothing forces them to agree; they match today
   only because `cli.py:123` writes both from one row — the artefact already withdrawn
   as evidence. **Recommend deriving and making the stored column non-authoritative or
   dropping it.** Needs a CHECK, a trigger, or a deletion — not a convention. Does not
   block step 1.
