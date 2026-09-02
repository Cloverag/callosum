import { DEMO_ENABLED } from "./mode";

/**
 * The seam: `fetch`, or the fixtures, decided before the request exists.
 *
 * `lib/http.ts` and `lib/auth.ts` both call this instead of `fetch`. They are
 * the only two call sites of `fetch` in `src/`, which is what makes "one seam"
 * a fact about the code rather than a convention.
 *
 * Note what is absent: no try, no catch, no status inspection. The branch is on
 * a constant. There is no input to this function that can turn a real failure
 * into fixture data.
 *
 * ---------------------------------------------------------------------------
 * WHY THE FIXTURES ARE BEHIND A DYNAMIC IMPORT
 * ---------------------------------------------------------------------------
 * They were a static import first, and a production build with demo mode OFF
 * then shipped the whole fabricated board — "Amara Okonkwo", the invented term
 * sheet, the synthetic workspace id — inside a client chunk. Measured, by
 * grepping `.next/static/chunks` after `next build`, not assumed.
 *
 * Nothing could *reach* that data with the constant false, so it was not a
 * correctness bug. It is still the wrong shape: fabricated board minutes sitting
 * in the JavaScript a real deployment serves is the sort of thing that gets
 * found later and cannot be explained quickly, and this feature's whole premise
 * is that demo data must not be able to turn up where it is not expected.
 *
 * Next inlines `NEXT_PUBLIC_MERIDIAN_DEMO` as a literal, so with it unset this
 * reads `if (false)` and the bundler drops the branch and the module behind it.
 * Verified the same way it was found: the strings are absent from the non-demo
 * build and present in the demo one.
 *
 * The import is per-request rather than hoisted because the module registry
 * caches it — the second call resolves an already-evaluated module — and
 * hoisting it into a top-level `await` would make this module async for every
 * build, including the ones that never touch it.
 */
export function transport(url: string, init: RequestInit): Promise<Response> {
  if (DEMO_ENABLED) {
    return import("./router").then((demo) =>
      demo.demoResponse(url, init.method ?? "GET", init.body),
    );
  }
  return fetch(url, init);
}
