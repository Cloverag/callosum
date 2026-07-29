"""Meridian API settings (P3, CP-A/A3).

Product-side, deliberately separate from `callosum.config`. The frozen core's
settings describe the engine — providers, models, stores. These describe the *web
application*, which the engine knows nothing about. Adding OIDC fields to the frozen
config would have made the research core aware of a browser session.

**Nothing here has a working default.** Every OIDC value is empty until the
environment supplies it, and `oidc_configured()` reports whether it did. A default
issuer or a placeholder secret is how a misconfigured deployment silently
authenticates against the wrong thing.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="MERIDIAN_")

    # --- OIDC (ADR-009) ----------------------------------------------------
    #
    # Keycloak is the reference provider — self-hostable, so the whole auth path can
    # be exercised locally without an account at a SaaS IdP, and standards-compliant
    # enough that swapping it for Auth0 or Okta is configuration rather than code.
    #
    # `oidc_issuer` is the base realm URL. Authlib discovers the authorization,
    # token and JWKS endpoints from `{issuer}/.well-known/openid-configuration`, so
    # nothing here hard-codes a provider's URL shape.
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""

    #: Where the provider sends the browser back. Must match the client's registered
    #: redirect URI exactly — providers reject a mismatch, which is the point.
    oidc_redirect_url: str = "http://localhost:8000/auth/callback"

    #: Scopes requested at login. `openid` is mandatory; `profile` and `email` are
    #: requested for display only. **Neither is used to identify anyone** — that is
    #: `sub`, per ADR-010, because email is mutable and reassignable.
    oidc_scopes: str = "openid profile email"

    # --- Session (ADR-009) -------------------------------------------------
    #
    # Signs the session cookie. No default: an unset secret would mean every
    # deployment shares one, and a signing key everybody knows signs nothing.
    session_secret: str = ""

    session_cookie_name: str = "meridian_session"

    #: Seconds. Short by web standards on purpose — the session carries a
    #: `principal_id` and every request re-derives authorization from it, so a
    #: shorter life costs a re-login rather than stale access.
    session_max_age: int = 60 * 60 * 8

    #: `Lax` rather than `Strict`: the OIDC callback is a cross-site GET redirect
    #: back from the provider, and `Strict` would withhold the cookie on exactly that
    #: navigation, breaking login. `Lax` still blocks cross-site POSTs, which is the
    #: CSRF case that matters.
    session_same_site: str = "lax"

    #: Set false only for local HTTP development. Cookies must be Secure in anything
    #: reachable over a network.
    session_https_only: bool = True

    def oidc_configured(self) -> bool:
        """True when enough is set to attempt a login.

        Checked at startup so a missing issuer surfaces as a clear refusal to enable
        auth, rather than as a confusing redirect failure on someone's first login.
        """
        return bool(self.oidc_issuer and self.oidc_client_id and self.oidc_client_secret)

    def session_configured(self) -> bool:
        return bool(self.session_secret)


@lru_cache
def api_settings() -> ApiSettings:
    return ApiSettings()
