"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import { FileSignature, GitMerge, CalendarClock, FileUp, ChevronRight, Check } from "lucide-react";
import { Card } from "@/components/ui/card";

export type ActionCounts = {
  decisions: number;
  conflicts: number;
  meetings: number;
  docs: number;
};

// Ordered by urgency — actionability decreases as you move down.
const ROWS: { key: keyof ActionCounts; label: string; href: string; icon: ReactNode }[] = [
  { key: "decisions", label: "Approve decisions", href: "/meetings", icon: <FileSignature /> },
  { key: "conflicts", label: "Review conflicts", href: "/entity-conflicts", icon: <GitMerge /> },
  { key: "meetings", label: "Prepare meetings", href: "/calendar", icon: <CalendarClock /> },
  { key: "docs", label: "Ingest documents", href: "/documents", icon: <FileUp /> },
];

export function NeedsYou({ counts }: { counts: ActionCounts | null }) {
  const reduce = useReducedMotion();
  const loading = counts === null;
  const total = counts ? counts.decisions + counts.conflicts + counts.meetings + counts.docs : 0;

  return (
    <Card className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-border px-5 py-3">
        <h2 className="text-sm font-medium text-foreground">Needs you</h2>
      </div>

      {loading ? (
        <div className="space-y-1 p-2.5">
          {ROWS.map((r) => (
            <div key={r.key} className="flex items-center gap-3 px-3 py-2.5">
              <div className="size-4 rounded bg-surface-raised" />
              <div className="h-3.5 flex-1 rounded bg-surface-raised" />
              <div className="size-5 rounded-full bg-surface-raised" />
            </div>
          ))}
        </div>
      ) : total === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center px-5 py-10 text-center">
          <span className="grid size-9 place-items-center rounded-full bg-success-subtle text-success-emphasis">
            <Check className="size-4" aria-hidden />
          </span>
          <p className="mt-3 text-sm font-medium text-foreground">All clear</p>
          <p className="mt-0.5 text-xs text-muted-foreground">Nothing awaits your review.</p>
        </div>
      ) : (
        <motion.ul
          className="space-y-0.5 p-2.5"
          initial="hidden"
          animate="show"
          variants={{ show: { transition: { staggerChildren: reduce ? 0 : 0.05 } } }}
        >
          {ROWS.map((r) => {
            const count = counts![r.key];
            return (
              <motion.li
                key={r.key}
                variants={{
                  hidden: { opacity: 0, y: reduce ? 0 : 6 },
                  show: { opacity: 1, y: 0, transition: { duration: reduce ? 0 : 0.2, ease: [0.22, 1, 0.36, 1] } },
                }}
              >
                <Link
                  href={r.href}
                  className="group flex items-center gap-3 rounded-lg px-3 py-2.5 transition-colors duration-150 hover:bg-surface-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus"
                >
                  <span className="text-muted-foreground group-hover:text-foreground [&_svg]:size-4" aria-hidden>
                    {r.icon}
                  </span>
                  <span className="flex-1 text-sm text-foreground">{r.label}</span>
                  {count > 0 ? (
                    <span className="rounded-full bg-accent-subtle px-2 py-0.5 text-xs font-medium tabular-nums text-accent-emphasis">
                      {count}
                    </span>
                  ) : (
                    <span className="text-xs tabular-nums text-subtle-foreground">0</span>
                  )}
                  <ChevronRight className="size-4 text-subtle-foreground transition-colors group-hover:text-muted-foreground" aria-hidden />
                </Link>
              </motion.li>
            );
          })}
        </motion.ul>
      )}
    </Card>
  );
}
