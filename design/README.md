# Meridian governed workflow design prototype

Open `meridian-governed-workflows.html` directly in a browser. It is self-contained static
UX research: no server, API, database, authentication, telemetry, memory write, or external
action exists behind it.

It adapts the supplied Meridian Dashboard prototype's calm workspace shell, persistent Ask
Meridian framing, and source badges into three trust-critical flows:

- **Grounded chat:** approved facts, readable citations, and an opaque withheld-source count.
- **Approval review:** exact quote, source, evidence span, confidence, and a local-only
  simulated disposition.
- **Citation inspection:** document identity, quote span, access basis, and provenance for
  readable sources only.

This is not P0/P3 implementation. It creates no product models, APIs, identity, policy,
persistence, or web application. The authoritative requirements remain `PRD.md`; delivery is
still gated by `ROADMAP.md`.

## Quick review

1. Use left navigation to switch flows.
2. Ask suggested questions and open `[1]` and `[2]` citations.
3. Simulate an approval/rejection and confirm the dialog says no graph change occurs.
4. Keyboard-review native controls and the labelled citation drawer close action.
5. Compare the artifact with `docs/ux/meridian-governed-workflows.md`.
