# Security policy

This repository is a research/product prototype with a **public synthetic demo**.
It is not a certified security product. Please still report anything that would
let a visitor read another identity's material, bypass tenancy, or write the
graph without a human approve.

## Reporting a vulnerability

**Do not open a public GitHub issue** for a vulnerability.

1. Use [GitHub private vulnerability reporting](https://github.com/Cloverag/callosum/security/advisories/new) on this repository.
2. If that form is unavailable, open a **private** advisory from the Security tab after the owner enables reporting (see `docs/compliance/GITHUB.md`).

Include: affected path or URL, what you could read or write, and a minimal
reproduction against the **demo corpus** or a local compose stack. Do not
attach real personal data.

There is **no bug bounty**. We will acknowledge a valid report and say when a
fix is on `master`.

## What is in scope

- Authorization (clearance, RLS, withheld titles, demo selector).
- Session cookie handling, CORS, OpenAPI exposure, rate limits.
- Supply-chain issues in **direct** production dependencies (frontend `npm`
  production tree, Python runtime deps).
- Anything that would let extraction write Neo4j without `store.approve()`.

## What is out of scope

- The demo identity selector itself, when used on the **fabricated** demo
  database — it is a documented impersonation endpoint
  (`docs/deploy/DEMO_AUTH_SPEC.md`).
- Findings that require `MERIDIAN_DEMO_SELECTOR` enabled against **real**
  data — that configuration is forbidden; report it as a **deployment**
  incident, not an app bug.
- Denial of service against the home-server demo host.
- Social engineering, physical access, or issues in Keycloak `start-dev`
  (local IdP, no TLS, in-memory H2).

## Safe harbor

Research against the public demo and this GitHub repository is welcome if you
stay within the fabricated corpus, do not degrade the host, and report in
private first.
