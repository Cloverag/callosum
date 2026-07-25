"use client";

import { useCallback, useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import {
  NODE_TYPE_LABEL,
  type GraphEdgeData,
  type GraphNodeData,
  type GraphView,
} from "@/lib/graph";

/**
 * The verified knowledge graph, drawn.
 *
 * COLOUR. Eight ontology types cannot each take a hue — past ~7 classes adjacent
 * colours blur, and the doctrine reserves violet for memory and blue for action.
 * So type is carried by a LABEL, not a colour, and colour is spent on the two
 * things that are genuinely about state: violet marks a Decision (what a board
 * actually looks for), blue marks selection — which the doctrine already lists
 * as an action use. Everything else is neutral, and unrelated nodes dim rather
 * than recolour, so identity never moves.
 *
 * SIZE encodes degree, so hubs read before labels are legible.
 */

type NodePayload = { node: GraphNodeData; state: "normal" | "focus" | "dim" } & Record<
  string,
  unknown
>;

function MemoryNode({ data }: NodeProps<Node<NodePayload>>) {
  const { node, state } = data;
  const isDecision = node.type === "Decision";
  // 11px .. 15px by degree — a hub is visibly a hub.
  const size = Math.min(15, 11 + node.degree * 0.5);

  return (
    <div
      className={cn(
        "group rounded-[10px] border bg-surface-raised px-2.5 py-1.5 text-center shadow-card transition-opacity",
        state === "dim" ? "opacity-25" : "opacity-100",
        state === "focus"
          ? "border-accent ring-2 ring-accent-border"
          : isDecision
            ? "border-memory-emphasis/45 bg-memory-subtle"
            : "border-border"
      )}
      style={{ maxWidth: 168 }}
    >
      {/* Both handles sit at the node's centre and are invisible, so edges are
          drawn centre-to-centre like a proper node-link diagram. */}
      <Handle
        type="target"
        position={Position.Top}
        style={{ left: "50%", top: "50%", opacity: 0, pointerEvents: "none" }}
      />
      <Handle
        type="source"
        position={Position.Top}
        style={{ left: "50%", top: "50%", opacity: 0, pointerEvents: "none" }}
      />
      <div
        className={cn(
          "font-medium leading-tight",
          isDecision ? "text-memory-emphasis" : "text-foreground"
        )}
        style={{ fontSize: size }}
      >
        {node.label}
      </div>
      <div className="mt-0.5 text-[10px] uppercase tracking-[0.06em] text-subtle-foreground">
        {NODE_TYPE_LABEL[node.type]}
      </div>
    </div>
  );
}

const nodeTypes = { memory: MemoryNode };

export function KnowledgeGraph({
  view,
  onSelect,
  selected,
  focusDocument = null,
}: {
  view: GraphView;
  onSelect: (id: string | null) => void;
  selected: string | null;
  /** When set, everything this document did not contribute recedes. */
  focusDocument?: string | null;
}) {
  /**
   * Two ways to narrow the picture, and a node selection always wins — it is the
   * more specific gesture, so clicking a node while a document filter is active
   * answers the question the click asked rather than the filter's.
   */
  const neighbours = useMemo(() => {
    if (selected) {
      const set = new Set<string>([selected]);
      for (const e of view.edges) {
        if (e.source === selected) set.add(e.target);
        if (e.target === selected) set.add(e.source);
      }
      return set;
    }
    if (focusDocument) {
      const set = new Set<string>();
      for (const n of view.nodes) if (n.document === focusDocument) set.add(n.id);
      // An edge extracted from this document also lights the entities it joins,
      // even when those entities were first introduced elsewhere — otherwise a
      // relationship would appear to connect nothing.
      for (const e of view.edges) {
        if (e.document === focusDocument) {
          set.add(e.source);
          set.add(e.target);
        }
      }
      return set;
    }
    return null;
  }, [selected, focusDocument, view.edges, view.nodes]);

  const nodes: Node<NodePayload>[] = useMemo(
    () =>
      view.nodes.map((n) => ({
        id: n.id,
        type: "memory",
        position: { x: n.x, y: n.y },
        data: {
          node: n,
          state: !neighbours ? "normal" : neighbours.has(n.id) ? "focus" : "dim",
        } as NodePayload,
      })),
    [view.nodes, neighbours]
  );

  const edges: Edge[] = useMemo(
    () =>
      view.edges.map((e) => {
        const fromDoc = focusDocument !== null && e.document === focusDocument;
        const lit = focusDocument !== null && !selected
          ? fromDoc
          : !neighbours || (neighbours.has(e.source) && neighbours.has(e.target));
        const onPath =
          selected !== null ? e.source === selected || e.target === selected : fromDoc;
        return {
          id: e.id,
          source: e.source,
          target: e.target,
          type: "straight",
          label: onPath ? e.relation : undefined,
          labelShowBg: true,
          labelBgPadding: [4, 2] as [number, number],
          labelBgStyle: { fill: "var(--surface-raised)" },
          labelStyle: {
            fill: "var(--muted-foreground)",
            fontSize: 10,
            letterSpacing: "0.04em",
          },
          style: {
            stroke: onPath ? "var(--accent)" : "var(--border-strong)",
            strokeWidth: onPath ? 1.75 : 1,
            opacity: lit ? 1 : 0.15,
          },
        };
      }),
    [view.edges, neighbours, selected, focusDocument]
  );

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => onSelect(node.id),
    [onSelect]
  );

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={handleNodeClick}
        onPaneClick={() => onSelect(null)}
        fitView
        fitViewOptions={{ padding: 0.16 }}
        minZoom={0.3}
        maxZoom={2}
        proOptions={{ hideAttribution: false }}
        nodesConnectable={false}
        edgesFocusable={false}
        className="[&_.react-flow\_\_pane]:cursor-grab"
      >
        <Background gap={22} size={1} color="var(--border)" />
        <Controls showInteractive={false} className="!shadow-card" />
      </ReactFlow>
    </div>
  );
}

