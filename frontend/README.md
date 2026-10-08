# Meridian frontend

Next.js 16 App Router UI for Callosum / Meridian. Light-mode **Calm Desk** design
(`DESIGN.md`). The browser talks only to this origin; `/api/*`, `/auth/*` and
`/health` are rewritten to the FastAPI process (`next.config.ts`).

Setup, identity, and the live demo are documented in the **repository root**
[`README.md`](../README.md), not here. Do not start this app without the API — every
page will load and every panel will error.

```bash
# from repo root
.venv/bin/uvicorn meridian.api.main:app --reload --port 8000
# from this directory
npm ci && npm run dev    # http://localhost:3000
```

`npm test` is Jest. `npm run build` is the production compile CI runs on Node 22.
