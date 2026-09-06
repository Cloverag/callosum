import dagre from "@dagrejs/dagre";

import type { GraphEdgeData, GraphNodeData } from "@/lib/graph";

/**
 * A layered layout, as the counterpart to the force simulation.
 *
 * ---------------------------------------------------------------------------
 * WHY BOTH
 * ---------------------------------------------------------------------------
 * The two answer different questions and neither is a better version of the
 * other.
 *
 *   FORCE     "what clusters?"  — which entities pull together, which hub
 *                                 everything hangs off, where the dense
 *                                 neighbourhoods are. Position means nothing in
 *                                 particular; proximity means a lot.
 *
 *   HIERARCHY "what follows from what?" — this graph is directed and the
 *                                 direction is semantic: a Person APPROVED a
 *                                 Decision, a Decision was MADE_IN a Meeting, an
 *                                 ActionItem is DERIVED_FROM a Decision, a
 *                                 Decision SUPERSEDES another. Layering by edge
 *                                 direction puts causes above consequences, and
 *                                 SUPERSEDES becomes a visible chain rather than
 *                                 one line among forty.
 *
 * Dagre is used rather than a tree layout because this is a DAG-ish graph, not a
 * tree: nodes have several parents (a Decision is approved by three people), and
 * `ALIAS_OF` produces Person→Person edges that no tree layout could place.
 * Cycles, if the ontology ever grows one, are broken by dagre internally instead
 * of hanging.
 */

/**
 * Node box, in pixels. `MemoryNode` is capped at `maxWidth: 168` and runs to two
 * lines for the longer labels. Dagre reserves space from these numbers alone —
 * it never measures the DOM — so understating them packs ranks tightly enough
 * that boxes overlap while the layout reports itself valid.
 */
const NODE_W = 172;
const NODE_H = 56;

export type Positions = Map<string, { x: number; y: number }>;

export function hierarchyLayout(
  nodes: GraphNodeData[],
  edges: GraphEdgeData[]
): Positions {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({
    // Left-to-right, and it is the better direction on both counts. Measured over
    // this graph at 172x56 boxes in a ~1500x760 pane:
    //
    //   TB  3087 x  568   5 ranks   fits at 0.49
    //   LR  1148 x 1202  28 ranks   fits at 0.63
    //
    // Top-down collapses the graph into five very wide bands — the widest holds 11
    // Persons — so it reads as five rows rather than a chain, and the sheet is so
    // wide that fitView drops near React Flow's 0.3 minZoom where labels stop being
    // legible. Left-to-right recovers the actual depth AND fits larger. It also
    // matches the direction the relationships read in: Raj APPROVED a decision
    // MADE_IN a meeting.
    rankdir: "LR",
    ranksep: 96,
    nodesep: 22,
    edgesep: 12,
    marginx: 40,
    marginy: 40,
  });

  for (const n of nodes) g.setNode(n.id, { width: NODE_W, height: NODE_H });

  // Only edges whose endpoints both survive the current view. Clearance
  // filtering can legitimately remove one end, and dagre would silently invent a
  // node for the missing id, leaving a blank box in the picture.
  const present = new Set(nodes.map((n) => n.id));
  for (const e of edges) {
    if (present.has(e.source) && present.has(e.target)) g.setEdge(e.source, e.target);
  }

  dagre.layout(g);

  // Dagre returns centres; React Flow positions from the top-left corner.
  const out: Positions = new Map();
  for (const n of nodes) {
    const laid = g.node(n.id) as { x: number; y: number } | undefined;
    if (laid) out.set(n.id, { x: laid.x - NODE_W / 2, y: laid.y - NODE_H / 2 });
  }
  return out;
}
