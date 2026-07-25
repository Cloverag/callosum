// What the graph is made of — entity types and relation types, counted.
//
// Derived from `graph.ts` (which is generated), so these never need maintaining
// and cannot disagree with the graph they describe.

import { NODE_TYPE_LABEL, type GraphView } from "./graph";

export type Distribution = {
  /** Stable key used to filter the graph. */
  key: string;
  label: string;
  count: number;
  /** Plain-English gloss. Half of these are ontology jargon to a board member. */
  hint?: string;
};

const ENTITY_HINT: Record<string, string> = {
  Person: "Anyone named in a source — directors, executives, investors.",
  Decision: "Something the board resolved, with the discussion that produced it.",
  Meeting: "A sitting the sources record.",
  Topic: "A subject decisions and discussion attach to.",
  ActionItem: "Work someone committed to, and who owns it.",
  Metric: "A reported figure, kept with the source that reported it.",
  Document: "A source in its own right — a deck, a forecast, a memo.",
  Organization: "An external party: a fund, a customer, a vendor.",
};

const RELATION_HINT: Record<string, string> = {
  APPROVED: "This person carried the decision.",
  OPPOSED: "This person argued against it — preserved, not smoothed away.",
  SUPPORTED: "This person backed it without being the one to decide.",
  REQUESTED: "A customer or party asked for it, so the decision has an origin.",
  SUPERSEDES: "A later decision replaced an earlier one. The reversal is kept.",
  ALIAS_OF: "Two names, one person — resolved only after human review.",
  MADE_IN: "The meeting a decision was taken in.",
  ABOUT: "What a decision concerns.",
  OWNS: "Who is accountable for an action item.",
  ATTENDED: "Who was present.",
  REPORTED_IN: "Where a figure was stated.",
  DERIVED_FROM: "What a claim was computed or drawn from.",
  PRESENTED_AT: "Where a document was tabled.",
  WORKS_AT: "Employment or affiliation.",
};

/** Entity types, largest first. */
export function entityTypeDistribution(view: GraphView): Distribution[] {
  const counts = new Map<string, number>();
  for (const n of view.nodes) counts.set(n.type, (counts.get(n.type) ?? 0) + 1);
  return [...counts.entries()]
    .map(([key, count]) => ({
      key,
      label: NODE_TYPE_LABEL[key as keyof typeof NODE_TYPE_LABEL] ?? key,
      count,
      hint: ENTITY_HINT[key],
    }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}

/**
 * Relation types, largest first.
 *
 * Sorted by count rather than grouped by meaning: the shape of the ontology's
 * ACTUAL use is the finding. `ALIAS_OF` at 4 and `SUPERSEDES` at 1 say the
 * corpus exercises identity resolution heavily and temporal reversal exactly
 * once — which is what a capability matrix is supposed to look like.
 */
export function relationTypeDistribution(view: GraphView): Distribution[] {
  const counts = new Map<string, number>();
  for (const e of view.edges) counts.set(e.relation, (counts.get(e.relation) ?? 0) + 1);
  return [...counts.entries()]
    .map(([key, count]) => ({ key, label: key, count, hint: RELATION_HINT[key] }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}
