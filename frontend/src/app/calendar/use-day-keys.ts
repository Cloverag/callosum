"use client";

import * as React from "react";
import { addDays, dayKey, isSameDay, startOfWeek } from "@/lib/calendar";

/**
 * Roving-focus keyboard navigation for the month/week day grids.
 *
 * Exactly one cell is tabbable (`tabIndex 0`) — the `active` day; the rest are
 * `-1` and reached with the arrow keys. When the grid owns focus, moving `active`
 * re-focuses the matching cell (the page shifts the period first if the target
 * day scrolled off-grid, so the cell always exists by the time we look for it).
 *
 * Not a full ARIA grid (no row/gridcell roles over the flat CSS grid) — just an
 * operable, labelled, focus-visible widget. Enter/Space activate the day.
 */
export function useDayGridKeys({
  active,
  columns,
  onNavigate,
  onActivate,
}: {
  /** The currently-focusable day (already resolved to be visible in the grid). */
  active: Date;
  /** Grid width — 7 for both month and week; ↑/↓ move by this many days. */
  columns: number;
  /** Move focus to another day. The page updates `active` and shifts the period. */
  onNavigate: (next: Date) => void;
  /** Enter/Space on a focused day (e.g. start a new meeting there). */
  onActivate: (day: Date) => void;
}) {
  const gridRef = React.useRef<HTMLDivElement>(null);
  const hasFocus = React.useRef(false);
  const activeKey = dayKey(active);

  // While the grid holds focus, keep the DOM focus on the active cell.
  React.useEffect(() => {
    if (!hasFocus.current) return;
    gridRef.current
      ?.querySelector<HTMLElement>(`[data-daykey="${activeKey}"]`)
      ?.focus();
  }, [activeKey]);

  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    // Only act when a day cell itself is focused — never when a meeting chip
    // inside a cell has focus (its own Enter/click must not create a meeting).
    const target = e.target as HTMLElement;
    if (!target.hasAttribute("data-daykey")) return;

    let next: Date | null = null;
    switch (e.key) {
      case "ArrowLeft":
        next = addDays(active, -1);
        break;
      case "ArrowRight":
        next = addDays(active, 1);
        break;
      case "ArrowUp":
        next = addDays(active, -columns);
        break;
      case "ArrowDown":
        next = addDays(active, columns);
        break;
      case "Home":
        next = startOfWeek(active);
        break;
      case "End":
        next = addDays(startOfWeek(active), 6);
        break;
      case "Enter":
      case " ":
        e.preventDefault();
        onActivate(active);
        return;
      default:
        return;
    }
    e.preventDefault();
    onNavigate(next);
  }

  const gridProps = {
    ref: gridRef,
    onKeyDown,
    onFocusCapture: () => {
      hasFocus.current = true;
    },
    onBlurCapture: (e: React.FocusEvent<HTMLDivElement>) => {
      if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
        hasFocus.current = false;
      }
    },
  };

  /** Props for a day cell: roving tabindex + a focus target key + a label. */
  function cellProps(day: Date, meetingCount: number, label: string) {
    return {
      "data-daykey": dayKey(day),
      tabIndex: isSameDay(day, active) ? 0 : -1,
      "aria-label": `${label}, ${
        meetingCount === 0
          ? "no meetings"
          : `${meetingCount} meeting${meetingCount === 1 ? "" : "s"}`
      }`,
    };
  }

  return { gridProps, cellProps };
}
