# Screenshots

Referenced by the root `README.md`. Capture at **1440×900**, light theme, on seeded
demo data — never on anything real.

Run the app first — **two processes**, both must stay running. Starting only the second
is the common mistake: every page loads and every panel shows an error, because `/api/*`
resolves to the Next dev server, which has no such routes.

```bash
docker compose up -d                                          # wait for all three healthy

.venv/bin/uvicorn meridian.api.main:app --reload --port 8000   # terminal 1, repo root
cd frontend && npm run dev                                     # terminal 2 → :3000
```

Full setup, seeding and the demo logins are in [demo-setup.md](../demo-setup.md).
Sign in as `raj` / `raj` for every shot except `memory-withheld.png`.

| File | Route | What it has to show |
|---|---|---|
| `dashboard.png` | `/dashboard` | The board home. Note the em dashes on unmeasured counts — that is the data-honesty rule visible in the product, and it is worth the screenshot. |
| `memory-graph.png` | `/memory` | The knowledge graph with a node selected, evidence panel open showing a **verbatim quote** and its source document. This is the thesis in one image. |
| `memory-withheld.png` | `/memory` | The same graph with clearance toggled to Investor, showing *"1 entity and 1 relationship withheld"*. Withholding disclosed as a count, never as content. |
| `packs.png` | `/packs` | A board pack with clearance-filtered items, renumbered from 1. |
| `meeting-conflict.png` | `/calendar` | The 409 conflict dialog: "Someone else saved this meeting while you were editing", with **their** values and the two choices. |

**Do not** crop out the browser chrome entirely — a screenshot that could be a mockup is
worth less than one that is obviously a running application.
