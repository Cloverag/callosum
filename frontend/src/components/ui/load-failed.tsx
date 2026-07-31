import { Card } from "@/components/ui/card";
import { ApiError } from "@/lib/http";

/**
 * What a surface shows when its data could not be loaded.
 *
 * Extracted from `resolutions/page.tsx`, which was the only page that handled a failed
 * request. The other seven logged an unhandled rejection and sat on their loading
 * skeleton forever — which reads to a user as "still loading", not as "this failed".
 *
 * **The rule this encodes: a failed request is not an empty result.**
 * `.catch(() => setItems([]))` is the tempting one-liner and it is wrong. It renders
 * "no meetings match these filters" — a confident statement about the data — when the
 * truth is that we do not know what the data is. That is the same class of error as
 * printing an unmeasured number as though it had been counted.
 *
 * The three cases are distinguished because they need different actions from the
 * reader: choose a workspace, sign in again, or tell someone the server is unhappy.
 */
export function LoadFailed({ what, error }: { what: string; error: ApiError }) {
  return (
    <Card className="p-10 text-center">
      <p className="text-sm text-foreground">{what} could not be loaded.</p>
      <p className="mt-1 text-sm text-muted-foreground">
        {error.needsWorkspace
          ? "Select a workspace to continue."
          : error.isUnauthenticated
            ? "Your session has ended. Sign in again."
            : error.message}
      </p>
    </Card>
  );
}

/**
 * Normalises anything thrown by a fetch into an `ApiError`.
 *
 * A network failure rejects with a `TypeError`, not an `ApiError`, so a surface that
 * assumed the latter would crash while handling the crash. Code `0` marks "never
 * reached the server", which is a different thing from any status the server returned.
 */
export function asApiError(err: unknown): ApiError {
  return err instanceof ApiError ? err : new ApiError(0, "network", "Could not reach the server.");
}
