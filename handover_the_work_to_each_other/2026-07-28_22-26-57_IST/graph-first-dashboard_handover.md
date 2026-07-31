# Proposal review — "make the graph the hero" dashboard redesign

**Date:** 2026-07-26
**Source:** external review (pasted by the owner; authored by another assistant)
**Companion doc:** `2026-07-26_frontend-registries-review.md`
**Status:** proposal + engineering assessment. **Nothing here is built.**

---

## 0. TL;DR for a reviewer

The core thesis is **right and worth doing**: the dashboard visualises *metrics
about* the graph instead of the graph, and Callosum's whole differentiator is the
verified graph. Issue #13 (Graph Viewer) already exists for exactly this.

But the proposal is built on a **factual error about the data** (§2), and about a
third of its specific recommendations **contradict this repo's own design rules and
the dataviz method** (§4). Adopt the thesis; do not adopt the shopping list as-is.

---

## 1. The proposal, condensed

Replace a dashboard of counters and line charts with a graph-first information
architecture, and split the product into five views:

| View | Contents |
|---|---|
| **Overview** | KPIs, graph health, recent activity, memory growth |
| **Knowledge Graph** | interactive node-link explorer + filters + evidence panel |
| **Timeline** | ingestion, decisions, supersessions, ontology evolution |
| **Analytics** | ontology distribution, communities, relation types, grounding metrics |
| **Search & Retrieval** | hybrid search with evidence, graph paths, provenance, confidence |

Ten specific surfaces proposed: interactive graph hero, community bubble map,
provenance timeline, a broken-out graph-health panel (evidence coverage / grounding
recall / GER / traversal / precision as bars), ontology treemap, temporal activity
bars, relationship-type radial chart, search-activity feed, a full-page graph
explorer, and a richer memory-growth chart using **line style instead of colour**
to separate series.

Libraries suggested: React Flow or Cytoscape.js, Sigma.js, Recharts, Nivo, Vis
Timeline — explicitly *instead of* leaning on Bklit.

Inspiration named: Neo4j Bloom, Linkurious, Graphistry, Langfuse, Grafana,
Superset, Metabase, Observable/D3, ECharts, Magic UI, Aceternity UI, Origin UI.

---

## 2. ⚠ The factual error — two different graphs got conflated

The proposal reasons from *"you already have 731 entities, 1277 edges, 60
communities."* **Those numbers are not Callosum's institutional-memory graph.**

They are the **graphify snapshot of this repository's own source code**, cut at tag
`meridian-p1.0.2` (731 nodes / 1277 edges / 53 communities). They were seeded into
`frontend/src/lib/insights.ts` as *mock dashboard data* — the comment in that file
says so — so the demo would show plausible figures.

The real Callosum knowledge graph, built from the demo corpus, is far smaller:

```
data/demo/                     16 documents (5 board transcripts + finance,
                               compensation, and 8 deliberately messy sources)
evaluate.py seeded gold graph  ~41 entities, ~40 relationships
```

### Why this matters, and why it is good news

- A **~40-node graph is ideal for a node-link hero.** It is readable, laid out
  honestly, and every node can be labelled. This makes the headline idea *easier*
  than the proposal assumes — no clustering, no WebGL, no Sigma.js.
- Conversely the **community bubble map is meaningless at this scale.** 53–60
  communities exist in the *code* graph, not the memory graph. Drop it.
- Anything premised on 731 nodes (GPU rendering, aggressive filtering, Graphistry)
  is solving a problem this project does not have.

**Action for whoever builds this: fix the mock or label it.** Right now
`insights.ts` presents code-graph metrics as institutional-memory metrics. That is
a demo honesty problem independent of any redesign, and it matters more for an FYP
defence than any chart styling.

---

## 3. The second constraint — there is no API

`ROADMAP.md` P3 (authenticated API + app shell) is **not started**. The frozen core
is CLI/Python; `meridian/api/main.py` is a 42-line stub with `/health` only. The
entire frontend runs on mocks in `src/lib/*`.

So of the ten proposed surfaces:

| Buildable now (on mocks) | Needs P3 (real API) |
|---|---|
| Knowledge-graph hero (seed from the gold graph) | Search-activity feed — needs a real query log |
| Ontology distribution | Live graph explorer over Neo4j |
| Relationship-type breakdown | Real ingestion/provenance timeline |
| Graph-health metric panel (real numbers exist in `eval/`) | Anything reflecting live tenant data |

The graph-health panel is the **cheapest high-value win**: those numbers are already
real and already measured — traversal 100%, grounding recall 17/21, GER 19%,
precision 1/2, candidate recall 22/22 — sitting in `eval/mechanism.csv` and
`eval/results-v2.csv`. Today the dashboard invents a health figure instead of
showing the ones the project actually earned.

---

## 4. Where the proposal conflicts with rules already decided here

Not style disagreements — these are documented rules in `frontend/DESIGN.md`,
`frontend/PRODUCT.md`, and the `dataviz` method.

