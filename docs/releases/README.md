# Release process

How a Callosum product baseline is cut. Each release is an immutable tag with a matching
release-notes file in this directory. The cadence is fixed so that **every knowledge graph and
every published doc corresponds to a tagged release, not an arbitrary point in development.**

## Cadence

```
merge  →  freeze  →  tag  →  graphify  →  publish
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

## Releases

| Tag | Commit | Date | Notes |
|-----|--------|------|-------|
| `meridian-p1` | `04dfd2f` | 2026-07-19 | [meridian-p1.md](meridian-p1.md) — P1 multi-tenancy (Postgres RLS + Neo4j entity partitioning) + entity_conflict + Next.js frontend shell |
