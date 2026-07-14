"""Provider abstraction: one interface, two backends.

Callosum runs on Ollama Cloud by default (free) and on Claude when credits exist.
The pipeline never imports a vendor SDK directly — it calls `structured()`, `text()`
and `embed()` from here, so switching providers is one environment variable.

This is not just thrift. Because both backends are live behind the same interface,
"open-weight vs frontier extraction quality" becomes a controlled experiment we get
almost for free: same prompt, same schema, same corpus, same graph, different model.
That comparison is a Phase 7 result.
"""

from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from callosum.config import Provider, settings

T = TypeVar("T", bound=BaseModel)

OLLAMA_TIMEOUT = 300.0  # cloud models think for a while on a dense transcript chunk


# ---------------------------------------------------------------------------
# Schema flattening
# ---------------------------------------------------------------------------


def _inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Resolve $ref/$defs into a single self-contained schema.

    Pydantic emits nested models and enums as `$ref` pointers into a `$defs` block.
    Ollama compiles the schema down to a GBNF grammar to constrain decoding, and its
    handling of `$ref` is unreliable — a dangling ref means the grammar silently
    fails to constrain the field, and you get free-form text where you expected an
    enum. Flattening is cheaper than debugging that.
    """
    defs = schema.pop("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].rsplit("/", 1)[-1]
                target = defs.get(name, {})
                merged = {k: v for k, v in node.items() if k != "$ref"}
                return resolve({**target, **merged})
            return {k: resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)


# ---------------------------------------------------------------------------
# Structured output
# ---------------------------------------------------------------------------


def structured(system: str, user: str, output: type[T]) -> T:
    """Get schema-validated structured output. The workhorse of extraction."""
    cfg = settings()

    if cfg.provider == Provider.ANTHROPIC:
        import anthropic

        response = anthropic.Anthropic(api_key=cfg.anthropic_api_key or None).messages.parse(
            model=cfg.anthropic_extraction_model,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            # Anthropic caches the system prefix across chunks; Ollama has no
            # equivalent API, which is why this lives inside the backend branch.
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_format=output,
        )
        return response.parsed_output

    schema = _inline_refs(output.model_json_schema())
    response = httpx.post(
        f"{cfg.ollama_host}/api/chat",
        timeout=OLLAMA_TIMEOUT,
        json={
            "model": cfg.ollama_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": schema,
            "options": {"num_ctx": 16384},
        },
    )
    _raise_for_ollama(response)
    content = response.json()["message"]["content"]

    # Ollama constrains decoding to the schema, so this should always parse. When it
    # doesn't, the failure is worth surfacing loudly rather than swallowing: a model
    # that cannot hold the schema cannot be trusted to populate the graph either.
    return output.model_validate_json(content)


def text(system: str, user: str, effort: str = "high", max_tokens: int = 4000) -> str:
    """Free-form generation — the answer-synthesis path."""
    cfg = settings()

    if cfg.provider == Provider.ANTHROPIC:
        import anthropic

        response = anthropic.Anthropic(api_key=cfg.anthropic_api_key or None).messages.create(
            model=cfg.anthropic_synthesis_model,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            output_config={"effort": effort},
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return next((b.text for b in response.content if b.type == "text"), "")

    response = httpx.post(
        f"{cfg.ollama_host}/api/chat",
        timeout=OLLAMA_TIMEOUT,
        json={
            "model": cfg.ollama_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"num_ctx": 16384, "num_predict": max_tokens},
        },
    )
    _raise_for_ollama(response)
    return response.json()["message"]["content"]


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------


def embed(texts: list[str], input_type: str = "document") -> list[list[float]]:
    """Embed texts. Both backends produce 1024-dim vectors, so the `chunk.embedding`
    column does not change when you switch providers — a corpus embedded with one
    model still has to be re-embedded with the other, but the schema holds.
    """
    if not texts:
        return []

    cfg = settings()

    if cfg.provider == Provider.ANTHROPIC:
        import voyageai

        client = voyageai.Client(api_key=cfg.voyage_api_key or None)
        vectors: list[list[float]] = []
        for i in range(0, len(texts), 128):
            result = client.embed(
                texts[i : i + 128], model=cfg.voyage_model, input_type=input_type
            )
            vectors.extend(result.embeddings)
    else:
        vectors = []
        # bge-m3 runs locally and is free. Batch modestly — a long transcript chunk
        # is a lot of tokens and the local model has no server-side batching.
        for i in range(0, len(texts), 16):
            response = httpx.post(
                f"{cfg.ollama_host}/api/embed",
                timeout=OLLAMA_TIMEOUT,
                json={"model": cfg.ollama_embedding_model, "input": texts[i : i + 16]},
            )
            _raise_for_ollama(response)
            vectors.extend(response.json()["embeddings"])

    from callosum.config import EMBEDDING_DIM

    if vectors and len(vectors[0]) != EMBEDDING_DIM:
        raise ValueError(
            f"Embedding model returned {len(vectors[0])}-dim vectors but "
            f"chunk.embedding is VECTOR({EMBEDDING_DIM}). Either pick a 1024-dim "
            f"model (bge-m3, mxbai-embed-large, voyage-3) or migrate the column."
        )
    return vectors


# ---------------------------------------------------------------------------


def _raise_for_ollama(response: httpx.Response) -> None:
    """Turn Ollama's failure modes into errors that say what to do about them."""
    if response.status_code == 200:
        return

    body = response.text
    if "unauthorized" in body or response.status_code == 401:
        raise RuntimeError(
            "Ollama Cloud is not authenticated. Run:  ollama signin\n"
            "(Cloud models like kimi-k2.5:cloud need a signed-in ollama.com account.)"
        )
    if response.status_code == 404:
        raise RuntimeError(
            f"Model not found: {settings().ollama_model}\n"
            f"Pull it first:  ollama pull {settings().ollama_model}"
        )
    raise RuntimeError(f"Ollama error {response.status_code}: {body[:500]}")


def health() -> dict[str, Any]:
    """Check the configured provider is actually reachable before a long ingest.

    Failing here costs a second. Failing on chunk 47 of an overnight run costs the run.
    """
    cfg = settings()

    if cfg.provider == Provider.ANTHROPIC:
        return {
            "provider": "anthropic",
            "model": cfg.anthropic_extraction_model,
            "key_set": bool(cfg.anthropic_api_key),
        }

    try:
        tags = httpx.get(f"{cfg.ollama_host}/api/tags", timeout=10.0)
        available = [m["name"] for m in tags.json().get("models", [])]
    except httpx.ConnectError as exc:
        raise RuntimeError(
            f"Ollama is not running at {cfg.ollama_host}. Start it:  ollama serve"
        ) from exc

    return {
        "provider": "ollama",
        "model": cfg.ollama_model,
        "embedding_model": cfg.ollama_embedding_model,
        "available": available,
        "model_present": any(m.startswith(cfg.ollama_model.split(":")[0]) for m in available),
        "embedding_present": any(
            m.startswith(cfg.ollama_embedding_model.split(":")[0]) for m in available
        ),
    }
