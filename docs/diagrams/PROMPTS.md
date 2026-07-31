# Diagram generation prompts

Six prompts for an image generator (ChatGPT / DALL·E / Midjourney), one per diagram.

## Read this first

**Image generators are unreliable at technical diagrams.** They garble labels, misspell
words, invent boxes that were never asked for, and cannot be trusted to preserve an
arrow's direction. For a project whose entire thesis is *"do not present unverified
things as fact"*, a diagram with an invented component is a worse failure than a plain
one.

So:

1. **Inspect every generated image against the label list in its prompt** before using
   it. If a box says `Postrges` or an arrow points the wrong way, regenerate — do not
   ship it.
2. **Never let the generator invent a component.** Each prompt below lists the exact
   boxes and exact arrows. Anything extra is wrong by definition.
3. Prefer generating **2–4 variants** and picking, rather than iterating on one.
4. If a diagram will not come out clean after a few attempts, fall back to Mermaid — it
   renders natively on GitHub, lives in the repo as text, and cannot misspell anything.

## Shared style block

Paste this at the top of **every** prompt, then the diagram-specific part.

```
Create a clean, professional software architecture diagram. Flat 2D vector
illustration, NOT isometric, NOT 3D, no perspective, no drop shadows, no gradients
except where specified.

STYLE
- Background: very light warm grey (#F7F8FA), completely flat
- Boxes: pure white (#FFFFFF) fill, 1px light grey border (#E5E7EB), 12px rounded
  corners, generous internal padding
- Typography: Inter or a near-identical geometric sans-serif. Box titles in semibold
  15px dark charcoal (#111827). Sub-labels in regular 12px medium grey (#6B7280)
- Arrows: 1.5px solid, medium grey (#9CA3AF), clean arrowheads, orthogonal routing
  (horizontal and vertical segments only, no diagonals, no curves)
- Generous white space. Nothing crowded. Wide margins.

COLOUR HAS MEANING — use it sparingly, roughly 90% neutral:
- BLUE (#2563EB): action, request flow, the live application path
- VIOLET (#6D28D9): institutional memory — the knowledge graph and anything derived
  from it
- AMBER (#F59E0B): a human decision point or a queue awaiting approval
- RED (#EF4444): a refusal, a rejection, a blocked path
- GREEN (#16A34A): a verified or accepted outcome

RULES — these are absolute
- Render ONLY the boxes and arrows listed below. Do not add components, legends,
  clouds, servers, people icons, or decorative elements that are not specified.
- Spell every label EXACTLY as written. Do not paraphrase, expand, abbreviate or
  translate any label.
- No logos of any real company or product.
- Landscape orientation, 16:9.
```

---

## 1 — Ingestion pipeline

```
[SHARED STYLE BLOCK]

DIAGRAM: a left-to-right pipeline showing how a document becomes verified memory.

Seven stages in one horizontal row, connected by arrows left to right:

1. Box, neutral. Title "Document". Sub-label "transcript · memo · email"
2. Box, neutral. Title "Chunk". Sub-label "character offsets preserved"
3. Two boxes stacked vertically, both fed by an arrow from "Chunk":
   - upper box, neutral: Title "Embed". Sub-label "bge-m3 · 1024-dim"
   - lower box, neutral: Title "Extract". Sub-label "LLM proposes entities and edges"
4. From "Extract" only, an arrow into a DIAMOND decision shape, amber border,
   white fill. Label inside: "locate() finds the quote?"
5. From the diamond, TWO arrows:
   - downward, RED, labelled "no" → box with a red border, title "Quarantine",
     sub-label "kept with a typed reason, never dropped"
   - rightward, GREEN, labelled "yes" → box with amber border, title
     "proposed_change", sub-label "awaiting human approval"
6. From "proposed_change", a BLUE arrow labelled "a human approves" into a
   VIOLET-bordered box, title "Knowledge graph", sub-label "Neo4j"
7. From the upper "Embed" box, a separate arrow right into a neutral box titled
   "pgvector", sub-label "Postgres"

At the bottom, centred, one line of 13px italic grey text, exactly:
"No edge enters the graph without a quote located in the source document."
```

---

## 2 — Graph + vector architecture

```
[SHARED STYLE BLOCK]

DIAGRAM: two stores side by side, joined by a shared identifier. This is the central
architecture picture, so it must be the cleanest of the set.

LEFT — a large rounded container, neutral border, titled "Postgres 16 + pgvector".
Inside it, four small stacked boxes:
  "document"  ·  "chunk + embedding"  ·  "proposed_change"  ·  "product domain"

RIGHT — a large rounded container with a VIOLET border, titled "Neo4j 5".
Inside it, three small stacked boxes:
  "Entity"  ·  "Relationship"  ·  "Chunk"

BETWEEN THEM, horizontally centred, a single prominent element: a rounded pill with a
violet fill at 10% opacity and a violet border, containing the text
"shared chunk UUID".

Two arrows through that pill, one above the other:
  - upper arrow pointing LEFT to RIGHT, labelled "a vector hit traverses into the graph"
  - lower arrow pointing RIGHT to LEFT, labelled "a graph hit returns the passage that proves it"

Both arrow labels in 12px grey, placed above their arrow, not overlapping it.

At the bottom, centred, 13px italic grey text, exactly:
"Two hemispheres. The bridge is the whole idea."
```

---

## 3 — Authentication and session flow

