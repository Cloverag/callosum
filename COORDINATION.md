# Two agents, one repository

**Status: active from 2026-09-11. Facts corrected 2026-10-09 by Devguru against `51f499d`** —
see "Corrections" at the end for exactly what changed and what was deliberately left alone.

Read this before touching anything. It says who owns what, which worktree you work in, and
the rules that stop two agents from destroying each other's work. `ROADMAP.md` and `phase.md` remain authoritative for gate status; `AGENTS.md`
remains authoritative for architecture and invariants. This file is only about *ownership
and collision avoidance*.

## Who is who

| Name | What it is | Reads on start-up | Carries session history |
|---|---|---|---|
| **Claude** | Claude Code CLI | `CLAUDE.md`, `AGENTS.md`, this file | Yes — long memory of this repo across ~15 sessions |
| **Codex** | OpenAI Codex CLI | `AGENTS.md`, this file | No — starts cold every time |
| **Raghav** (`Cloverag`) | The maintainer and owner. Decides; merges. | — | — |
| **Devguru** (`Devguru-codes`) | Human contributor. **Backend owner** per [`rules.md`](./rules.md) §5 — domain, migrations, RLS/tenancy, API contracts, tests, infra. Pushes under his own account. | `AGENTS.md`, `CLAUDE.md`, this file | Yes |

> **Unresolved, and for Raghav to settle (flagged 2026-10-09).** The Claude lane below claims
> ingest & tenancy, identity/RBAC, audit coverage and every measured README figure. `rules.md`
> §5 assigns all of that to **backend = Devguru**, and he has five open PRs in exactly that
> territory (#231, #215, #217, #218, #219). This file and §5 must agree before either is the
> document an agent reads on start-up — otherwise the collision this file prevents between two
> agents is reintroduced between an agent and a human. **No lane was changed here to resolve it.**

The two **agents** push with the **same `gh` credential (`Cloverag`)**; Devguru pushes under his
own. Consequences that are not negotiable:

- Every PR, comment, and review is attributed to `Cloverag`. **You cannot tell from GitHub
  which agent did what** — so every PR body must open with a line naming its author agent:
  `Agent: Claude` or `Agent: Codex`.
- GitHub refuses self-review on the shared account. **Neither agent can formally approve the
  other's PR.** Post review findings as a normal issue comment and let Raghav merge. A peer
  agent's approval is not a merge authorisation.
- Only Raghav merges to `master`. Neither agent merges its own work. **A human reviewer who is
  not the author may merge** — `rules.md` §4's rule is *"nobody merges their own PR on their own
  review"*, not that one person holds the button. (Devguru merged #222 on that basis,
  2026-10-09.)

## Worktrees — the physical separation

Three worktrees already exist. **One agent per worktree. Never open a worktree another agent
is working in.**

```
/home/clover/clode projects/callosum         → CLAUDE
/home/clover/clode projects/callosum-166     → CLAUDE
/home/clover/clode projects/callosum-mobile  → CODEX
```

The branch each one sat on when this was written (`eval/abstention-strata`,
`feat/audit-refusal-and-failure-166`, `master @ 658436e`) has since merged, so those
annotations were removed rather than guessed at — only the agent in a worktree knows what is
checked out in it. Run `git -C <path> branch --show-current` instead of trusting a table.

`callosum-mobile` is handed to Codex. Create new branches from there. If Codex needs a second
parallel branch, add a *new* worktree (`git worktree add ../callosum-codex-2 <branch>`) —
do not switch branches inside a worktree another task is mid-way through.

Before **every** commit, in any worktree: `git status --short`. If you see a file you did not
touch, stop and report it. It belongs to the other agent or to Raghav. This has already cost
this repo an uncommitted `.gitignore` edit once.

## The lanes

The split is not "frontend vs backend". It is **what the work depends on**: Codex gets work
that is fully specified by the files in front of it; Claude keeps work that depends on
measured history, security invariants, or decisions made in earlier sessions.

### Codex owns

Self-contained, verifiable from the repo alone, low collision risk.

| Area | Open work |
|---|---|
| Frontend / mobile | ~~PR #209~~ ✅ merged · ~~PR #210~~ ✅ merged · **#211** edge readout has no keyboard path — **fixed in PR #218, in review** |
| Frontend correctness | ~~#198~~ **already closed in code on `master`** — `pack-builder.tsx` renders `withheld_items` via `WithheldNote` (#229); the issue is open, the defect is not · ~~#140~~ issue closed |
| Test hygiene | **#184** orphan workspaces · **#182** clearance literals — **both fixed in PR #218, in review** |
| Schema-doc drift | **#195** pre-0022 global UNIQUE in `schema/postgres.sql` — **fixed in PR #218, in review** |

