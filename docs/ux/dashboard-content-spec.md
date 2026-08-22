# Meridian — Dashboard Content Spec (prototype IA)

Content only. No colour, type, spacing, or layout opinions — every item below is *what
the screen says*, not how it looks.

Legend: **[B]** built today · **[F]** future/planned · **[N]** deliberately NOT MEASURED
(must render as "Not measured" + reason, never as `0` or a guess).

---

## 1. Product in one line

**Meridian Board Operating System**, powered by the **Callosum** institutional-memory
engine. Runs a startup's board cycle end to end — *prepare → meet → decide → execute →
recall* — on a knowledge graph where every AI-proposed fact carries a machine-checked
verbatim source quote, nothing enters memory without human approval, and access control
filters content *before* retrieval.

The one question the whole product exists to answer: **"Why did we reject this?"**

---

## 2. Users & what changes per role

| Role | Sees | Primary dashboard job |
|---|---|---|
| Founder / CEO | Everything at their clearance | "What needs me before the board meeting" |
| Chief of Staff / board admin | Everything at their clearance | Completeness: pack, agenda, minutes, follow-ups |
| Director | Board-facing surfaces; no ops internals | Pre-read status, decisions, my votes |
| Observer / Adviser | Read-only, reduced clearance | Pre-read + published minutes only |
| Investor | Restricted clearance | Withheld items shown **as a count**, never as a title |

**Board directory roles [B]:** `director · observer · executive · administrator · adviser`
(a member may exist with **no login** — a non-executive director must still be recordable
and votable).

**Clearance ladder [B]:** `0 public → 1 → 2 → 3 → 4 restricted`, **fail-closed**, evaluated
per-workspace (the same person may be clearance 4 in one workspace, 1 in another).

**Withholding rule [B]:** withheld content is disclosed as *"N items withheld at your
clearance — the answer may be incomplete"*. Never silent, never titled.

---

## 3. Global shell

**Left nav (in this order — it follows the workflow, not the alphabet) [B]**
1. Dashboard
2. Prepare meeting
3. Calendar
4. Meetings
5. Decisions
6. Resolutions
7. Commitments
8. Board packs
9. Minutes
10. Documents
11. Institutional Memory
12. Review queue
13. Settings

> Chain to preserve in the design: **Decision → Resolution → Commitment** = what was
> concluded → the formal instrument recording it → the work it produced. Three separate
> objects, always traceable one to the next.

**Header [B]:** breadcrumb · workspace switcher · global search **[F]** · notifications
**[F]** · account menu.

**Assistant rail ("Ask Meridian") [B]:** collapsible right rail, persists across
navigation. Contents: suggested prompts · question box · answer · **verbatim citations**
(quote + source document) · withheld count · abstention message when nothing grounds the
question.

---

## 4. Main dashboard — `/dashboard`

Header: **Dashboard** — *"What needs you now, and whether the memory can be trusted."*
That split is the page's structure.

### 4.0 Daily brief [B]
One orientation sentence, assembled from live counts + narrative tail. Clauses with
nothing to report are **dropped, not zeroed**.
- `{n} meetings this week` (omitted if 0)
- `{n} name conflicts awaiting your review` (omitted if 0)
- narrative tail, e.g. *"Series B terms are still open ahead of the Q3 board meeting."*

---

### Band A — Operational: *what needs me now*

**A1 · Next meeting hero [B]**
- Meeting title, type, date/time, timezone, location/link
- Status chip: `draft · scheduled · in_progress · completed · cancelled`
- Days/hours until start
- Attendee avatars + count (confirmed / invited / declined **[F]**)
- Board pack state: not started / draft / **published** + pre-read sent date
- Agenda item count + total allotted minutes
- Primary CTA → **Prepare meeting**; secondary → open meeting

**A2 · Board readiness [B shell / N data]**
Four tracks, 0–100: **Agenda · Metrics · Documents · Approvals**, plus a composite.
Currently `null` — *no definition of readiness exists to compute it from*. To make it
real each track needs a stated denominator first:
- Agenda = items with a presenter + time allotment / total items
- Documents = pack items attached / agenda items requiring material
- Approvals = decisions moved out of `proposed` / decisions on the agenda
- Metrics = KPIs refreshed this period / KPIs on the standing template **[F]**

