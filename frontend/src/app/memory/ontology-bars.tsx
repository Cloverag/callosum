"use client";

import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/vendor/tooltip";
import type { Distribution } from "@/lib/graph-stats";

/**
 * What the graph is made of — sorted bars, one hue.
 *
 * FORM. The proposal that prompted this asked for a treemap of entity types and
 * a radial chart of relation types. Both were rejected on measurement, not
 * taste: there are 8 entity types and 14 relation types, and past ~7 colour
 * classes adjacent categories blur — while a radial bar encodes magnitude as arc
 * length at varying radius, so equal values look unequal. Sorted horizontal bars
 * put every value on one baseline where length is the only variable, which is
 * exactly the comparison a reader is making.
 *
 * COLOUR is not the encoding here, so 14 rows is fine — a single memory violet
 * throughout, length carrying the value, and blue only for the active filter.
 *
 * INTERACTIVE by design: each row filters the canvas above, because "11 Persons"
 * is a fact and "show me the 11" is the question that follows it.
 */
export function OntologyBars({
  title,
  caption,
  items,
  activeKey,
  onSelect,
}: {
  title: string;
  caption: string;
  items: Distribution[];
  activeKey: string | null;
  onSelect: (key: string | null) => void;
}) {
  const max = Math.max(...items.map((i) => i.count), 1);
  const total = items.reduce((sum, i) => sum + i.count, 0);

  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        {activeKey ? (
          <button
            type="button"
            onClick={() => onSelect(null)}
            className="rounded-[6px] text-xs text-accent-emphasis underline decoration-dotted underline-offset-4 hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
          >
            Clear filter
          </button>
        ) : (
          <span className="text-xs tabular-nums text-subtle-foreground">
            {total} across {items.length}
          </span>
        )}
      </div>
      <p className="max-w-[52ch] text-xs text-subtle-foreground">{caption}</p>

      <ul className="flex flex-col gap-0.5">
        {items.map((item) => {
          const active = activeKey === item.key;
          const row = (
            <button
              type="button"
              onClick={() => onSelect(active ? null : item.key)}
              aria-pressed={active}
              className={cn(
                "group w-full rounded-[8px] px-2 py-1.5 text-left transition-colors",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised",
                active ? "bg-accent-subtle" : "hover:bg-surface-alt"
              )}
            >
              <div className="flex items-baseline justify-between gap-3">
                <span
                  className={cn(
                    "truncate text-xs",
                    item.label === item.label.toUpperCase() && item.label.length > 2
                      ? "font-mono tracking-[0.04em]"
                      : "",
                    active ? "font-medium text-accent-emphasis" : "text-muted-foreground"
                  )}
                >
                  {item.label}
                </span>
                <span className="shrink-0 text-xs tabular-nums text-foreground">
                  {item.count}
                </span>
              </div>
              {/* One shared 0..max scale, so rows are comparable by length alone. */}
              <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-surface-sunken">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${(item.count / max) * 100}%`,
                    background: active ? "var(--accent)" : "var(--memory)",
                    opacity: active ? 1 : 0.55,
                  }}
                />
              </div>
            </button>
          );

          return (
            <li key={item.key}>
              {item.hint ? (
                <Tooltip>
                  <TooltipTrigger render={row} />
                  <TooltipContent side="right" className="max-w-[18rem]">
                    {item.hint}
                  </TooltipContent>
                </Tooltip>
              ) : (
                row
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
