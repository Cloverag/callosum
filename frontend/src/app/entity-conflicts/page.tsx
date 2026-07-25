"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { ShieldAlert, Check, X, User } from "lucide-react";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { apiClient, type EntityConflict } from "@/lib/api";

const EASE = [0.16, 1, 0.3, 1] as const;

function EntityBlock({ name, quote }: { name: string; quote: string }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-surface-elevated text-muted-foreground">
          <User className="size-4" />
        </span>
        <h3 className="truncate text-lg font-light tracking-tight text-foreground">{name}</h3>
      </div>
      <div className="rounded-lg border border-border bg-surface-sunken px-4 py-3">
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
          Source context
        </div>
        <p className="text-sm leading-relaxed text-foreground/90">&ldquo;{quote}&rdquo;</p>
      </div>
    </div>
  );
}

function ConflictCard({
  conflict,
  processing,
  disabled,
  reduce,
  onResolve,
}: {
  conflict: EntityConflict;
  processing: boolean;
  disabled: boolean;
  reduce: boolean;
  onResolve: (id: string, action: "approve" | "reject") => void;
}) {
  const pct = Math.round(conflict.similarity * 100);

  return (
    <motion.div
      layout
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.97, filter: "blur(6px)" }}
      transition={{ duration: 0.35, ease: EASE }}
    >
      <Card className={cn("group relative overflow-hidden", processing && "pointer-events-none opacity-60")}>
        {/* subtle accent sheen on hover — decorative, token-based */}
        <div
          className="pointer-events-none absolute inset-0 bg-gradient-to-br from-accent-subtle to-transparent opacity-0 transition-opacity duration-300 group-hover:opacity-100"
          aria-hidden
        />

        <div className="relative flex items-center justify-between gap-3 border-b border-border px-5 py-3">
          <div className="flex items-center gap-2">
            <Badge>{conflict.type_a}</Badge>
            <span className="text-xs text-muted-foreground">
              Detected {new Date(conflict.created_at).toLocaleDateString()}
            </span>
          </div>
          <div className="flex items-center gap-2 rounded-full border border-border bg-surface-elevated px-3 py-1">
            <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">Similarity</span>
            <span className="text-sm font-medium tabular-nums text-accent-emphasis">{pct}%</span>
          </div>
        </div>

        <div className="relative grid gap-6 px-5 py-5 md:grid-cols-2">
          <EntityBlock name={conflict.name_a} quote={conflict.quote_a} />
          <EntityBlock name={conflict.name_b} quote={conflict.quote_b} />
        </div>

        <div className="relative flex justify-end gap-2 border-t border-border px-5 py-3">
          <Button variant="ghost" disabled={disabled} onClick={() => onResolve(conflict.id, "reject")}>
            <X className="size-4" />
            Reject
          </Button>
          <Button loading={processing} disabled={disabled} onClick={() => onResolve(conflict.id, "approve")}>
            <Check className="size-4" />
            Approve merge
          </Button>
        </div>
      </Card>
    </motion.div>
  );
}

function ConflictSkeletons() {
  return (
    <div className="space-y-4">
      {[0, 1].map((i) => (
        <Card key={i} className="overflow-hidden">
          <div className="border-b border-border px-5 py-3">
            <div className="h-4 w-40 animate-pulse rounded bg-surface-sunken" />
          </div>
          <div className="grid gap-6 px-5 py-5 md:grid-cols-2">
            {[0, 1].map((j) => (
              <div key={j} className="space-y-2">
                <div className="h-6 w-32 animate-pulse rounded bg-surface-sunken" />
                <div className="h-16 w-full animate-pulse rounded bg-surface-sunken" />
              </div>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <Card>
      <div className="flex flex-col items-center justify-center gap-3 px-6 py-16 text-center">
        <span className="flex size-12 items-center justify-center rounded-full border border-border bg-surface-elevated text-success-emphasis">
          <Check className="size-6" />
        </span>
        <div>
          <h3 className="text-sm font-medium text-foreground">No conflicts pending review</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            New potential duplicate entities appear here as documents are ingested.
          </p>
        </div>
      </div>
    </Card>
  );
}

export default function EntityConflictsPage() {
  const [conflicts, setConflicts] = useState<EntityConflict[] | null>(null);
  const [processingId, setProcessingId] = useState<string | null>(null);
  const reduce = useReducedMotion() ?? false;

  useEffect(() => {
    apiClient
      .getPendingConflicts()
      .then(setConflicts)
      .catch(() => setConflicts([]));
  }, []);

  async function resolve(id: string, action: "approve" | "reject") {
    setProcessingId(id);
    try {
      if (action === "approve") await apiClient.approveConflict(id);
      else await apiClient.rejectConflict(id);
      setConflicts((prev) => (prev ?? []).filter((c) => c.id !== id));
    } finally {
      setProcessingId(null);
    }
  }

  return (
    <div className="relative p-6">
      {/* soft violet wash at the top — the requested gradient, kept subtle */}
      <div
        className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-48 bg-gradient-to-b from-accent-subtle to-transparent"
        aria-hidden
      />

      <PageHeader
        icon={<ShieldAlert />}
        title="Entity Conflicts"
        description="Review potential duplicate entities detected across the workspace memory graph."
      />

      <div className="mt-6">
        {conflicts === null ? (
          <ConflictSkeletons />
        ) : conflicts.length === 0 ? (
          <EmptyState />
        ) : (
          <motion.div layout className="space-y-4">
            <AnimatePresence mode="popLayout">
              {conflicts.map((c) => (
                <ConflictCard
                  key={c.id}
                  conflict={c}
                  processing={processingId === c.id}
                  disabled={!!processingId}
                  reduce={reduce}
                  onResolve={resolve}
                />
              ))}
            </AnimatePresence>
          </motion.div>
        )}
      </div>
    </div>
  );
}
