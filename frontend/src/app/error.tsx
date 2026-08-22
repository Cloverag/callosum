"use client";

import { useEffect } from "react";
import { Card } from "@/components/ui/card";

/**
 * State 3 — error. The last resort for a surface that threw during render.
 *
 * ---------------------------------------------------------------------------
 * THIS IS THE NET, NOT THE HANDLER
 * ---------------------------------------------------------------------------
 * Pages already catch their own failed fetches and render `LoadFailed`, which is
 * the better experience: the rest of the page keeps working and only the part
 * that failed says so. This boundary catches what that cannot — a render-time
 * throw, a bad shape from the API that a component destructured, a bug.
 *
 * Before it existed, those took the whole segment down to React's default,
 * which in production is a blank screen. A blank screen is the same failure the
 * spec names elsewhere: it does not distinguish "broken" from "empty".
 *
 * It sits inside `layout.tsx`, so the shell survives and the reader can still
 * navigate away instead of being stranded.
 *
 * ---------------------------------------------------------------------------
 * ONE STATEMENT, AT THE TOP
 * ---------------------------------------------------------------------------
 * The spec's rule for this state is that a failure is stated once. Repeating it
 * per widget produces a page of identical red boxes and buries the one fact the
 * reader needs — that nothing on screen can be trusted right now.
 */
export default function SegmentError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Nothing is wired to collect this yet. It goes to the console rather than
    // nowhere, because a digest with no matching log entry is unactionable —
    // the digest is the only handle a user can quote back to support.
    console.error("Unhandled render error", error);
  }, [error]);

  /**
   * `ApiError` survives a client-side throw, but a server-rendered one is
   * replaced with a bare Error carrying only `digest` — React strips the message
   * so it cannot leak. So this is duck-typed, and falls back to the generic
   * wording rather than asserting a cause it cannot actually see.
   */
  const isSessionError = error.name === "ApiError" && /session/i.test(error.message);

  return (
    <div className="p-8">
      <Card className="mx-auto max-w-lg p-10 text-center">
        <p className="text-sm text-foreground">This page could not be displayed.</p>
        <p className="mt-1 text-sm text-muted-foreground">
          {isSessionError
            ? "Your session has ended. Sign in again."
            : "Something went wrong while rendering it. Your data has not been changed."}
        </p>

        {/* The reassurance above is load-bearing on a governance product: the
            reader's first question after a crash is whether their approval or
            vote went through. This boundary only ever catches render, never a
            write in flight, so the answer is always no. */}

        <div className="mt-6 flex items-center justify-center gap-3">
          <button
            type="button"
            onClick={reset}
            className="rounded-[12px] bg-accent px-4 py-2 text-sm font-medium text-accent-foreground hover:bg-accent-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-raised"
          >
            Try again
          </button>
        </div>

        {error.digest && (
          <p className="mt-6 text-xs text-subtle-foreground">
            Reference <span className="font-mono tabular-nums">{error.digest}</span>
          </p>
        )}
      </Card>
    </div>
  );
}
