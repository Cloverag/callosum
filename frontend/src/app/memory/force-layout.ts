"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";

import type { GraphEdgeData, GraphNodeData } from "@/lib/graph";

/**
 * A live force layout for the knowledge graph.
 *
 * ---------------------------------------------------------------------------
 * WHY THIS EXISTS
 * ---------------------------------------------------------------------------
 * Positions used to be baked into `lib/graph.ts` — "computed offline, seed 7, so
 * the picture is stable across loads and needs no layout library." Stable, but
 * the layout that got frozen had collapsed: of 34 nodes, **6 sat at exactly
 * y = 660.0** and **6 at exactly x = 0.0**. A fifth of the graph was on a
 * straight line or flat against the left edge, which is why it read as a diagram
 * that had failed rather than a graph.
 *
 * The picture was also not draggable, for a second and independent reason: the
 * `nodes` array was a `useMemo` over that constant with no `onNodesChange`
 * handler. React Flow v12 is controlled, so a drag was computed and then thrown
 * away on the next render. It looked interactive and was not.
 *
 * ---------------------------------------------------------------------------
 * WHAT THIS DOES
 * ---------------------------------------------------------------------------
 * The same simulation Obsidian's graph view uses: nodes repel, edges pull like
 * springs, the whole thing settles, and dragging re-heats it so the neighbourhood
 * rearranges around your hand. Positions are computed in the browser from the
 * graph's own topology, so they can never disagree with the data — a baked
 * coordinate silently survives an edge being added or removed.
 *
 * Released on drop rather than pinned, which is Obsidian's behaviour: a node you
 * let go of floats back into the layout instead of leaving a hole where the
 * forces still act but the node no longer moves.
 */

type SimNode = SimulationNodeDatum & { id: string; degree: number };
type SimLink = SimulationLinkDatum<SimNode>;

export type Positioned = { x: number; y: number };

/**
 * Tuned for ~34 nodes in a ~1200x800 pane, not for graphs in general.
 *
 * COLLIDE is the one that matters visually. These nodes are DOM boxes up to
 * 168px wide, not the dots d3's defaults assume, so a radius near the default 1
 * lets labelled boxes sit on top of each other while the simulation reports
 * itself perfectly settled.
 */
const CHARGE = -620;
const LINK_DISTANCE = 104;
const COLLIDE_RADIUS = 74;
/** Gentle pull to origin so disconnected components cannot drift off-screen. */
const GRAVITY = 0.11;

