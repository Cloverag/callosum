from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Opus on both extraction and synthesis. Extraction quality *is* graph quality:
# a missed OPPOSED edge is a wrong answer to "who opposed Pricing Model B", and
# no amount of retrieval cleverness recovers an edge that was never written.
# Cost is handled by the Batch API (50%) + prompt caching, not by a weaker model.
EXTRACTION_MODEL = "claude-opus-4-8"
SYNTHESIS_MODEL = "claude-opus-4-8"

EMBEDDING_MODEL = "voyage-3"
EMBEDDING_DIM = 1024  # must match VECTOR(1024) in schema/postgres.sql


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    voyage_api_key: str = ""

    # 5433, not 5432 — dodges any Postgres already running on the host.
    postgres_dsn: str = "postgresql://meridian:meridian@localhost:5433/meridian"

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "meridian123"

    chunk_tokens: int = 800
    chunk_overlap_tokens: int = 120


@lru_cache
def settings() -> Settings:
    return Settings()
