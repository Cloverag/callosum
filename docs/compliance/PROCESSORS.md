# Processors (demo)

Named third parties that may see **synthetic** demo traffic. Not a customer DPA.
Prompt or document text may leave the machine and the EU/UK.

| Processor | Role | What it may see |
|---|---|---|
| Vercel | Hosts the Next.js frontend | HTTPS requests, including the session cookie on this origin |
| Cloudflare | Tunnel and DNS to the API | HTTPS to `api` on the demo host |
| Demo host (operator-controlled) | FastAPI, Postgres, Neo4j | Full demo database, `query_log`, `audit_event` |
| Ollama Cloud | Default LLM (`gpt-oss:120b-cloud`) | Prompts/completions for extraction and answer synthesis when those paths run |
| Local `bge-m3` | Embeddings on the demo host | Chunk text, not a third-party processor when run locally |

Keycloak is **not** a demo processor: the public demo uses the principal
selector, not OIDC.

Anthropic / Voyage appear in `pyproject.toml` as optional providers. They are
**not** in the default demo path unless the operator points `.env.demo` at them.

Change this file when the demo’s vendors change. The control matrix points here
for SOC 2 CC9 / GDPR Art. 28 (lite).
