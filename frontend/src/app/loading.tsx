/**
 * State 1 — loading. The route-level skeleton.
 *
 * Sits inside the shell from `layout.tsx`, so the sidebar, header and assistant
 * rail stay put while a segment resolves and only the content column redraws.
 * A full-page spinner would throw the navigation away and rebuild it, which
 * reads as "the app restarted" rather than "this page is coming".
 *
 * ---------------------------------------------------------------------------
 * WHAT THIS DOES AND DOES NOT COVER
 * ---------------------------------------------------------------------------
 * Next shows this while a *segment* suspends. Today every dashboard surface is
 * `"use client"` and fetches in `useEffect`, so the segment resolves almost at
 * once and each widget renders its own in-card skeleton afterwards — this file
 * is therefore mostly structural preparation, and it is the piece that starts
 * doing real work the moment a page moves its fetch to the server.
 *
 * It is deliberately shaped like a page rather than being a single grey block:
 * a skeleton whose proportions do not match what arrives causes a visible
 * relayout, which is a worse first impression than a slightly longer blank.
 */
export default function Loading() {
  return (
    <div className="p-8" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading…</span>

      {/* Page header: title, then the one-line description beneath it. */}
      <div className="flex flex-col gap-3">
        <div className="h-7 w-56 rounded bg-surface-sunken" />
        <div className="h-4 w-96 max-w-full rounded bg-surface-sunken" />
      </div>

      {/* One wide card and one narrow, the proportions most surfaces open with. */}
      <div className="mt-8 grid gap-6 lg:grid-cols-3">
        <div className="h-48 rounded-[16px] bg-surface-sunken lg:col-span-2" />
        <div className="h-48 rounded-[16px] bg-surface-sunken" />
      </div>

      <div className="mt-8 space-y-6">
        <div className="h-40 rounded-[16px] bg-surface-sunken" />
        <div className="h-40 rounded-[16px] bg-surface-sunken" />
      </div>
    </div>
  );
}
