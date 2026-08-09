"""What a logged-in session holds, and what it deliberately does not (P3, CP-A/A3).

ADR-009 settled the transport: an httpOnly, `SameSite=Lax`, signed cookie. This module
settles the *contents*, which matters more.

---------------------------------------------------------------------------
THE SESSION HOLDS AN IDENTITY. IT NEVER HOLDS AN AUTHORIZATION.
---------------------------------------------------------------------------

Stored: `principal_id`, and the `(provider, subject)` it was resolved from.

**Not stored: `clearance`.** It is a property of a membership, and memberships change.
A clearance copied into a cookie is a snapshot of an authorization decision that keeps
being true after the fact stops being true — a director demoted from confidential to
investor would keep reading confidential material until their session expired. Every
request re-derives clearance through `resolve_principal_by_id()`, which costs one
indexed JOIN.

**Not stored: `workspace_id` as an authorization.** A4 writes the *selection* here, but
ADR-012 requires it be re-validated against `membership` on every request, for the same
reason: a revoked membership must stop working immediately, not at session expiry.

The rule in one line: the session says *who you claim to be*, the database says *what
that lets you do*. Anything cached in the cookie is a fact that cannot be revoked.
"""

import time
from dataclasses import dataclass
from typing import Any

#: Session keys. Named constants because they are read in three places and a typo in
#: any of them would silently produce a logged-out request rather than an error.
PRINCIPAL_ID = "principal_id"
PROVIDER = "auth_provider"
SUBJECT = "auth_subject"
WORKSPACE_ID = "workspace_id"
CREATED_AT = "auth_created_at"

#: Maximum session lifetime (24 hours in seconds).
MAX_SESSION_LIFETIME_SECONDS = 86400.0


@dataclass(frozen=True)
class AuthenticatedSession:
    """Who the caller claims to be, and — once A4 lands — which workspace they chose.

    Deliberately not a `Principal`. That type carries `clearance`, lives in the frozen
    `retrieve.py`, and is what the RBAC gate consumes; constructing one from cookie
    contents would mean authorization derived from something the client holds. A
    `Principal` is built per request from the database, using `principal_id` here as
    the input.
    """

    principal_id: str
    provider: str
    subject: str
    #: `None` until a workspace is selected (A4). Never trusted without re-validation.
    workspace_id: str | None = None


def establish(session: dict[str, Any], *, principal_id: str, provider: str, subject: str) -> None:
    """Writes an authenticated identity into the session.

    Called once, from the OIDC callback, after the subject has been resolved to a
    provisioned principal. Any previous workspace selection is cleared: a new login is
    a new session, and carrying a stale selection across one would let a workspace
    outlive the membership that justified it.
    """
    session[PRINCIPAL_ID] = str(principal_id)
    session[PROVIDER] = provider
    session[SUBJECT] = subject
    session[CREATED_AT] = time.time()
    session.pop(WORKSPACE_ID, None)


def read(session: dict[str, Any]) -> AuthenticatedSession | None:
    """Reads the session, or `None` if it does not hold a complete identity.

    Partial sessions are treated as absent rather than repaired. A cookie carrying a
    `principal_id` but no provider is not a half-valid login, it is something
    unexpected — and guessing at its meaning is how an edge case becomes a bypass.
    """
    principal_id = session.get(PRINCIPAL_ID)
    provider = session.get(PROVIDER)
    subject = session.get(SUBJECT)
    created_at = session.get(CREATED_AT)

    if not principal_id or not provider or not subject:
        return None

    # Enforce absolute session expiry (H-8)
    if created_at is not None and (time.time() - float(created_at)) > MAX_SESSION_LIFETIME_SECONDS:
        session.clear()
        return None

    return AuthenticatedSession(
        principal_id=str(principal_id),
        provider=str(provider),
        subject=str(subject),
        workspace_id=session.get(WORKSPACE_ID) or None,
    )


def select_workspace(session: dict[str, Any], workspace_id: str) -> None:
    """Records a workspace choice (A4 uses this).

    Recording is not authorizing. The value written here is re-checked against
    `membership` on every request that uses it — ADR-012.
    """
    session[WORKSPACE_ID] = str(workspace_id)


def clear(session: dict[str, Any]) -> None:
    """Empties the session on logout.

    Clears every key rather than the ones this module knows about, so a key added
    elsewhere cannot survive a logout and quietly outlive the identity that put it
    there.
    """
    session.clear()
