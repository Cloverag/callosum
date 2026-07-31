# Screenshots

Referenced by the root `README.md`. Capture at **1440×900**, light theme, on seeded
demo data — never on anything real.

Run the app first:

```bash
docker compose up -d
cd frontend && npm run dev        # http://localhost:3000
```

| File | Route | What it has to show |
|---|---|---|
| `dashboard.png` | `/dashboard` | The board home. Note the em dashes on unmeasured counts — that is the data-honesty rule visible in the product, and it is worth the screenshot. |
| `memory-graph.png` | `/memory` | The knowledge graph with a node selected, evidence panel open showing a **verbatim quote** and its source document. This is the thesis in one image. |
| `memory-withheld.png` | `/memory` | The same graph with clearance toggled to Investor, showing *"1 entity and 1 relationship withheld"*. Withholding disclosed as a count, never as content. |
| `packs.png` | `/packs` | A board pack with clearance-filtered items, renumbered from 1. |
| `meeting-conflict.png` | `/calendar` | The 409 conflict dialog: "Someone else saved this meeting while you were editing", with **their** values and the two choices. |

**Do not** crop out the browser chrome entirely — a screenshot that could be a mockup is
worth less than one that is obviously a running application.
