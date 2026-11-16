# GitHub settings you must click

These controls are **not** stored in git. A passing CI run does not mean they
are on. After merging the compliance stack, an owner of `Cloverag/callosum`
should set:

## Security

1. **Settings → Code security → Private vulnerability reporting** — on.
   `SECURITY.md` points reporters here.
2. **Dependabot alerts** and **Dependabot security updates** — on
   (`.github/dependabot.yml` already describes the ecosystems).
3. **Code scanning** — CodeQL workflow is `.github/workflows/codeql.yml`.
   Confirm the first run appears under Security → Code scanning.

## `master` protection

Settings → Branches → add a rule for `master`:

- Require a pull request before merging.
- Require status checks: `Backend CI (Python 3.12 + Postgres & Neo4j)`,
  `Frontend CI (Next.js & Jest)`, `Migration chain reverses (full, down to base and back)`.
- Do **not** require CodeQL to be green until the first run is known-good
  (it can fail on existing alerts).
- Dismiss stale reviews.
- Do not allow force pushes.
- Do not allow deletions.

**Require review from Code Owners** only after a second GitHub account can
review. Same-login agents cannot approve their own PRs (`COORDINATION.md` /
PR #212). Enabling it with a single account blocks every merge.

## Pages and metadata

- Repository **LICENSE** is MIT (root `LICENSE`).
- About: do not describe the default LLM as Claude; it is Ollama
  `gpt-oss:120b-cloud`. Homepage may stay the demo URL.