**A3 · Needs you [B]**
Action counts, each linking to its queue:
- Decisions to sign (`status = proposed`) **[N — needs a workspace-wide list endpoint]**
- Name conflicts awaiting review **[B]**
- Meetings in `draft` or `scheduled` needing prep **[B]**
- Documents to ingest **[N — ingestion is a CLI op, there is no queue]**
- **[F]** Commitments overdue · resolutions awaiting my vote · minutes awaiting finalisation · pack items unread by directors

---

### Band B — Institutional memory: *can I trust it?*

**B1 · Memory health [B]**
| Field | Today | Note |
|---|---|---|
| Verified % | **100%** | true by construction — an edge with no located quote is refused |
| Entities | **38** | seeded gold graph |
| Edges | **40** | |
| Relation types present | **14** | of the ontology's full set |
| Documents ingested | **10** | (16 files in the demo corpus) |
| Awaiting human approval | **[N]** | `proposed_change WHERE status='pending'` — no extraction run has populated it |
| Quarantined (rejected, retained) | **[N]** | `extraction_failure` table, same reason |
| Meeting status breakdown | [B] | stacked bar by `draft/scheduled/in_progress/completed/cancelled` |
| Review velocity (weekly throughput) | **[N]** | same queue as above; a weekly axis would invent time the data doesn't have |

**B2 · Graph quality [B]** — split into two tiers, and *never collapsed into one health %*.
That separation is the point of the panel.

*Verified tier (deterministic, gated, no LLM in the loop):*
- Candidate recall — **22 / 22**
- Traversal — **21 / 21**
- RBAC fail-closed — **1 / 1**

*Observed tier (LLM-dependent — reported, never gated):*
- Entity grounding — **17 / 21** (Grounding Error Rate 19% is the inverse of this, not a second measurement)
- Grounding precision — **1 / 2** (abstain-when-nothing-matches; the known open weakness)

*Ablation:* grounding **off = 38%** → **on = 100%**.
*Provenance line:* run `2026-07-20`, from `eval/mechanism.csv`, `eval/results.md`.

> Show fractions, not just percentages — "17 / 21" exposes how small the denominator is.

**B3 · Memory growth [B]**
Cumulative unique entities + edges, **x-axis = ingestion order, not time** (the data has
no timestamps). The curve flattening where a document mostly repeats known entities is
the honest shape of institutional memory.
`M12 (7/6) → M13 (15/16) → M14 (25/28) → Finance (27/29) → Sales (29/30) → M15 (31/34) → M16 (34/37) → Board email (35/38) → Audit email (37/39) → Comp review (38/40)`

**B4 · Recent decisions [B]** — newest 5: title · status · meeting · date · stance bar
(support / oppose / abstain). Links through to `/decisions` rather than growing unbounded.

