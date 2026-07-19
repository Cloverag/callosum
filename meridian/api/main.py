"""Meridian API entry point.

This file exists to make the architecture boundary real: the product imports the
frozen Callosum engine as a library and serves it over HTTP. Nothing here reaches
into `callosum` internals — it only calls the library's public surface.

Run it (from the repo root, with the venv):
    .venv/bin/uvicorn meridian.api.main:app --reload --port 8000

Then open http://localhost:8000/health  and  http://localhost:8000/health/engine
"""

from fastapi import FastAPI

# The proof of separation: Meridian depends ON Callosum, as an ordinary import.
import callosum

app = FastAPI(
    title="Meridian API",
    version="0.0.1",
    summary="Board Operating System over the Callosum verified-memory engine.",
)


@app.get("/health")
def health() -> dict:
    """Liveness: the Meridian API process is up and serving."""
    return {"status": "ok", "service": "meridian-api", "version": app.version}


@app.get("/health/engine")
def engine_health() -> dict:
    """Confirms Meridian can reach the frozen Callosum engine as a library.

    We only touch the package handle here — no database, no model call — so this
    stays a fast, dependency-free check that the boundary is wired correctly.
    """
    return {
        "status": "ok",
        "engine": "callosum",
        "engine_loaded_from": callosum.__file__,
    }
