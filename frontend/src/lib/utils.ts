import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * A timestamp as a short calendar date in the viewer's own time zone.
 *
 * One copy for every card (#249). The five it replaces pinned `timeZone: "UTC"` to
 * dodge a hydration mismatch, but these cards only render client-side behind
 * `SessionGate`, and UTC showed an evening event in the Americas on the next day while
 * the calendar, which uses local days, showed the right one.
 */
export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}
