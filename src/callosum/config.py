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
    ollama_host: str = "http://localhost:11434"
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
    postgres_dsn: str = "postgresql://callosum:callosum@localhost:5433/callosum"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "callosum123"

    # --- Chunking ---
    chunk_tokens: int = 800
    chunk_overlap_tokens: int = 120


@lru_cache
def settings() -> Settings:
    return Settings()
