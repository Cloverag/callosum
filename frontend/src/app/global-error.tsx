"use client";

import { useEffect } from "react";
import "./globals.css";
import { THEME_SCRIPT } from "@/components/theme";

/**
 * The last resort: a failure in the ROOT LAYOUT itself.
 *
 * `error.tsx` renders *inside* the layout, so it cannot catch a throw from the
 * layout — at that point there is no shell left to render into. Next.js
 * replaces the whole document with this file instead, which is why it must
 * supply its own `<html>` and `<body>`.
 *
 * Two consequences of replacing the document, both handled here rather than
 * left to chance:
 *
 *   · The layout's `globals.css` import is gone with it, so the token layer is
 *     imported directly. Without it this page renders as unstyled black text on
 *     white — in a dark-theme session, a full-screen white flash at the exact
 *     moment something has already gone wrong.
 *   · The layout's pre-paint theme script is gone too, so it is repeated. It
 *     resolves an explicit light/dark choice; without it only the OS preference
 *     would apply and a user who had chosen dark would get a light page.
 *
 * No `Card`, `Button` or font import: every one of those is a module that could
 * itself be implicated in the failure being reported. A fallback that depends on
 * the thing it is a fallback for is not a fallback.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Root layout render failed:", error);
  }, [error]);

  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body
        style={{
          background: "var(--surface)",
          color: "var(--foreground)",
          minHeight: "100vh",
          display: "grid",
          placeItems: "center",
          padding: "2rem",
          fontFamily: "ui-sans-serif, system-ui, sans-serif",
        }}
      >
        <main
          style={{
            maxWidth: "32rem",
            textAlign: "center",
            background: "var(--surface-raised)",
            border: "1px solid var(--border)",
            borderRadius: "16px",
            padding: "2.5rem",
            boxShadow: "var(--sh-card)",
          }}
        >
          {/* 1.125rem / 600 is the `section` step on the DESIGN.md ramp. The
              other literals here are `body` (0.875), `metadata` (0.8125) and
              `caption` (0.6875) — inline styles, but on the documented scale. */}
          <h1 style={{ fontSize: "1.125rem", fontWeight: 600, margin: 0, letterSpacing: "-0.01em" }}>
            Meridian could not start.
          </h1>
          <p style={{ margin: "0.5rem 0 0", fontSize: "0.875rem", color: "var(--muted-foreground)" }}>
            The application shell failed to render, so nothing below it could load. This is not a
            problem with your data.
          </p>
          {error.digest && (
            <p
              style={{
                margin: "0.75rem 0 0",
                fontFamily: "ui-monospace, monospace",
                fontSize: "0.6875rem",
                color: "var(--subtle-foreground)",
              }}
            >
              Reference {error.digest}
            </p>
          )}
          <button
            type="button"
            onClick={reset}
            style={{
              marginTop: "1.5rem",
              height: "2rem",
              padding: "0 0.875rem",
              fontSize: "0.8125rem",
              fontWeight: 500,
              borderRadius: "12px",
              border: "1px solid var(--border)",
              background: "var(--surface-raised)",
              color: "var(--foreground)",
              cursor: "pointer",
            }}
          >
            Reload
          </button>
        </main>
      </body>
    </html>
  );
}
