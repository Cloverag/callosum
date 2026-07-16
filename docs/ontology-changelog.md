# Ontology changelog

The ontology (`src/callosum/ontology.py`) is versioned. `ONTOLOGY_VERSION` is stamped on
every proposed edge and every quarantined failure, so any result can be attributed to the
ontology that produced it — and so "recall rose from 89% to 93% under v2" is a claim you
can actually make. Changes are evidence-driven: a type is added only when the corpus
produces a relationship that cannot be represented without losing semantics, never because
it "seems useful."

## v2 — 2026-10-14

**Added:** `REQUESTED`

**Definition:** an actor (person, organization, customer, regulator, …) formally requested
a proposal, action, topic, or decision. Deliberately general — it carries
`Customer —REQUESTED→ Pricing Model`, `CEO —REQUESTED→ Budget Review`, and
`Board —REQUESTED→ Security Audit` equally.

**Reason:** Board Meeting 13 introduced a customer-driven decision — Northwind, the largest
account, formally asked to move to usage-based pricing, and that request materially drove
the board's reversal. No existing relation could carry it without distortion: `SUPPORTED`
would wrongly equate a customer's commercial request with a director's vote; `ABOUT` or a
bare mention would drop the causal role entirely. The corpus produced a relationship the
ontology could not represent — the definition of an evidence-based change.

**Backwards compatibility:** fully compatible. `REQUESTED` is additive; every v1 edge and
extraction remains valid. Re-running extraction under v2 can only add edges of the new
type, never invalidate existing ones.

## v1 — 2026-07-12 (initial)

Entity types: Person, Organization, Meeting, Decision, Document, Topic, ActionItem, Metric.
Relation types: ATTENDED, PROPOSED, SUPPORTED, OPPOSED, APPROVED, OWNS, WORKS_AT, MADE_IN,
ABOUT, SUPERSEDES, PRESENTED_AT, EVIDENCE_FOR, REPORTED_IN, DERIVED_FROM. Every type traces
to a requirement in the PRD / high-value use-cases (see `reference/`).
