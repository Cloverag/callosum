# Postmortem — Meridian P1

**Release:** `meridian-p1` (`04dfd2f`) · **Date:** 2026-07-19 · **Outcome:** shipped clean, no incident.

A postmortem is written for every release even when nothing failed — the point is to convert what we
*learned* into rules before it fades. Below is the engineering-record view (grounded in the ADRs,
reviews, and PR history); the judgement calls are yours to confirm or amend.

## 1. What surprised us?

- **Postgres superusers bypass RLS unconditionally — `FORCE` cannot stop them.** The isolation model
  looked complete with `ENABLE`+`FORCE`, but a superuser connection silently ignored the policy. This
  forced the two-role / two-DSN split (`callosum` for migrations vs `callosum_app` NOSUPERUSER
  NOBYPASSRLS at runtime). See ADR-003. The security guarantee lived in *who connects*, not just the policy.

## 2. What was harder than expected?

- **Neo4j has no RLS**, so tenant isolation couldn't mirror the Postgres approach. A query-level WHERE
  filter was insufficient — a colliding entity name could bridge tenants through a shared node. The fix
  was *structural*: bake `workspace_id` into the entity MERGE identity `(name, type, workspace_id)` so
  tenants are partitioned by construction (ADR-004). Two stores meant designing isolation twice.
- **Eval throughput was gated by Ollama Cloud 429 session limits**, not by the code — heavy runs on one
  account hit the cap, and there was no local chat model to fall back to.

## 3. What almost went wrong?

- **The frontend PR (#9) nearly polluted the frozen research eval record.** An agent sanity-check
  appended ~58 rows to `eval/results.csv`. Caught in review before merge; reverted and verified
  byte-identical to master. Had it merged, the immutable research baseline's history would have been
  corrupted by an out-of-scope frontend change.

## 4. What should become a rule?

- **Diff-scope check before any merge** — nothing outside the PR's stated scope lands (a frontend PR
  touches only `frontend/` + its own docs). This caught #9.
- **Never modify frozen artifacts from an unrelated PR** — eval CSVs, gold sets, and baseline tags are
  off-limits to product/frontend work.
- **Graphify at the tag, never mid-development** — already encoded in the release cadence (step 4).
- **One migration head** — Alembic linear history; re-parent external features rather than fork the chain.
- **Freeze before refactor; merge foundation before features; one RFC at a time.** The recurring win
  this project came from asking *"what's the smallest change that increases confidence?"* rather than
  *"what's the smartest architecture?"*

## 5. What should we never do again?

- **Evade an API rate limit with a throwaway account** — already refused during P0 eval (ToS); keep it a
  hard line. Wait for quota or use a real local model instead.
- **Let a "quick sanity-check" run write into version-controlled frozen data.** Sanity checks output to
  scratch, never to `eval/`.

---

*Confirm / amend §1–§3 (the "surprised / harder / almost" calls are subjective — this draft reflects the
documented record). Any new item under §4 should be promoted into `docs/releases/README.md`.*
