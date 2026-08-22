"use client";

import { useEffect } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

/**
 * What a route shows when its render throws.
 *
 * There was no boundary anywhere in the app: no `error.tsx`, no
 * `componentDidCatch`, no `ErrorBoundary`. React's behaviour without one is to
 * unmount the entire tree, so a property access on an undefined field in a
 * single card took the whole shell to a blank white screen — the failure mode
 * that looks to a user like the product is gone rather than like one panel is
 * broken.
 *
 * This is the same rule `LoadFailed` encodes for failed requests, applied to
 * failed renders: a crash is not an empty state, and it must say so. The
 * treatment matches `LoadFailed` deliberately — a second visual language for
 * failure would make the app look broken in two different ways.
 *
 * Next.js renders this in place of the route segment, so the shell around it
 * (sidebar, header, assistant rail) survives and the reader can navigate away
 * instead of reloading.
 */
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // The server strips the message in production and leaves a `digest` to
    // correlate against the server log; the console is the only place the
    // client can surface it. There is no error-reporting sink in this project,
    // and inventing one here would be scope this page does not own.
    console.error("Route render failed:", error);
  }, [error]);

  return (
    <div className="p-8">
      <Card className="p-10 text-center">
        <p className="text-sm text-foreground">This page could not be displayed.</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Something in it failed while rendering. The rest of the application is unaffected —
          you can retry, or use the navigation to go elsewhere.
        </p>
        {/* Kept from #138 when the two error boundaries were merged. On a governance
            product the reader's first question after a crash is whether their approval
            or vote went through. This boundary only ever catches a render, never a
            write in flight, so the answer is always no — and saying so is worth a line. */}
        <p className="mt-1 text-sm text-muted-foreground">
          Nothing you submitted has been changed.
        </p>
        {error.digest && (
          <p className="mt-3 font-mono text-[11px] text-subtle-foreground">
            Reference {error.digest}
          </p>
        )}
        <div className="mt-6 flex justify-center">
          <Button variant="secondary" size="sm" onClick={reset}>
            Try again
          </Button>
        </div>
      </Card>
    </div>
  );
}