**B5 · Approved facts — "Evidence, not summaries" [B]**
5 graph facts derived from the graph (never authored), each showing:
- Plain statement — `{source} approved|supersedes|owns {target}`
- The **verbatim located quote**
- The **source document filename** (not a prettified meeting name — that's how invented citations got in last time)
- Restricted edges excluded.

**[F] future dashboard widgets:** contradiction alerts (Finance says 12M, Sales says
11.6M) · superseded-decision alerts · commitment burndown · decision cycle time ·
director engagement (pre-read open rates) · KPI trends from connectors · quarantine
breakdown by failure reason · saved questions & scheduled digests.

---

## 5. Every other screen — what it shows

**`/prepare` — Prepare meeting [B]** · 5-stage wizard:
`Gathering → Analysis → Agenda → Board pack → Readiness`
Pulls prior decisions, unresolved commitments, current metrics into an **editable draft**.
Endpoints: readiness, agenda-suggestions, publish-preread.

**`/calendar` [B]** · month / week / day views · meeting chips by status · create + edit
meeting form · meeting detail drawer.

**`/meetings` [B]** · list + detail. Fields: title, type, scheduled_start/end, location,
status, attendees, agenda, pack, minutes, decisions. Transitions are enforced:
`draft → scheduled → in_progress → completed`, `cancelled` reachable from the early states.

**`/decisions` [B]** · statuses `proposed · approved · rejected · superseded · deferred`.
Per decision: title, rationale, meeting, owner, **stances** (who supported/opposed/abstained),
evidence documents, supersede chain, transition history.
Actions: transition · record stance · supersede.

**`/resolutions` [B]** · statuses `draft · adopted · rejected · superseded`.
Per resolution: text, meeting, **vote tally** (for / against / abstain / quorum), voter list,
transition, supersede, **bridge to commitment** (the resolution → work link).

**`/commitments` [B]** · statuses `open · in_progress · blocked · completed · cancelled`;
delivery statuses `not_dispatched · pending · delivered · failed`.
Per commitment: description, owner, due date, source decision/resolution, **update
timeline** (append-only progress notes).

**`/packs` — Board packs [B]** · statuses `draft · published`; sensitivity `public …
maximum`. Per pack: meeting, ordered items, per-item document, reorder, publish,
supersede. Locked once the meeting is `in_progress/completed/cancelled`.

**`/minutes` [B]** · statuses `draft · final`. Finalise + supersede. Only editable while
the meeting is `in_progress` or `completed`.

**`/documents` [B]** · corpus list: filename, type, ingested-at, chunk count, sensitivity,
extraction result. **[F]** upload, PDF/DOCX/PPTX, connectors, OCR, re-ingest.

**`/memory` — Institutional Memory [B]**
- **"View as" clearance toggle**: *Founder (full)* ↔ *Investor (restricted)* — the same
  graph, visibly smaller. This is the RBAC demo.
- Interactive knowledge graph (nodes + edges, click for evidence)
- Entity-type distribution bars
- Relationship-type distribution bars
- Provenance timeline
- Withheld banner with count

**`/entity-conflicts` — Review queue [B]** · candidate duplicate/alias pairs ("Raj" =
"Rajesh Kumar") with evidence, **approve / reject**. **[F]** the full approval queue for
proposed edges, confidence-sorted, bulk review, audit trail.

**`/settings` [B]** · workspace, members + roles + clearance, integrations **[F]**,
notifications **[F]**, ontology version, audit log **[F]**.

---

## 6. Data model reference (for graph/detail surfaces)

**Entity types (8):** `Person · Organization · Meeting · Decision · Document · Topic ·
ActionItem · Metric`

**Relation types:** `ATTENDED · PROPOSED · SUPPORTED · OPPOSED · APPROVED · OWNS ·
WORKS_AT · REQUESTED · ALIAS_OF · MADE_IN · ABOUT · SUPERSEDES · PRESENTED_AT ·
EVIDENCE_FOR · REPORTED_IN · DERIVED_FROM` — ontology **v3**.

**Rejection reasons (quarantine breakdown):** `quote_not_found` (the big one — fabricated
or paraphrased) · `quote_empty` · `entity_not_extracted` · `self_reference`

**Every edge carries:** source, relation, target, **verbatim quote**, character offsets,
source document, sensitivity, provenance stamp (provider / model / prompt / ontology
version), version history (append-only).

---

## 7. States every widget needs a design for

1. **Loading** — skeleton
2. **Empty** — nothing exists yet (with the action that creates the first one)
3. **Error** — stated **once at the top of the page**; cards below show `—` so the page
   degrades honestly without reading as "your workspace is empty"
4. **Not measured** — `—` plus the reason. **A count that was never counted is not a zero.**
5. **Withheld** — count + "your answer may be incomplete", never a title
6. **Stale / conflict** — optimistic concurrency: every object can reject a write as stale
7. **Locked** — object frozen because its parent meeting moved state

---

## 8. Non-negotiable content rules (these are product claims, not polish)

- No graph edge without a **located verbatim quote**. Cite the **filename**, not a pretty label.
- **AI never** approves, signs, votes, sends, or mutates memory — it drafts, proposes, summarises, routes.
- Permissions filter **before** retrieval, fail-closed, and disclose withholding.
- Verified (deterministic) and observed (LLM-dependent) metrics are **never averaged together**.
- A number on screen is traceable to a file in the repo, or it is `null`.
