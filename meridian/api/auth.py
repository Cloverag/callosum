"""OIDC login, callback and logout (P3, CP-A/A3 — ADR-009, ADR-010, ADR-011).

Keycloak is the reference provider, but nothing here is Keycloak-specific: endpoints
are discovered from `{issuer}/.well-known/openid-configuration`, so swapping in Auth0,
Okta or Entra is configuration rather than code.

The flow, and where each ADR lands:

    GET /auth/login     -> redirect to the provider
    GET /auth/callback  <- provider returns a code
                           authlib exchanges it and VALIDATES the id_token
                           `sub` -> principal_id            (ADR-010)
                           unprovisioned subject -> 403      (ADR-011)
                           identity written to the session   (ADR-009)
    POST /auth/logout   -> clear the session
    GET  /auth/me       -> who the session says you are

**No workspace is selected here.** A successful login leaves the session holding an
identity and nothing else; choosing a workspace is A4, and it is a separate step
precisely because a principal may hold several memberships and must not be guessed
into one (ADR-012).

**Nothing in this module resolves clearance.** It maps a subject to a principal id and
stops. Clearance comes from a membership, per request, once a workspace exists.
"""

from typing import Any

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse

from callosum import store
from callosum.identity import IdentityNotProvisioned, resolve_identity
from meridian.api import session as sess
from meridian.api.config import ApiSettings, api_settings

router = APIRouter(prefix="/auth", tags=["auth"])

#: Registration name for the provider inside authlib's registry.
_OIDC = "meridian_oidc"


def build_oauth(settings: ApiSettings) -> OAuth:
    """Registers the provider from its discovery document.

    Discovery rather than hard-coded endpoints: it keeps this provider-agnostic, and
    it means the JWKS URL used to verify id_token signatures comes from the issuer
    rather than from our configuration — one fewer thing to get wrong.
    """
    oauth = OAuth()
    oauth.register(
        name=_OIDC,
        server_metadata_url=f"{settings.oidc_issuer.rstrip('/')}/.well-known/openid-configuration",
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
        client_kwargs={
            "scope": settings.oidc_scopes,
            # PKCE. The Keycloak client in keycloak/realm-dev.json sets
            # `pkce.code.challenge.method: S256`, which makes the provider *require*
            # a code challenge — without this the redirect omits one and Keycloak
            # rejects the exchange. Found by running the flow against a live realm;
            # a stubbed client cannot surface a provider-side requirement.
            #
            # Worth having regardless of the provider: it binds the authorization
            # code to the session that requested it, so an intercepted code is
            # useless to anyone else.
            "code_challenge_method": "S256",
        },
    )
    return oauth


def _client(request: Request):
    """The registered OIDC client, or a 503 if auth was never configured.

    503 rather than 500: an unconfigured issuer is a deployment state, not a bug, and
    it should read as "this server cannot do that yet" rather than as a crash.
    """
    oauth: OAuth | None = getattr(request.app.state, "oauth", None)
    if oauth is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured on this server.",
        )
    return oauth.create_client(_OIDC)


@router.get("/login")
async def login(request: Request):
    """Starts the authorization-code flow.

    `authorize_redirect` puts the `state` and PKCE verifier in the session, which is
    what the callback checks the provider's response against. That is why the session
    middleware has to be installed even for an anonymous request.
    """
    client = _client(request)
    settings = api_settings()
    return await client.authorize_redirect(request, settings.oidc_redirect_url)


@router.get("/callback")
async def callback(request: Request):
    """Completes the flow and establishes the session.

    `authorize_access_token` does the exchange **and** validates the id_token —
    signature against the issuer's JWKS, plus `iss`, `aud`, `exp` and the `nonce`. The
    claims are only trusted after that returns.
    """
    client = _client(request)
    settings = api_settings()

    try:
        token = await client.authorize_access_token(request)
    except OAuthError as exc:
        # A failed exchange is the caller's problem (bad or replayed code, state
        # mismatch), not the server's. `exc.description` is the provider's message and
        # is safe to relay; it is about the request that was just made.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc.description or exc)) from exc

    claims: dict[str, Any] = token.get("userinfo") or {}
    subject = claims.get("sub")
    issuer = claims.get("iss") or settings.oidc_issuer

    if not subject:
        # Every OIDC provider must return `sub`. Its absence means the token is not
        # what we think it is, and continuing would mean authenticating nobody.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Identity provider returned no subject claim."
        )

    # The issuer is taken from the VALIDATED token, not from configuration, so the
    # (provider, subject) pair stored is the one the provider actually asserted.
    with store.pg(store.DEFAULT_WORKSPACE_ID) as conn:
        # `principal_identity` has no tenant column and no RLS (ADR-010) — login runs
        # before a workspace exists, so the workspace passed here is incidental and
        # scopes nothing. It is required only because `store.pg` takes one.
        try:
            principal_id = resolve_identity(conn, issuer, subject)
        except IdentityNotProvisioned as exc:
            # ADR-011. The provider authenticated them; this system has no record of
            # them, and login does not create one. Safe to be specific: they proved
            # control of this subject, so they learn only about their own account.
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Your identity is not provisioned for this workspace. Ask an administrator.",
            ) from exc

    sess.establish(request.session, principal_id=str(principal_id), provider=issuer, subject=subject)

    # A workspace is NOT selected here (ADR-012). The next step is A4.
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/logout")
async def logout(request: Request):
    """Ends the local session.

    Deliberately does not perform provider-side single logout. Ending the Keycloak SSO
    session too is a product decision — it would sign the user out of every
    application sharing that realm — and it is not this checkpoint's to make.
    """
    sess.clear(request.session)
    return JSONResponse({"status": "logged_out"})


@router.get("/me")
async def me(request: Request):
    """What the session claims, with no authorization attached.

    Returns the identity and the selected workspace if there is one. It deliberately
    does **not** return clearance: clearance is per-workspace, resolved per request,
    and reporting it from a session read would be reporting a cached authorization.
    """
    current = sess.read(request.session)
    if current is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")

    return {
        "principal_id": current.principal_id,
        "provider": current.provider,
        "workspace_id": current.workspace_id,
        "workspace_selected": current.workspace_id is not None,
    }
