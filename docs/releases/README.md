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
   release. Run in Kitty (fish; claude-cli backend; text/code scope, not media):
   ```
   graphify . --update --obsidian --obsidian-dir "/home/clover/Documents/Obsidian Vault/Meridian"
   ```
   Drop `--update` if there is no existing baseline graph. Do this at the tag, not mid-development —
   an arbitrary rebuild produces a graph that corresponds to nothing.
5. **Publish** — write the release notes (`docs/releases/meridian-pN.md`: commit, tag, research
   baseline, capabilities, acceptance metrics, known limitations, deferred RFCs, ADR + freeze links)
   and add the row to the index below. Release-notes and graph commits may land *after* the tag —
   they describe the tag, so the tagged code tree stays untouched.
6. **Postmortem** — write `docs/releases/meridian-pN-postmortem.md` **even if nothing failed.** Five
   questions: (1) What surprised us? (2) What was harder than expected? (3) What almost went wrong?
   (4) What should become a rule? (5) What should we never do again? Answers to (4) feed back into
   this checklist — this is where the process improves, release over release.

## Releases

| Tag | Commit | Date | Notes | Postmortem |
|-----|--------|------|-------|-----------|
| `meridian-p1` | `04dfd2f` | 2026-07-19 | [meridian-p1.md](meridian-p1.md) — P1 multi-tenancy (Postgres RLS + Neo4j entity partitioning) + entity_conflict + Next.js frontend shell |
| `meridian-p1.0.1` | `43d64f3` | 2026-07-20 | [meridian-p1.0.1.md](meridian-p1.0.1.md) — patch: scope entity-conflict detection to workspace (F2); restores the P1 Cypher-isolation invariant |
| `meridian-p1.0.2` | `4c375b7` | 2026-07-20 | [meridian-p1.0.2.md](meridian-p1.0.2.md) — hardening: Neo4j query gateway (P2-RFC-001) closes Defect Class D-001; CI ban-test enforces no raw session outside gateway/allowlist | [postmortem](meridian-p1-postmortem.md) |
