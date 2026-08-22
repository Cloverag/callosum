from enum import StrEnum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Provider(StrEnum):
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"


# Both providers must emit vectors of this width — it is baked into
# `chunk.embedding VECTOR(1024)` in schema/postgres.sql. bge-m3 (Ollama) and
# voyage-3 (Anthropic) are both 1024, which is what makes the backends swappable
# without a migration. Note that switching providers still requires re-embedding
# the corpus: same width, different vector space.
EMBEDDING_DIM = 1024


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Ollama by default. It costs nothing, and a final-year project should be
    # runnable by whoever marks it without them buying API credits first.
    #
    # The Anthropic path stays live but dormant. Extraction quality *is* graph
    # quality — a missed OPPOSED edge is a wrong answer that no retrieval trick
    # recovers — so which model does the extracting is a real research variable,
    # not an implementation detail. Phase 7 measures it.
    provider: Provider = Provider.OLLAMA

    # --- Ollama (default, free) ---
    # `127.0.0.1`, not `localhost` — see the note on the store DSNs below.
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "gpt-oss:120b-cloud"
    ollama_embedding_model: str = "bge-m3"

    # --- Anthropic (needs credits) ---
    anthropic_api_key: str = ""
    anthropic_extraction_model: str = "claude-opus-4-8"
    anthropic_synthesis_model: str = "claude-opus-4-8"
    voyage_api_key: str = ""
    voyage_model: str = "voyage-3"

    # --- Stores ---
    # 5433, not 5432 — dodges any Postgres already running on the host.
    #
    # Two roles, one database (Meridian P1 tenancy):
    #   postgres_dsn      — the `callosum` SUPERUSER. Migrations + admin only. Bypasses
    #                       Row-Level Security, which is why the app must NOT use it.
    #   postgres_app_dsn  — the `callosum_app` non-superuser (created by migration 0004).
    #                       Every runtime connection (store.pg) uses this, so RLS is
    #                       actually enforced. Requires migrations to have run first.
    #
    # ---------------------------------------------------------------------------
    # `127.0.0.1`, NEVER `localhost`, AND `connect_timeout` IS NOT OPTIONAL
    # ---------------------------------------------------------------------------
    # `localhost` resolves to BOTH `::1` and `127.0.0.1`, and `getaddrinfo` returns
    # the IPv6 address first. `docker-compose.yml` publishes these services on IPv4
    # only — `"127.0.0.1:5433:5432"` — so nothing is listening on `::1`. Every
    # connection therefore opened against a dead address, waited out a timeout, and
    # only then fell back to IPv4.
    #
    # Measured on Windows 11 / Docker Desktop, 2026-08-15:
    #
    #     127.0.0.1  ->  0.03s
    #     localhost  ->  8.15s   (exactly the connect_timeout supplied)
    #
    # `store.pg()` opens a fresh connection per call, so the gated suite paid that
    # stall hundreds of times and appeared to hang rather than run.
    #
    # `connect_timeout` matters independently of the host. libpq's default is 0,
    # meaning *wait forever*: with a half-up database — Docker Desktop starting, a
    # container paused, a port proxy accepting but not forwarding — a connection
    # blocks indefinitely and the failure presents as a hang with no error to read.
    # Ten seconds is far longer than a local connection ever legitimately needs and
    # far shorter than a person's patience.
    #
    # Overridable as always: set POSTGRES_DSN / POSTGRES_APP_DSN / NEO4J_URI in
    # `.env` for a remote or differently-bound database.
    postgres_dsn: str = (
        "postgresql://callosum:callosum@127.0.0.1:5433/callosum?connect_timeout=10"
    )
    postgres_app_dsn: str = (
        "postgresql://callosum_app:callosum_app@127.0.0.1:5433/callosum?connect_timeout=10"
    )
    # No timeout parameter here: the Neo4j driver takes `connection_timeout` as a
    # keyword argument and rejects unknown URI query parameters, so a `?`-suffix
    # would be a startup error rather than a shorter wait. `store.neo()` already
    # takes an explicit `wait`.
    neo4j_uri: str = "bolt://127.0.0.1:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "callosum123"

    # --- Chunking ---
    chunk_tokens: int = 800
    chunk_overlap_tokens: int = 120


@lru_cache
def settings() -> Settings:
    return Settings()