export function useForceLayout(
  nodes: GraphNodeData[],
  edges: GraphEdgeData[],
  /**
   * Fired once, when the layout first comes to rest.
   *
   * `fitView` on mount is computed against the seed ring, which is a fraction of
   * the settled graph's extent — so the picture opens zoomed far in on two or
   * three nodes and never re-fits. Callers use this to frame it once the size is
   * known. Deliberately once: re-fitting after every drag would yank the viewport
   * out from under the hand that moved a node.
   */
  onFirstSettle?: () => void,
  /** When false the simulation is not created at all — the hierarchy layout owns
   *  positions and a running sim would be invisible work on every frame. */
  enabled = true
) {
  const simRef = useRef<Simulation<SimNode, SimLink> | null>(null);
  const byId = useRef<Map<string, SimNode>>(new Map());
  // Ticks mutate the simulation's own node objects in place; this counter is the
  // only thing React needs in order to re-read them. Copying 34 positions into
  // state on every one of ~300 ticks would be pure garbage.
  const [tick, setTick] = useState(0);
  // Held in a ref so a caller passing an inline arrow does not restart the
  // simulation on every render.
  const settleCb = useRef(onFirstSettle);
  settleCb.current = onFirstSettle;
  const hasSettled = useRef(false);

  useEffect(() => {
    if (!enabled || nodes.length === 0) return;
    // Reset per simulation, not per mount: switching back from the layered layout
    // rebuilds the sim from the seed ring, and without this the viewport keeps the
    // zoom dagre needed and opens on a handful of nodes.
    hasSettled.current = false;

    // Seed on a ring rather than at the origin. d3 seeds in a phyllotaxis spiral
    // when x/y are undefined, which is fine, but an explicit deterministic ring
    // means the first painted frame is already legible instead of a single blob
    // that explodes outward.
    const radius = 60 + nodes.length * 9;
    const simNodes: SimNode[] = nodes.map((n, i) => {
      const angle = (i / nodes.length) * Math.PI * 2;
      return {
        id: n.id,
        degree: n.degree,
        x: Math.cos(angle) * radius,
        y: Math.sin(angle) * radius,
      };
    });

    const index = new Map(simNodes.map((n) => [n.id, n]));
    byId.current = index;

    // An edge naming a node the current view filtered out would throw inside
    // forceLink. Clearance filtering can legitimately produce exactly that, so
    // drop such edges instead of letting the layout crash the page.
    const simLinks: SimLink[] = edges
      .filter((e) => index.has(e.source) && index.has(e.target))
      .map((e) => ({ source: index.get(e.source)!, target: index.get(e.target)! }));

    const sim = forceSimulation(simNodes)
      .force("charge", forceManyBody().strength(CHARGE).distanceMax(700))
      .force(
        "link",
        forceLink<SimNode, SimLink>(simLinks)
          .id((d) => d.id)
          // Hubs get longer edges so their spokes have room to fan out instead
          // of crushing together around a high-degree node.
          .distance((l) => {
            const s = l.source as SimNode;
            const t = l.target as SimNode;
            return LINK_DISTANCE + Math.min(s.degree, t.degree) * 4;
          })
          .strength(0.32)
      )
      .force("collide", forceCollide<SimNode>().radius(COLLIDE_RADIUS).strength(0.9))
      .force("center", forceCenter(0, 0))
      .force("x", forceX(0).strength(GRAVITY))
      .force("y", forceY(0).strength(GRAVITY))
      .alpha(1)
      .alphaDecay(0.022)
      .on("tick", () => setTick((t) => t + 1))
      .on("end", () => {
        if (hasSettled.current) return;
        hasSettled.current = true;
        settleCb.current?.();
      });

    simRef.current = sim;
    return () => {
      sim.stop();
      simRef.current = null;
    };
  }, [nodes, edges, enabled]);

  const positionOf = useCallback((id: string): Positioned => {
    const n = byId.current.get(id);
    return { x: n?.x ?? 0, y: n?.y ?? 0 };
  }, []);

  /** Pin under the cursor and keep the simulation warm while dragging. */
  const onDragStart = useCallback((id: string) => {
    const n = byId.current.get(id);
    if (!n) return;
    simRef.current?.alphaTarget(0.3).restart();
    n.fx = n.x;
    n.fy = n.y;
  }, []);

  const onDrag = useCallback((id: string, p: Positioned) => {
    const n = byId.current.get(id);
    if (!n) return;
    n.fx = p.x;
    n.fy = p.y;
  }, []);

  const onDragStop = useCallback((id: string) => {
    const n = byId.current.get(id);
    if (!n) return;
    simRef.current?.alphaTarget(0);
    n.fx = null;
    n.fy = null;
  }, []);

  /** Re-heat from the UI — the equivalent of Obsidian's graph settling again. */
  const reheat = useCallback(() => {
    simRef.current?.alpha(0.9).restart();
  }, []);

  // `tick` is returned so callers can depend on it. Without that the consuming
  // `useMemo` keeps its first result — every node at (0, 0) — while the
  // simulation runs correctly and invisibly underneath. Nothing renders wrong;
  // nothing renders at all.
  return useMemo(
    () => ({ tick, positionOf, onDragStart, onDrag, onDragStop, reheat }),
    [tick, positionOf, onDragStart, onDrag, onDragStop, reheat]
  );
}
