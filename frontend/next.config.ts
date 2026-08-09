import type { NextConfig } from "next";

/**
 * Where the FastAPI application is listening.
 *
 * Same-origin is a design decision, not an accident: the session is an httpOnly cookie
 * (ADR-009), and `lib/http.ts` sends `credentials: "same-origin"`. Pointing the browser
 * straight at `http://localhost:8000` would put the API on a different origin, the
 * cookie would not be sent, and every authenticated request would read as logged-out.
 *
 * So the Next server proxies instead, and the browser only ever talks to one origin.
 */
const API_ORIGIN = process.env.MERIDIAN_API_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // Allow HMR / dev resources when the app is opened via the LAN IP, not just localhost.
  allowedDevOrigins: ["192.168.29.45"],

  /**
   * Without these, nothing on this site loads data.
   *
   * `lib/http.ts` fetches `/api/...` relative to the page, so in development that
   * resolves to the Next dev server on :3000, which has no such routes and answers with
   * its own 404 HTML. Every surface then renders an error — and the failure is
   * indistinguishable from the API simply not running, which is why it is worth
   * stating here rather than leaving to be rediscovered.
   *
   * `/auth` is proxied for the same reason: the sign-in callback sets the session
   * cookie, and a cookie set on :8000 is not sent to :3000.
   *
   * In production both are expected to sit behind one reverse proxy, where these
   * rewrites are harmless; set `MERIDIAN_API_ORIGIN` if the API lives elsewhere.
   */
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` },
      { source: "/auth/:path*", destination: `${API_ORIGIN}/auth/:path*` },
      { source: "/health/:path*", destination: `${API_ORIGIN}/health/:path*` },
    ];
  },

  /**
   * `/` goes to the dashboard.
   *
   * This used to be `redirect("/dashboard")` inside `app/page.tsx` — a Server Component
   * that threw during render instead of returning markup. Once the shell moved inside
   * `SessionGate`, React's dev-mode render timing measured a component that never
   * rendered and reported `'Home' cannot have a negative time stamp`.
   *
   * Resolving the route before anything renders is both the fix and the more honest
   * shape: `/` is not a page that decides to go elsewhere, it is an alias. Permanent is
   * false because this is an application route, not a moved resource.
   */
  async redirects() {
    return [{ source: "/", destination: "/dashboard", permanent: false }];
  },
};

export default nextConfig;
