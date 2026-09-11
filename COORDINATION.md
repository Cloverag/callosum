# Two agents, one repository

**Status: active from 2026-09-11.** Read this before touching anything. It says who owns
what, which worktree you work in, and the rules that stop two agents from destroying each
other's work. `ROADMAP.md` and `phase.md` remain authoritative for gate status; `AGENTS.md`
remains authoritative for architecture and invariants. This file is only about *ownership
and collision avoidance*.

## Who is who

| Name | What it is | Reads on start-up | Carries session history |
|---|---|---|---|
| **Claude** | Claude Code CLI | `CLAUDE.md`, `AGENTS.md`, this file | Yes — long memory of this repo across ~15 sessions |
| **Codex** | OpenAI Codex CLI | `AGENTS.md`, this file | No — starts cold every time |
| **Raghav** | The maintainer. The only human. | — | — |

Both agents push with the **same `gh` credential (`Cloverag`)**. Consequences that are not
negotiable:

- Every PR, comment, and review is attributed to `Cloverag`. **You cannot tell from GitHub
  which agent did what** — so every PR body must open with a line naming its author agent:
  `Agent: Claude` or `Agent: Codex`.
- GitHub refuses self-review on the shared account. **Neither agent can formally approve the
  other's PR.** Post review findings as a normal issue comment and let Raghav merge. A peer
  agent's approval is not a merge authorisation.
- Only Raghav merges to `master`. Neither agent merges its own work.

## Worktrees — the physical separation

Three worktrees already exist. **One agent per worktree. Never open a worktree another agent
is working in.**

```
/home/clover/clode projects/callosum         → CLAUDE   (currently eval/abstention-strata)
/home/clover/clode projects/callosum-166     → CLAUDE   (currently feat/audit-refusal-and-failure-166)
/home/clover/clode projects/callosum-mobile  → CODEX    (currently master @ 658436e)
```

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
| Frontend / mobile | **PR #209** app shell mobile drawer · **PR #210** knowledge-graph mobile · **#211** edge readout has no keyboard path |
| Frontend correctness | **#198** `packs.ts` header forbids the withheld count ADR-018 requires · **#140** documents intake UI against #128's JSON endpoint |
| Test hygiene | **#184** three test files leak five orphan workspaces per gated run · **#182** 15 test files seed `principal.clearance` with a literal that contradicts the role beside it |
| Schema-doc drift | **#195** `schema/postgres.sql` still declares the pre-0022 global UNIQUE on `document.content_hash` |

Notes for Codex on those:
- #209/#210 are **already open PRs with commits on them**. Read the branch before adding to it.
- #182 is a 15-file mechanical fix. It is exactly the kind of sweep this repo has got wrong
  five times by scoping it wrong, not by getting the logic wrong. State your scope
  (the grep you ran, the file count it returned) in the PR body so a reader can check the
  *scope*, not just the diff.
- #195 is documentation-of-record, not a live migration. Do not write a migration for it.

### Claude owns

Work that turns on measured numbers, security invariants, or prior rulings.

| Area | Open work |
|---|---|
| Evaluation | **#203** and its stack: **PR #204 → #205 → #206 → #208** (stacked; merge order matters) |
| Audit coverage / P4 | **#166** (32 of 43 mutating routes write no audit event) · **#168** · **PR #207** refusal + failure tests |
| Identity / RBAC | **#187** · **PR #189** · **PR #190** |
| Ingest & tenancy | **#196** `upsert_document` is single-workspace by construction · **#176** · **#201** `callosum init` grants membership to every principal row |
| Demo & deploy | the live demo, `docker-compose.demo.yml`, `docs/deploy/`, the tunnel, the home server |
| Measured claims | `README.md` measured block, `eval/results*.csv`, `eval/mechanism.csv`, `docs/findings.md` |

### Shared, with a handshake

`AGENTS.md`, `ROADMAP.md`, `PRD.md`, `phase.md`, `CONTRIBUTING.md`, this file. Whoever edits
one says so in their PR body. Do not edit these in a branch whose subject is something else.

## Hard rules

1. **Never rewrite history.** A `filter-repo` run on 2026-09-03 invalidated 32 SHA pins across
   the docs and the repair map is still uncommitted. No rebase of a pushed branch, no
   force-push to a shared branch, no history surgery — by either agent, ever.
2. **Migration slots are reserved, not discovered.** Latest is `0029_workspace_bootstrap.py`;
   **next free slot is 0030**. Claude holds the pen on migrations. Two branches once collided
   on slot 0023. Codex: if you think you need a migration, open an issue instead and say why.
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
| 2026-09-11 | Claude | #203 stack | `eval/founder-only-tier` … `eval/abstention-strata` | callosum | PR #204/#205/#206/#208 OPEN |
| 2026-09-11 | Claude | #166 | `feat/audit-refusal-and-failure-166` | callosum-166 | PR #207 OPEN |
| 2026-09-11 | Codex | — | — | callosum-mobile | unclaimed — pick from the Codex lane above |

## Known dirty state at the time of writing

In the `callosum` worktree, uncommitted and **belonging to Claude**:
`eval/mechanism.csv` (+104) and `scripts/eval.sh` (+23). Do not stage, stash, or revert them.

Six commits on `eval/*` are ahead of `origin/master` by design — they are the stacked PR
chain, not stray work.
