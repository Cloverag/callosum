# Privacy notice — Callosum / Meridian demo

**This is not a product privacy policy for a company that processes customer
board data.** It describes the **public synthetic demo** at
[callosum-demo.vercel.app](https://callosum-demo.vercel.app/demo).

Callosum/Meridian is a research/product prototype. Demo identities (Raj
Malhotra, Priya Nair, Marcus Webb) are **fictional**. There is no real board, no
real compensation file, and no real email addresses belonging to those people.
The identity selector is an **authentication bypass**, allowed only because the
database is fabricated. See `docs/deploy/DEMO_AUTH_SPEC.md`.

The operator of this demo is the repository owner of
[Cloverag/callosum](https://github.com/Cloverag/callosum).

## What we store when you use the demo

- A **session cookie** (`httpOnly`, `SameSite=Lax`, `Secure` on the demo host).
  It holds a principal id and the identity provider label. It does **not** hold
  clearance. Purpose: stay signed in as the demo identity you picked. Typical
  lifetime: 24 hours (see `meridian/api/session.py`).
- **No marketing cookies, no analytics pixels, no sale of data.**
- If you type a question into a surface that calls retrieval, the API may write
  a `query_log` row (question, plan, hits, answer). That log is an operational
  record of a **fake board**. Intended retention: until the demo volume is
  reset, or **90 days**, whichever comes first. There is **no automated TTL**
  in v1.
- Membership and approval actions may write append-only `audit_event` rows
  under the same retention intent.

Do not paste real people’s names, emails, or confidential files into the demo.
If you did so by accident, contact the repository owner via a **private**
GitHub security advisory (`SECURITY.md`) or an issue that contains **no**
payload — we will delete what we can identify on the demo host.

## Processors

The browser talks to Vercel. The API sits on a home server reached through
Cloudflare. Synthesis/extraction may call **Ollama Cloud**. Named list:
`docs/compliance/PROCESSORS.md`. Prompt text may leave your country.

## Your requests

Because the corpus is fiction, GDPR rights in respect of Raj/Priya/Marcus do
not apply. For **your** accidental input: we will erase identifiable `query_log`
rows on request. We do not run a self-service DSAR portal.

## Production

A future tenant with real documents needs a different notice, a DPA, and
`MERIDIAN_DEMO_SELECTOR` **off**. That is not this deployment.

Control mapping: `docs/compliance/CONTROL_MATRIX.md`.