**Every item in this table is now merged, closed, or sitting in PR #218.** Nothing here is
startable as written — Raghav to repopulate the lane. Verified 2026-10-09 against `51f499d`.

Notes kept because they generalise:
- #182 is a 15-file mechanical fix. It is exactly the kind of sweep this repo has got wrong
  five times by scoping it wrong, not by getting the logic wrong. State your scope
  (the grep you ran, the file count it returned) in the PR body so a reader can check the
  *scope*, not just the diff.
- #195 is documentation-of-record, not a live migration. Do not write a migration for it.

### Claude owns

Work that turns on measured numbers, security invariants, or prior rulings.

| Area | Open work |
|---|---|
| Evaluation | **#203** still open · ~~PR #204 → #205 → #206 → #208~~ ✅ all merged |
| Audit coverage / P4 | **#166** still open (P4 was accepted 2026-10-08 with it recorded as a known gap) · **#168** still open · ~~PR #207~~ ✅ merged |
| Identity / RBAC | ~~#187~~ closed · ~~PR #189~~ ✅ merged · ~~PR #190~~ ✅ merged |
| Ingest & tenancy | **#196** `upsert_document` is single-workspace by construction — still open · ~~#176~~ closed · **#201** — **fixed in PR #217, in review** |
| Demo & deploy | the live demo, `docker-compose.demo.yml`, `docs/deploy/`, the tunnel, the home server |
| Measured claims | `README.md` measured block, `eval/results*.csv`, `eval/mechanism.csv`, `docs/findings.md` |

### Shared, with a handshake

`AGENTS.md`, `ROADMAP.md`, `PRD.md`, `phase.md`, `CONTRIBUTING.md`, this file. Whoever edits
one says so in their PR body. Do not edit these in a branch whose subject is something else.

## Hard rules

1. **Never rewrite history.** A `filter-repo` run on 2026-09-03 invalidated 32 SHA pins across
   the docs and the repair map is still uncommitted. No rebase of a pushed branch, no
   force-push to a shared branch, no history surgery — by either agent, ever.
2. **Migration slots are reserved, not discovered.** Two branches once collided on slot 0023.
   Codex: if you think you need a migration, open an issue instead and say why.
   **Derive the slot, never read it from this file** — a pinned number here went stale within a
   month and would have handed the next agent an occupied slot, which is the collision this rule
   exists to prevent:
   ```bash
   ls meridian/migrations/versions/*.py | sort | tail -1   # highest on master
   gh pr list --state open --search 'migrations'            # slots claimed but unmerged
   ```
   At `51f499d` (2026-10-09) that is head `0030_document_principal_role`, with `0031_membership_request`
   held by open PR #231 — so **the next free slot is 0032**.
3. **Append-only files stay append-only.** `eval/results.csv`, `eval/results-v2.csv`,
   `eval/mechanism.csv`. Never overwrite, never reformat, never sort.
4. **Never invent a number.** Every figure in a doc, README, PR body, or UI must be traceable
   to a run or a source file. If you did not measure it, do not write it. This repo has caught
   fabricated demo counts in a deploy doc once already.
   The **measured demo baseline** (over HTTPS, pack `66875926-64d0-495d-ba56-ba6d30462d8f`):
   anonymous 401 · founder 3 visible / 0 withheld · exec 3 / 0 · investor 2 / 1. Two outcomes,
   not three — founder and exec are identical below sensitivity 4. Do not re-derive these.
5. **A green test is not a passing test.** Three vacuous-check shapes have shipped here: a
   binary corpus that made every RBAC test read "investor vs everyone", raw-SQL inserts that
   create a document with no chunks so the negative passes on an empty index, and
   `_answer_correct` returning True for any text when `expect` and `forbid` are both empty.
   Prove a new test can go **red** — mutate the code under it — before you claim it covers
   anything.
6. **Registration is not coverage.** "The route is registered" proves a decorator ran. #166 is
   open precisely because 32 routes existed and were never called by a test.
