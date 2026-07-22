import { Sparkles } from "lucide-react";
import { Card } from "@/components/ui/card";

/** A slim, evidence-grounded orientation line — the first thing the operator reads. */
export function DailyBrief({ brief }: { brief: string | null }) {
  return (
    <Card className="flex items-center gap-4 px-6 py-4">
      <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-accent-subtle text-accent-emphasis">
        <Sparkles className="size-4" aria-hidden />
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-subtle-foreground">Daily brief</div>
        {brief === null ? (
          <div className="mt-1 h-4 w-2/3 rounded bg-surface-raised" />
        ) : (
          <p className="mt-0.5 text-sm text-foreground">{brief}</p>
        )}
      </div>
      <kbd className="hidden shrink-0 rounded border border-border px-1.5 py-0.5 text-[10px] text-subtle-foreground sm:inline">
        ⌘J to ask
      </kbd>
    </Card>
  );
}
