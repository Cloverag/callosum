"""Provider abstraction: one interface, two backends.

Callosum runs on Ollama Cloud by default (free) and on Claude when credits exist.
The pipeline never imports a vendor SDK directly — it calls `structured()`, `text()`
and `embed()` from here, so switching providers is one environment variable.

This is not just thrift. Because both backends are live behind the same interface,
"open-weight vs frontier extraction quality" becomes a controlled experiment we get
almost for free: same prompt, same schema, same corpus, same graph, different model.
That comparison is a Phase 7 result.
"""

import json
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

    # Ollama enforces `format` as a decoding grammar for LOCAL models only. Cloud
    # models receive it as, at best, a suggestion — on longer inputs they happily
    # emit markdown tables instead. So the schema also goes into the prompt as an
    # explicit instruction, we still pass `format` (it helps when honored), and a
    # failed parse gets one repair round-trip before we give up.
    json_instruction = (
        "\n\n# Output format (mandatory)\n"
        "Respond with a SINGLE JSON object and nothing else — no markdown, no "
        "tables, no code fences, no commentary before or after. The object must "
        f"validate against this JSON Schema:\n{json.dumps(schema)}"
    )

    def _call(messages: list[dict[str, str]]) -> str:
        response = httpx.post(
            f"{cfg.ollama_host}/api/chat",
            timeout=OLLAMA_TIMEOUT,
            json={
                "model": cfg.ollama_model,
                "messages": messages,
                "stream": False,
                "format": schema,
                "options": {"num_ctx": 16384},
            },
        )
        _raise_for_ollama(response)
        return response.json()["message"]["content"]

    messages = [
        {"role": "system", "content": system + json_instruction},
        {"role": "user", "content": user},
    ]
    content = _call(messages)

    try:
        return _parse_structured(content, output)
    except ValueError:
        # Repair round: the model already did the reasoning — make it re-emit its
        # own output as the JSON it was asked for. One retry, then fail loudly.
        repair = _call(
            messages
            + [
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        "Your previous reply was not a JSON object. Convert it into "
                        "a single JSON object that validates against the schema you "
                        "were given. Output ONLY the JSON object."
                    ),
                },
            ]
        )
        return _parse_structured(repair, output)


def _parse_structured(content: str, output: type[T]) -> T:
    """Find and validate the schema object inside possibly-messy model output.

    Tries the whole content first, then each balanced JSON object found by
    raw_decode at successive '{' positions (skipping fences, preamble, and inner
    objects). A candidate only counts if it shares at least one key with the target
    model's fields — Pydantic ignores unknown keys and every Extraction field has a
    default, so without this guard a stray inner dict like {"type": "Person"} would
    "validate" as an EMPTY Extraction and silently discard the whole result. A
    parser that can hallucinate an empty success is worse than one that crashes.
    """
    import json as _json

    from pydantic import ValidationError

    fields = set(output.model_fields)

    def try_candidate(candidate: Any) -> T | None:
        if not isinstance(candidate, dict) or not (fields & candidate.keys()):
            return None
        try:
            return output.model_validate(candidate)
        except ValidationError:
            return None

    try:
        parsed = _json.loads(content.strip())
    except _json.JSONDecodeError:
        parsed = None
    if (result := try_candidate(parsed)) is not None:
        return result

    decoder = _json.JSONDecoder()
    pos = content.find("{")
    attempts = 0
    while pos != -1 and attempts < 20:
        try:
            candidate, _ = decoder.raw_decode(content, pos)
            if (result := try_candidate(candidate)) is not None:
                return result
        except _json.JSONDecodeError:
            pass
        pos = content.find("{", pos + 1)
        attempts += 1

    raise ValueError(
        f"Model output contained no object matching {output.__name__}. "
        f"First 300 chars: {content[:300]!r}"
    )


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

    # An empty or whitespace-only string makes bge-m3 emit a NaN vector, which Ollama
    # then fails to JSON-encode ("unsupported value: NaN", HTTP 500) — taking down the
    # whole call. Substitute a single space: the resulting vector is meaningless, but
    # callers that pass empty text (e.g. a planner that returned no search_query) get a
    # harmless zero-signal embedding instead of a crash. Real inputs are never empty.
    texts = [t if t and t.strip() else " " for t in texts]

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
