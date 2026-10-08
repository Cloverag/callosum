# Incident response (demo / prototype)

This is a one-pager for the **synthetic public demo** and this GitHub
repository. It is not a SOC 2 incident program.

## Severity

| Level | Meaning | First action |
|---|---|---|
| S1 | Real personal data on the demo host, or a tenant database with `MERIDIAN_DEMO_SELECTOR=true` | Disable the selector; take the API down; rotate secrets |
| S2 | Authorization bypass on the fabricated corpus (wrong identity sees withheld titles) | Disable selector if needed; patch; rotate session secret |
| S3 | Dependency CVE, docs accidentally exposed, rate-limit gap | Patch in a PR; no host takedown unless exploited |

## Disable the demo

1. Set `MERIDIAN_DEMO_SELECTOR` to empty/false on the API host and recreate the
   API container (`docs/deploy/DEPLOY.md`).
2. To take the site off the internet: pause the Cloudflare tunnel and/or the
   Vercel project.
3. `/docs` and `/openapi.json` must stay off (`ENVIRONMENT=production`,
   `MERIDIAN_EXPOSE_DOCS` unset).

## Rotate (S1 / S2)

Rotate in this order, then restart the API:

1. `MERIDIAN_SESSION_SECRET` — invalidates every demo session.
2. Cloudflare tunnel token (if the tunnel is the exposure).
3. Vercel environment variables that proxy to the API.
4. Database passwords only if the host itself was reached.

Record what you rotated in a **private** note, not a public issue.

## Who

Names live in `docs/compliance/CONTROL_MATRIX.md` (access inventory). If a row
is empty, the GitHub org owner is the default.

## Afterward

- File or update a GitHub advisory if a vulnerability in this repo was involved
  (`SECURITY.md`).
- Do not put payloads in public issues.
- Residual product risks stay on the issue tracker (`#195`, `#196`,
  `#213`); an incident does not close them.
