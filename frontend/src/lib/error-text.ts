import type { ApiError } from "@/lib/http";

/**
 * The one place a server-supplied error string becomes text on a screen.
 *
 * ---------------------------------------------------------------------------
 * WHY THIS EXISTS, GIVEN IT CANNOT SANITISE ANYTHING
 * ---------------------------------------------------------------------------
 * It does not filter, and it could not: the client has no idea which strings are
 * restricted. `meridian/api/errors.py` passes a domain exception's own `str()` to the
 * client unless that exception has a fixed detail — deliberately, because "expected
 * version 3, current 4" is exactly what a caller needs.
 *
 * So the value here is **chokepoint, not sanitiser**. Before this, four surfaces each
 * rendered `error.message` inline. The invariant that no error names a restricted
 * document lived in the discipline of whoever wrote each exception message, and nothing
 * could enforce it or change it in one place. That is the property #151 was opened to
 * stop relying on, and #157 found it still holding four layers up.
 *
 * With one function, a policy change is one edit, and
 * `__tests__/error-text-discipline.test.ts` fails the build when a fifth surface renders
 * `error.message` directly rather than joining.
 *
 * ---------------------------------------------------------------------------
 * WHAT IT DELIBERATELY DOES NOT DO
 * ---------------------------------------------------------------------------
 * It does not paraphrase. A 403 from intake names the clearance the caller may file at,
 * and replacing that with "permission denied" throws away the only part telling them
 * what to do next. The server's words are kept because they are useful; they are kept
 * *here* so that if that ever stops being safe, there is somewhere to change it.
 */
export function serverMessage(error: ApiError): string {
  // The two cases that are about the SESSION rather than the request. Both are answered
  // without consulting the server's string at all, because neither is about this call.
  if (error.needsWorkspace) return "Select a workspace to continue.";
  if (error.isUnauthenticated) return "Your session has ended. Sign in again.";
  return error.message;
}

/**
 * `serverMessage`, prefixed with what failed.
 *
 * The prefix is the caller's own words about its own surface — never the server's — so
 * a reader knows which panel is broken without the message having to say so.
 */
export function loadFailedText(what: string, error: ApiError): string {
  return `${what} could not be loaded. ${serverMessage(error)}`;
}
