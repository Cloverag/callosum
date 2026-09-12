/**
 * Public privacy notice. Ungated in `session-gate.tsx` so a signed-out visitor
 * on /demo can read it. Canonical copy lives in `docs/privacy.md`; this page
 * is what the demo actually serves.
 */
export default function PrivacyPage() {
  return (
    <main className="mx-auto max-w-2xl p-8">
      <h1 className="text-2xl font-semibold">Privacy</h1>
      <p className="mt-3 text-sm text-muted-foreground">
        This is the public synthetic demo, not a product that processes a real
        company&apos;s board data. Raj Malhotra, Priya Nair and Marcus Webb are
        fictional. There is no real board and no real compensation file.
      </p>
      <p className="mt-3 text-sm text-muted-foreground">
        The identity selector is an authentication bypass, allowed only because
        that database is fabricated.
      </p>

      <h2 className="mt-8 text-lg font-medium">What this demo stores</h2>
      <ul className="mt-2 list-disc space-y-2 pl-5 text-sm text-muted-foreground">
        <li>
          A session cookie (<code className="text-foreground">httpOnly</code>,{" "}
          <code className="text-foreground">SameSite=Lax</code>, Secure on the
          demo host). It holds who you picked, not a clearance. About 24 hours.
        </li>
        <li>No marketing cookies, no analytics pixels, no sale of data.</li>
        <li>
          Questions you type may be written to an operational <code className="text-foreground">query_log</code>.
          Intended keep: until the demo volume is reset, or 90 days, whichever
          comes first. There is no automated expiry in this version.
        </li>
      </ul>

      <h2 className="mt-8 text-lg font-medium">Do not paste real people</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        If you accidentally submitted real names or files, tell the repository
        owner through a private GitHub security advisory and include no payload
        in a public issue. We will delete what we can identify.
      </p>

      <h2 className="mt-8 text-lg font-medium">Processors</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Vercel (this frontend), Cloudflare (tunnel to the API), the operator&apos;s
        demo host (database), and Ollama Cloud when the model runs. Prompt text
        may leave your country. Full list:{" "}
        <code className="text-foreground">docs/compliance/PROCESSORS.md</code> in
        the repository.
      </p>

      <p className="mt-8 text-sm">
        <a className="text-accent-emphasis underline" href="/demo">
          Back to the demo
        </a>
      </p>
    </main>
  );
}
