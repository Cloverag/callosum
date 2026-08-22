"use client";

/**
 * The layout itself failed.
 *
 * This replaces the root layout rather than rendering inside it, which is why it
 * carries its own `<html>` and `<body>` — by the time it runs, the shell that
 * would normally provide them is the thing that threw.
 *
 * That also means no shell, no navigation and no tokens can be relied on: if the
 * stylesheet is what failed, token classes render as nothing. The styling here is
 * inline and literal for that reason alone. It is the only file in the app
 * allowed to hold raw colour values, and it holds the two it cannot do without.
 *
 * In practice this is reachable when `SessionGate` throws, since it wraps the
 * whole shell. There is no "try again" that can fix a broken layout mid-session,
 * so the action is a full reload.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body style={{ margin: 0, background: "#f7f8fa", color: "#111827", fontFamily: "system-ui, sans-serif" }}>
        <div style={{ display: "flex", minHeight: "100vh", alignItems: "center", justifyContent: "center", padding: "2rem" }}>
          <div style={{ maxWidth: "28rem", textAlign: "center" }}>
            <p style={{ margin: 0, fontSize: "0.875rem" }}>Meridian could not start.</p>
            <p style={{ margin: "0.25rem 0 0", fontSize: "0.875rem", color: "#475569" }}>
              The application shell failed to load. Reloading usually clears it; if it does not, the
              server may be unreachable.
            </p>
            <button
              type="button"
              onClick={reset}
              style={{
                marginTop: "1.5rem",
                padding: "0.5rem 1rem",
                fontSize: "0.875rem",
                fontWeight: 500,
                color: "#ffffff",
                background: "#2563eb",
                border: "none",
                borderRadius: "12px",
                cursor: "pointer",
              }}
            >
              Reload
            </button>
            {error.digest && (
              <p style={{ marginTop: "1.5rem", fontSize: "0.75rem", color: "#64748b" }}>
                Reference {error.digest}
              </p>
            )}
          </div>
        </div>
      </body>
    </html>
  );
}