| Proposal | Conflict | What to do instead |
|---|---|---|
| Community bubbles coloured **by graph health** | Status colours are reserved for good/warning/critical and must not double as a categorical/continuous channel | Size = node count; health as an explicit status badge with icon + label |
| **Ontology treemap** across 7 entity types | *"More than ~7 colour classes carrying meaning → use a table"*; also violet-only doctrine leaves no categorical palette | Horizontal bar chart, one hue, sorted — or a table. Both beat a treemap for comparing 7 values |
| **Radial chart** for relationship types | Radial bars encode magnitude as arc length at varying radius, so equal values look unequal — a classic distortion | Plain horizontal bars. The proposal's own ASCII sketch is already bars |
| **Magic UI / Aceternity UI** | `DESIGN.md` Don'ts: *"Don't use gradients, neon, glow-as-default"*; anti-refs include crypto-fintech neon and AI-slop tells | Keep the current primitives. Animate UI (already vendored) is the aesthetic-neutral option |
| Separate **gauge + bars + counters** per metric | *"Eight categorical hues when the story is one number"* — and a KPI row of 5 bars is fine, but each needs a stated scale | Bars are right; give each a labelled 0–100% track so 50% precision doesn't read as "half a bar of something" |
| **Grafana** as a model | Grafana is a dark, dense ops console; this product's voice is "Calm Executive Trust", light-only | Langfuse and Metabase are the on-brief references. Superset/Grafana are not |

### Where the proposal is straightforwardly right

- **Graph as hero.** Yes. This is the differentiator and it is currently invisible.
- **Break graph health into its real component metrics.** Yes — and the numbers exist.
- **"Different line styles instead of different colours"** for memory growth. This is
  exactly the correction already applied in `c619f9f`, arrived at independently:
  violet-700 vs violet-500 measured **ΔE 11.7** against a floor of 15, so the two
  series were rebuilt as *filled area vs bare line*. The proposal and the validator
  agree.
- **Bklit is heavier than this project needs.** Agreed, and already flagged as open
  question 7.1 in the companion review — ~60 vendored files and `@visx@4.0.1-alpha.0`
  to draw one area and one line.
- **Evidence panel on node click** (source quote, provenance, superseded-by). This is
  the Callosum thesis made visual and it is the single most compelling demo surface.

---

## 5. Library assessment

| Suggested | Verdict |
|---|---|
| **React Flow** | Best fit for a ~40-node explorer. Declarative, React-native, good a11y story, no canvas escape hatch needed at this scale |
| **Cytoscape.js** | Stronger graph algorithms, but imperative and heavier to bind to React state. Overkill here |
| **Sigma.js / Graphistry** | Solving a 10k-node problem this project doesn't have. Skip |
| **Recharts** | Reasonable, but it is a *third* charting stack after Bklit and the hand-rolled SVG primitives. Only adopt if Bklit is removed first |
| **Nivo** | Same objection, plus it brings its own theming model that fights the semantic token layer |
| **Vis Timeline** | Not needed — a provenance timeline is a list with a rule down the left. Hand-roll it |

**Recommendation: add exactly one library — React Flow — and remove Bklit rather than
stacking a third chart stack on top of it.** The existing hand-rolled `Gauge`,
`Sparkline`, `StatBar` already cover the metric surfaces; a horizontal bar panel is
~40 lines. That leaves the dependency budget for the one thing genuinely hard to
hand-roll: an interactive node-link graph with layout.

---

## 6. Suggested sequencing (smallest change that increases confidence first)

Consistent with the project's stated working style — one verified change per commit,
measure before refactoring, don't over-engineer V1.

1. **Fix the mock honesty problem.** Either seed `insights.ts` from the real gold
   graph or label the figures as code-graph metrics. Cheap, and it removes a claim
   the project cannot defend. *(No new dependency.)*
2. **Graph-health metric panel** using the real `eval/` numbers — evidence coverage,
   grounding recall, GER, traversal, precision — as labelled bars on a 0–100 track.
   Highest value-to-effort ratio in the whole proposal. *(No new dependency.)*
3. **Decide Bklit in or out** before adding anything else. This blocks 4 and 5.
4. **Knowledge-graph hero** on React Flow, seeded from the gold graph, with the
   evidence panel on node click. This is issue #13 and the demo centrepiece.
5. **Ontology + relationship-type bars.** Both are the same component with different
   data; build once.
6. **Defer** search activity, ingestion timeline and the live explorer to P3, when an
   API exists to feed them.

The five-view IA (Overview / Graph / Timeline / Analytics / Search) is a sound
destination, but adopting it now would create three routes with nothing real behind
them. Grow into it as the data arrives.

---

## 7. ⚠ CHALLENGE THIS

1. **Is a ~40-node graph impressive enough to be the hero?** It is honest and
   readable, but a reviewer may find it thin next to the claim. The alternative —
   ingesting a larger corpus — is a research-track decision, not a frontend one, and
   the corpus is deliberately a capability matrix rather than a pile of documents.
2. **Does React Flow's licence and bundle size suit an FYP?** Not checked this
   session.
3. **Is the graph hero on `/dashboard` or its own route?** The proposal says both.
   Putting a node-link canvas in a scrolling dashboard fights the scroll.
4. **Nothing here is validated against a rendered screen.** Same gap as the companion
   review: the current memory-growth chart has still never been looked at by a human.
5. **The five-view IA implies a nav restructure**, which touches the shipped shell in
   PR #25 — a branch that is already unmerged and stacked two deep.
