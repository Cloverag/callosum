"""Meridian API entry point.

This file exists to make the architecture boundary real: the product imports the
frozen Callosum engine as a library and serves it over HTTP. Nothing here reaches
into `callosum` internals — it only calls the library's public surface.

Run it (from the repo root, with the venv):
    .venv/bin/uvicorn meridian.api.main:app --reload --port 8000

Then open http://localhost:8000/health  and  http://localhost:8000/health/engine
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

# The proof of separation: Meridian depends ON Callosum, as an ordinary import.
import callosum
from meridian.api import auth, errors
from meridian.api import agenda as agenda_api
from meridian.api import board_members as board_members_api
from meridian.api import commitments as commitments_api
from meridian.api import conflicts as conflicts_api
from meridian.api import decisions as decisions_api
from meridian.api import documents as documents_api
from meridian.api import meetings as meetings_api
from meridian.api import minutes as minutes_api
from meridian.api import notifications as notifications_api
from meridian.api import packs as packs_api
from meridian.api import prep as prep_api
from meridian.api import resolutions as resolutions_api
from meridian.api.config import api_settings

app = FastAPI(
    title="Meridian API",
    version="0.0.1",
    summary="Board Operating System over the Callosum verified-memory engine.",
)

_settings = api_settings()

# --- CORS Configuration (M-14) ---------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Session (ADR-009) -----------------------------------------------------
#
# Installed only when a signing secret is configured. Starting with an unsigned or
# default-signed session would be worse than starting without one: the app would look
# authenticated-capable while handing out cookies anybody could forge.
#
# `httponly=True` is Starlette's default and is not overridden — the session must not
# be readable from JavaScript. `same_site="lax"` is required rather than preferred:
# the OIDC callback is a cross-site GET redirect back from the provider, and `strict`
# would withhold the cookie on exactly that navigation.
if _settings.session_configured():
    app.add_middleware(
        SessionMiddleware,
        secret_key=_settings.session_secret,
        session_cookie=_settings.session_cookie_name,
        max_age=_settings.session_max_age,
        same_site=_settings.session_same_site,
        https_only=_settings.session_https_only,
    )

# --- OIDC (ADR-009) --------------------------------------------------------
#
# Registered at startup so a missing issuer is visible immediately, rather than as a
# confusing redirect failure on someone's first login. When it is absent the routes
# still mount and answer 503 — "this server cannot do that yet" — which is a
# deployment state, not a crash.
if _settings.oidc_configured():
    app.state.oauth = auth.build_oauth(_settings)

app.include_router(auth.router)
app.include_router(resolutions_api.router)
app.include_router(board_members_api.router)
app.include_router(agenda_api.router)
app.include_router(meetings_api.router)
app.include_router(packs_api.router)
app.include_router(minutes_api.router)
app.include_router(decisions_api.router)
app.include_router(commitments_api.router)
app.include_router(documents_api.router)
app.include_router(conflicts_api.router)
app.include_router(prep_api.router)
app.include_router(notifications_api.router)

# Domain exceptions map to HTTP centrally (P3 §5.3). Registered once here rather than
# caught in each route, so a new endpoint inherits the right statuses — a 409 for a
# stale write, a 404 for a row RLS hid — without restating any of them.
errors.install_exception_handlers(app)


@app.get("/health")
def health() -> dict:
    """Liveness: the Meridian API process is up and serving."""
    return {"status": "ok", "service": "meridian-api", "version": app.version}


@app.get("/health/engine")
def engine_health() -> dict:
    """Confirms Meridian can reach the frozen Callosum engine as a library.

    We only touch the package handle here — no database, no model call — so this
    stays a fast, dependency-free check that the boundary is wired correctly.

    **It does not report where the engine was loaded from.** It used to return
    `callosum.__file__`, an absolute server path, on an unauthenticated endpoint —
    which tells an anonymous caller the deployment layout and the operating user's
    home directory. The version answers the question this check exists for ("is the
    boundary wired, and to what") without the disclosure.
    """
    return {
        "status": "ok",
        "engine": "callosum",
        "engine_version": callosum.__version__,
    }
