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
 * **What this does and does not achieve, measured rather than assumed.** The
 * first version of this comment claimed Next inlines the variable as a literal,
 * so the branch becomes `if (false)` and the bundler drops the module. That is
 * wrong, and the build says so: Turbopack compiles the read to a *runtime*
 * lookup —
 *
 *     let t = "1" === e.i(47167).default.env.NEXT_PUBLIC_MERIDIAN_DEMO;
 *
 * — so no branch is ever eliminated and the router is emitted to
 * `.next/static/chunks` whatever the variable says.
 *
 * What the dynamic import actually buys is code splitting. The router lands in
 * a chunk of its own (22KB) reachable only through the async loader
 * (`e.A(23599)`), so it is in no route's initial import graph and a browser
 * with demo mode off never requests it. The bytes exist on the server; they do
 * not reach a client. That is a real improvement over a static import and it is
 * less than "the fixtures are gone" — worth stating precisely, because the next
 * person to need them gone will otherwise trust this comment instead of
 * grepping the build.
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
