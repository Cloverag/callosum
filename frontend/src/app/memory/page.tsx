"use client";

import { useEffect, useState } from "react";
import { Network } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { graphApi, NODE_TYPE_LABEL, type GraphView } from "@/lib/graph";
import { entityTypeDistribution, relationTypeDistribution } from "@/lib/graph-stats";
import { KnowledgeGraph, EvidencePanel, type GraphFocus } from "./knowledge-graph";
import { ProvenanceTimeline } from "./provenance-timeline";
import { OntologyBars } from "./ontology-bars";

/**
 * Institutional Memory — the verified knowledge graph itself.
 *
 * Every other surface in the product reports *about* the graph. This one is the
 * graph, and it is the strongest thing the project has to show: 38 entities and
 * 40 relationships, each carrying the verbatim quote it was extracted from.
 *
 * The clearance switch is not a demo toy. It exercises the same rule the backend
 * enforces in SQL and in Cypher: an investor asking about compensation is not
 * shown the node and is *told* something was withheld, as a count and never as a
 * title. Silent withholding would be the failure this project exists to prevent.
 */
export default function MemoryPage() {
  const [view, setView] = useState<GraphView | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [focus, setFocus] = useState<GraphFocus | null>(null);
  const [asFounder, setAsFounder] = useState(true);

  useEffect(() => {
    let live = true;
    graphApi.get(asFounder).then((v) => {
      if (!live) return;
      setView(v);
      // Drop a selection that this clearance can no longer see.
      setSelected((s) => (s && v.nodes.some((n) => n.id === s) ? s : null));
      // A filter whose subject this clearance can no longer see is dropped, so
      // the page never shows an active filter matching nothing.
      setFocus((f) => {
        if (!f) return null;
        const stillThere =
          f.kind === "document"
            ? v.nodes.some((n) => n.document === f.value) ||
              v.edges.some((e) => e.document === f.value)
            : f.kind === "entityType"
              ? v.nodes.some((n) => n.type === f.value)
              : v.edges.some((e) => e.relation === f.value);
        return stillThere ? f : null;
      });
    });
    return () => {
      live = false;
    };
  }, [asFounder]);

  /** Selecting a node answers a more specific question than any filter, so it
   *  clears the filter rather than compounding with it. */
  const selectNode = (id: string | null) => {
    setSelected(id);
    if (id) setFocus(null);
  };

  /** Applying a filter is a different question from the open node, so it drops
   *  the selection. Only one thing narrows the canvas at a time. */
  const applyFocus = (next: GraphFocus | null) => {
    setFocus(next);
    setSelected(null);
  };

  const entityTypes = view ? entityTypeDistribution(view) : [];
  const relationTypes = view ? relationTypeDistribution(view) : [];

  const withheld = (view?.withheldNodes ?? 0) + (view?.withheldEdges ?? 0);

  return (
    <div className="p-8">
      <PageHeader
        title="Institutional Memory"
        description="Every relationship carries the quote it came from. No quote, no edge."
        icon={<Network />}
        actions={
          <div
            className="inline-flex items-center rounded-[12px] border border-border bg-surface-raised p-0.5"
            role="group"
            aria-label="View the graph as"
          >
            {[
              { key: true, label: "Founder", hint: "Full clearance" },
              { key: false, label: "Investor", hint: "Restricted clearance" },
            ].map((opt) => (
              <button
                key={String(opt.key)}
                type="button"
                onClick={() => setAsFounder(opt.key)}
                aria-pressed={asFounder === opt.key}
                title={opt.hint}
                className={cn(
                  "rounded-[10px] px-3 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised",
                  asFounder === opt.key
                    ? "bg-accent-subtle font-medium text-accent-emphasis"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                View as {opt.label}
              </button>
            ))}
          </div>
        }
      />

      <div className="mt-4 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
        {view ? (
          <>
            <span>
              <span className="tabular-nums text-foreground">{view.nodes.length}</span> entities
            </span>
            <span aria-hidden className="text-border-strong">·</span>
            <span>
              <span className="tabular-nums text-foreground">{view.edges.length}</span> relationships
            </span>
            {withheld > 0 && (
              <Badge tone="warning">
                {view.withheldNodes} entit{view.withheldNodes === 1 ? "y" : "ies"} and{" "}
                {view.withheldEdges} relationship
                {view.withheldEdges === 1 ? "" : "s"} withheld
              </Badge>
            )}
          </>
        ) : (
          <span className="text-subtle-foreground">Reading the graph…</span>
        )}
      </div>

      {withheld > 0 && (
        <p className="mt-2 max-w-[62ch] text-xs text-subtle-foreground">
          Withheld content is disclosed as a count, never as a title — this caller's
          clearance is below the source's sensitivity, so the rows are filtered before
          retrieval rather than hidden afterwards.
        </p>
      )}

      {/* Stacked, not side-by-side. The shell already spends 248px on the sidebar
          and 368px on the AI rail, so a two-column split left the canvas about
          215px wide — unreadable for 38 nodes. Tailwind's breakpoints measure the
          viewport, not this container, so the split looked fine at `lg:` and was
          broken in practice. Full width for the graph; evidence below it. */}
      <div className="mt-5 flex flex-col gap-5">
        <div className="h-[30rem] overflow-hidden rounded-[16px] border border-border bg-surface-raised shadow-card">
          {view ? (
            <KnowledgeGraph
              view={view}
              selected={selected}
              onSelect={selectNode}
              focus={focus}
            />
          ) : (
            <div className="h-full w-full animate-pulse bg-surface-sunken" />
          )}
        </div>

        <div className="grid gap-5 xl:grid-cols-2">
          <aside className="max-h-[26rem] min-h-[10rem] overflow-hidden rounded-[16px] border border-border bg-surface-raised shadow-card">
            {view && <EvidencePanel view={view} selected={selected} />}
          </aside>

          <div className="max-h-[26rem] overflow-y-auto rounded-[16px] border border-border bg-surface-raised px-4 py-4 shadow-card">
            {view && (
              <ProvenanceTimeline
                view={view}
                activeDocument={focus?.kind === "document" ? focus.value : null}
                onSelectDocument={(d) =>
                  applyFocus(d ? { kind: "document", value: d } : null)
                }
                onSelectNode={selectNode}
              />
            )}
          </div>
        </div>

        {/* What the graph is made of. Two distributions, one component — the
            same comparison in both cases, so the same form. */}
        {view && (
          <div className="grid gap-5 xl:grid-cols-2">
            <div className="rounded-[16px] border border-border bg-surface-raised px-4 py-4 shadow-card">
              <OntologyBars
                title="Entity types"
                caption="What the ontology allows to exist, and how much of each the corpus actually produced."
                items={entityTypes}
                activeKey={focus?.kind === "entityType" ? focus.value : null}
                onSelect={(k) => applyFocus(k ? { kind: "entityType", value: k } : null)}
              />
            </div>
            <div className="rounded-[16px] border border-border bg-surface-raised px-4 py-4 shadow-card">
              <OntologyBars
                title="Relationship types"
                caption="How entities connect. ALIAS_OF is identity resolution; SUPERSEDES is a decision reversing an earlier one."
                items={relationTypes}
                activeKey={focus?.kind === "relation" ? focus.value : null}
                onSelect={(k) => applyFocus(k ? { kind: "relation", value: k } : null)}
              />
            </div>
          </div>
        )}
      </div>

      {/* A canvas is not reachable without a pointer and sight. The same graph,
          as text, so the evidence is available to everyone. */}
      {view && (
        <details className="mt-4">
          <summary className="cursor-pointer text-xs text-muted-foreground underline decoration-dotted underline-offset-4 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface">
            View the graph as a list
          </summary>
          <div className="mt-3 overflow-x-auto rounded-[12px] border border-border bg-surface-raised">
            <table className="w-full min-w-[44rem] text-sm">
              <caption className="sr-only">
                Every relationship in institutional memory, with its source quote
              </caption>
              <thead>
                <tr className="text-left text-xs uppercase tracking-[0.06em] text-subtle-foreground">
                  <th scope="col" className="px-4 py-2 font-semibold">From</th>
                  <th scope="col" className="px-4 py-2 font-semibold">Relation</th>
                  <th scope="col" className="px-4 py-2 font-semibold">To</th>
                  <th scope="col" className="px-4 py-2 font-semibold">Evidence</th>
                </tr>
              </thead>
              <tbody>
                {view.edges.map((e) => (
                  <tr key={e.id} className="border-t border-border align-top">
                    <td className="px-4 py-2 text-foreground">{e.source}</td>
                    <td className="px-4 py-2 font-mono text-[11px] uppercase text-accent-emphasis">
                      {e.relation}
                    </td>
                    <td className="px-4 py-2 text-foreground">{e.target}</td>
                    <td className="px-4 py-2 italic text-muted-foreground">“{e.quote}”</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-subtle-foreground">
            Entity types present:{" "}
            {[...new Set(view.nodes.map((n) => NODE_TYPE_LABEL[n.type]))].join(" · ")}
          </p>
        </details>
      )}
    </div>
  );
}