/**
 * Evidence for the selected node. This is the thesis made operable: every edge
 * shows the verbatim quote that was located in the source, because an edge that
 * could not produce one does not exist in the graph at all.
 */
export function EvidencePanel({
  view,
  selected,
}: {
  view: GraphView;
  selected: string | null;
}) {
  const node = view.nodes.find((n) => n.id === selected) ?? null;
  const edges = useMemo(
    () =>
      selected
        ? view.edges.filter((e) => e.source === selected || e.target === selected)
        : [],
    [view.edges, selected]
  );

  if (!node) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
        <p className="text-sm text-muted-foreground">Select a node</p>
        <p className="max-w-[22rem] text-xs text-subtle-foreground">
          Every relationship carries the verbatim quote it was extracted from. Choose
          an entity to read its evidence.
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="border-b border-border px-5 py-4">
        <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-subtle-foreground">
          {NODE_TYPE_LABEL[node.type]}
        </div>
        <h3 className="mt-1 text-base font-semibold text-foreground">{node.label}</h3>
        {(node.role || node.detail) && (
          <p className="mt-1 text-sm text-muted-foreground">
            {[node.role, node.detail].filter(Boolean).join(" · ")}
          </p>
        )}
        <p className="mt-2 text-xs text-subtle-foreground">
          Extracted from <span className="text-muted-foreground">{node.document}</span>
        </p>
      </div>

      <div className="px-5 py-4">
        <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-subtle-foreground">
          {edges.length} relationship{edges.length === 1 ? "" : "s"}
        </div>

        <ul className="mt-3 flex flex-col gap-3">
          {edges.map((e) => (
            <EvidenceItem key={e.id} edge={e} from={node.id} />
          ))}
        </ul>
      </div>
    </div>
  );
}

function EvidenceItem({ edge, from }: { edge: GraphEdgeData; from: string }) {
  const outgoing = edge.source === from;
  const other = outgoing ? edge.target : edge.source;

  return (
    <li className="rounded-[12px] border border-border bg-surface-raised p-3">
      <div className="flex flex-wrap items-baseline gap-x-1.5 gap-y-1 text-sm">
        <span className="font-mono text-[11px] uppercase tracking-[0.05em] text-accent-emphasis">
          {edge.relation}
        </span>
        <span className="text-subtle-foreground">{outgoing ? "→" : "←"}</span>
        <span className="font-medium text-foreground">{other}</span>
      </div>

      {edge.quote && (
        <blockquote className="mt-2 rounded-[8px] bg-surface-sunken px-3 py-2 text-xs italic text-muted-foreground">
          “{edge.quote}”
        </blockquote>
      )}

      <div className="mt-2 flex items-center justify-between gap-2">
        <span className="truncate text-[11px] text-subtle-foreground">{edge.document}</span>
        <Badge tone="success">Verified</Badge>
      </div>
    </li>
  );
}