```
[SHARED STYLE BLOCK]

DIAGRAM: a numbered request sequence, laid out as four vertical columns with arrows
between them. Column headers across the top, boxes and arrows below.

COLUMNS, left to right:
  "Browser"  ·  "Next.js"  ·  "FastAPI"  ·  "Keycloak (OIDC)"

Arrows between columns, each numbered and labelled, top to bottom:
  1. Browser → Next.js:   "GET /dashboard"
  2. Next.js → FastAPI:   "proxied /api/*"        [BLUE arrow]
  3. FastAPI → Keycloak:  "unknown session · redirect to sign in"
  4. Keycloak → FastAPI:  "callback with subject"
  5. FastAPI → FastAPI (a short self-loop, arrow curving back to the same column):
     "principal_identity lookup on (provider, subject)"
  6. FastAPI → Browser:   "httpOnly signed cookie"  [BLUE arrow]

To the right of step 5, a small callout box with a RED border, no arrow, containing
two lines:
  "Unknown subject → rejected"
  "No auto-provisioning"

At the bottom, spanning the full width, a neutral strip box containing exactly:
"workspace_id and clearance are re-derived from the session on every request — never
accepted from the client."
```

---

## 4 — Evidence verification

```
[SHARED STYLE BLOCK]

DIAGRAM: a close-up of the single most important mechanism. Only four elements, large
and legible. This one should feel like a magnified detail, not a system overview.

TOP LEFT — a box styled like a document page, neutral, titled "Source document".
Inside it, three lines of small grey placeholder text, and ONE line highlighted with a
soft green background showing exactly:
  "We're not doing Model B."

TOP RIGHT — a box, neutral, titled "LLM proposes". Inside, two lines:
  "Raj Malhotra —[APPROVED]→ Reject Pricing Model B"
  "quote: \"We're not doing Model B.\""

CENTRE — both top boxes have arrows pointing down into a single wide box with an amber
border, titled "locate()". Inside it, three short lines:
  "tolerates whitespace reflow"
  "tolerates case and glyph differences"
  "tolerates nothing else"

BOTTOM — from "locate()", two diverging arrows:
  - left, GREEN, labelled "found" → box with green border: "Edge stored, with character
    offsets"
  - right, RED, labelled "not found" → box with red border: "Quarantined, with a typed
    reason"

At the bottom, centred, 13px italic grey text, exactly:
"A paraphrase is treated as a fabrication."
```

---

## 5 — API architecture

```
[SHARED STYLE BLOCK]

DIAGRAM: layered, top to bottom, showing one request passing through the API.

FOUR horizontal bands, each a wide rounded box, stacked with arrows pointing downward
between them:

BAND 1, BLUE border, titled "9 routers".
  Inside, a single row of small pills, evenly spaced:
  "meetings" "agenda" "decisions" "packs" "minutes" "resolutions" "commitments"
  "board-members" "documents"

BAND 2, neutral, titled "deps.current_principal".
  Sub-label: "resolves workspace and clearance from the session, per request"

BAND 3, neutral, titled "10 domain modules".
  Sub-label: "expected_version on every mutation"

BAND 4, neutral, titled "Postgres — row-level security".
  Sub-label: "ENABLE + FORCE · runtime connects as a non-superuser role"

To the RIGHT of band 1, outside the stack, a small box with a RED border, connected to
band 1 by a short red arrow pointing left. It contains two lines:
  "OpenAPI schema test"
  "no endpoint may declare workspace_id or clearance"

To the RIGHT of band 3, outside the stack, a small neutral box connected by a short
grey arrow pointing left, containing:
  "409 on a version mismatch"

At the bottom, centred, 13px italic grey text, exactly:
"61 operations. The scope of a request is never something the request can choose."
```

---

## 6 — Product architecture

```
[SHARED STYLE BLOCK]

DIAGRAM: the package boundary between the frozen research engine and the product built
on it. The boundary is the subject of the picture.

TOP — a wide container with a VIOLET border, titled "meridian/ — product".
  Inside, three rows of small boxes:
    row 1: "frontend/ — Next.js, 15 routes"
    row 2: "meridian/api/ — FastAPI, 61 operations"
    row 3: "meridian/*.py — 10 domain modules"  and  "migrations/ — 17"

MIDDLE — a single horizontal dividing line, dashed, medium grey, spanning the full
width. Centred ON the line, a small white pill with a grey border containing exactly:
  "import callosum"

BOTTOM — a wide container with a heavier neutral border and a very light grey fill,
titled "src/callosum/ — research engine".
  Immediately under the title, a small pill with a BLUE border: "FROZEN — eval-baseline-v3"
  Inside, one row of five small boxes:
    "ingest.py" "extract.py" "retrieve.py" "store.py" "schema/postgres.sql"

ONE arrow only, pointing DOWNWARD from the product container, through the "import
callosum" pill, into the engine container.

To the right of the dashed line, a small callout with a RED border, unconnected:
  "The product never edits the engine."

At the bottom, centred, 13px italic grey text, exactly:
"A dependency, not a fork."
```

---

## After generating

Save into `docs/diagrams/` as:

| File | Prompt |
|---|---|
| `01-ingestion.png` | 1 |
| `02-graph-vector.png` | 2 |
| `03-auth-session.png` | 3 |
| `04-evidence-verification.png` | 4 |
| `05-api-architecture.png` | 5 |
| `06-product-architecture.png` | 6 |

Then check each against its label list. The most common failures, in order:

1. a misspelled label
2. an arrow reversed
3. an extra invented box
4. the shared-UUID pill rendered as a database instead of a label

Diagram **2** is the one to get right if you only get one right — it is the thesis in a
single picture, and it is the image most likely to be looked at.