7. **`git rebase <upstream>` lies.** It reports "up to date" while keeping the commits you
   meant to drop (#178). Use `--onto` and verify with `git log origin/master..HEAD`.
8. **Do not touch the other lane's files** to make your branch pass. Open an issue, assign it
   to the owning lane, and note the dependency in your PR.

## Claiming work — the ledger

Before starting anything, append a row to the table below **in its own commit on `master`**,
pushed immediately, so the other agent sees the claim before it duplicates the work. Append
only; never edit or delete someone else's row — close it by setting the status.

Status: `CLAIMED` → `IN PROGRESS` → `PR #n OPEN` → `MERGED` / `DROPPED`.

| Date (IST) | Agent | Issue/PR | Branch | Worktree | Status |
|---|---|---|---|---|---|
| 2026-09-11 | Claude | #203 stack | `eval/founder-only-tier` … `eval/abstention-strata` | callosum | **MERGED** |
| 2026-09-11 | Claude | #166 | `feat/audit-refusal-and-failure-166` | callosum-166 | **MERGED** (PR #207; #166 itself still open) |
| 2026-09-11 | Codex | — | — | callosum-mobile | unclaimed — pick from the Codex lane above |
| 2026-10-09 | Devguru | #225 | `feat/membership-grant-approval-225` | main checkout | PR #231 OPEN |
| 2026-10-09 | Devguru | #213 | `fix/213-stress-audit` | main checkout | PR #215 OPEN |
| 2026-10-09 | Devguru | #216 / #201 | `docs/compliance-governance` | main checkout | PR #217 OPEN (stacked on #215) |
| 2026-10-09 | Devguru | #159 #182 #183 #184 #195 #211 | `fix/hygiene-open-issues` | main checkout | PR #218 OPEN |
| 2026-10-09 | Devguru | #220 | `fix/ai-prompt-boundary` | main checkout | PR #219 OPEN |

## Known dirty state

**The 2026-09-11 entry is spent and is recorded here rather than deleted**, because "do not
revert these files" is exactly the instruction that causes harm once it is stale: the
`eval/mechanism.csv` (+104) and `scripts/eval.sh` (+23) changes, and the six `eval/*` commits
ahead of `origin/master`, all landed with the #203 stack. Nothing is being protected now.

A dirty-state note needs a date and an owner, or the next reader cannot tell a live warning
from an expired one. If you leave work uncommitted for another session, add a dated row and
strike it when it lands.

---

## Corrections, 2026-10-09 (Devguru, against `51f499d`)

This file is on the shared list above, so the edit is recorded here as well as in the PR.
Reviewed as PR #212; **the rules were right and the facts had expired.** Everything below is a
factual correction. **No lane assignment was changed, added or moved** — who owns what is the
maintainer's decision and the point of the document.

| What was wrong | Why it mattered |
|---|---|
| Hard rule 2 pinned "next free slot is **0030**" | `0030` merged in #189; `0031` is held by open PR #231. The rule that exists to prevent slot collisions was itself handing out an occupied slot. Now derived by command |
| All **nine** PRs in the lane tables were listed as open | #209, #210, #204, #205, #206, #208, #207, #189, #190 — all merged |
| #140 listed as open Codex work | issue closed |
| #198 listed as open Codex work | already closed in code on `master`: `pack-builder.tsx` renders `withheld_items` via `WithheldNote` (#229). The issue is open; the defect is not |
| #211, #184, #182, #195 assigned to Codex | all four are fixed in PR #218, in review. Assigning them would have produced duplicate work |
| #201 in the Claude lane; #176 and #187 listed as open | #201 is fixed in PR #217; #176 and #187 are closed |
| Worktree table pinned to three branches | all three have merged; only the agent in a worktree knows what is checked out there |
| Ledger showed #204/#205/#206/#208 and #207 as OPEN | merged; statuses closed per the append-only rule, rows left intact |
| "Known dirty state" protected files that had long since landed | a stale "do not revert" is worse than none |
| "Raghav — the only human" | there is a second human contributor, and `rules.md` §5 names him backend owner |

**Left for Raghav, deliberately not resolved here:**

1. **The Claude lane and `rules.md` §5 disagree about who owns backend.** Flagged inline above.
   The Codex lane is now empty of startable work and needs repopulating; both are ownership
   decisions, not facts.
2. **Checkpoint-id collision**, filed as **#233**: P5's `CP5A`/`CP5B` collide with P2's
   `CP5a`/`CP5b` by case alone, and `git log --grep` is case-insensitive. Same namespace problem
   this file guards against for migration slots — worth one convention covering both.
3. The **measured demo baseline** in hard rule 4 was not re-verified; it says not to re-derive it,
   so it was left exactly as written.
