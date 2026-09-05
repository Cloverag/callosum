"""The demo principal selector: a third caller of `session.establish()`.

WHAT THIS IS
------------
A public demo needs a visitor to switch between seeded principals and watch the same
request return different material. What OIDC actually provides is one thing — an
*identity assertion*, "this browser belongs to subject X". This route replaces that one
step and nothing else.

    identity assertion   <- Keycloak provides this; THIS ROUTE replaces only this
    ----------------------------------------------------------------------------
    session write        <- meridian.api.session, unchanged
    principal resolve    <- identity.resolve_principal_by_id, unchanged
    workspace verify     <- deps.current_workspace, unchanged
    clearance derive     <- membership.role -> ROLE_TO_CLEARANCE, unchanged
    RLS scoping          <- store.pg(workspace_id), unchanged
    row filtering        <- d.sensitivity <= clearance, in SQL, unchanged

It is therefore not a second authentication implementation. It constructs no
`Principal`, reads neither `principal.role` nor `principal.clearance`, and passes a
clearance to nothing. `auth.callback` and `auth.select_workspace` already write to the
session; this is the third such caller, not a new mechanism.

THE BROWSER CANNOT NAME A PRINCIPAL
-----------------------------------
The request body carries a *symbol* — `founder`, `exec`, `investor` — typed as a
`Literal`, so FastAPI rejects anything else with 422 before this module runs. There is
no `principal_id` field to inject. The symbol is mapped to an email on the server, from
`callosum.cli.DEMO_PRINCIPALS`, and the id is looked up in the database.

WHY THE GUARD IS NOT `_dev_auto_auth_enabled()`'s
-------------------------------------------------
That helper requires an explicitly non-production environment. The demo deployment pins
`ENVIRONMENT=production` (it is a public host), so reusing it would leave the selector
permanently off exactly where it is needed. An earlier draft of this design said to
reuse it; that was wrong.

Instead: one explicit flag, absent by default. Enabling it means **anyone who can reach
this route may assume any listed identity**. That is acceptable only because the demo
database holds fabricated board minutes. It must never be set against real data, and the
flag is named to say so.
"""

import os
from typing import Literal

import psycopg
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from callosum import store
from callosum.cli import DEMO_PRINCIPALS
from callosum.config import settings as core_settings
from callosum.identity import PrincipalNotFound, resolve_principal_by_id
from meridian.api import deps
from meridian.api import session as sess

router = APIRouter(prefix="/auth/demo", tags=["demo"])

#: The env var that turns this on. Absent means off — the state every environment
#: starts in, and the only safe default for a route that hands out identities.
FLAG = "MERIDIAN_DEMO_SELECTOR"

_TRUTHY = frozenset({"true", "1", "yes"})

#: Symbol -> email, derived from the seed rather than restated. If a demo principal's
#: role is renamed, this raises at import instead of silently offering a symbol that
#: resolves to nobody.
_EMAIL_BY_ROLE = {role: email for _name, email, role, _clr, _org in DEMO_PRINCIPALS}
DemoIdentity = Literal["founder", "exec", "investor"]
IDENTITY_EMAILS: dict[str, str] = {r: _EMAIL_BY_ROLE[r] for r in ("founder", "exec", "investor")}

#: Display labels only. Deliberately no role and no clearance: publishing those beside
#: the names turns the picker into a directory of who can see what.
IDENTITY_LABELS: dict[str, str] = {
    "founder": "Founder",
    "exec": "Exec",
    "investor": "Investor",
}


class DemoSelection(BaseModel):
    identity: DemoIdentity


def selector_enabled() -> bool:
    """**Fail-closed.** Unset, empty or unrecognised all mean off."""
    return os.environ.get(FLAG, "").strip().lower() in _TRUTHY


def _require_enabled() -> None:
    """404 rather than 503 when disabled.

    `main.py` answers 503 for unconfigured OIDC, because a login route that exists but
    is not wired up is a deployment state worth reporting. This one is different: a
    disabled impersonation endpoint should not announce that it exists.
    """
    if not selector_enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "not_found"})


@router.get("/identities")
def list_identities() -> dict[str, list[dict[str, str]]]:
    """The symbols a visitor may pick. Names only — no roles, no clearances."""
    _require_enabled()
    return {
        "identities": [
            {"symbol": s, "label": IDENTITY_LABELS[s]} for s in IDENTITY_EMAILS
        ]
    }


@router.post("/select")
def select_identity(request: Request, selection: DemoSelection) -> dict[str, str]:
    """Establishes a session for one seeded demo principal.

    Fail-closed on exactly the terms every other request uses: the id is verified
    through `resolve_principal_by_id`, which JOINs an *active* membership, so a
    principal who was never seeded or whose membership was revoked does not resolve and
    no session is written. The refusal is uniform.

    `provider="demo-selector"` is deliberate and load-bearing. The auto-auth bypass this
    project fixed in #191 defaulted `provider` to a Keycloak issuer URL and `subject` to
    an email, so audit records claimed an OIDC login that never happened. A demo session
    says it is a demo session.
    """
    _require_enabled()

    email = IDENTITY_EMAILS[selection.identity]

    with psycopg.connect(core_settings().postgres_dsn, row_factory=psycopg.rows.dict_row) as admin:
        row = admin.execute("SELECT id FROM principal WHERE email = %s", (email,)).fetchone()

    if row is None:
        # The demo database has not been seeded. Not the caller's fault and not a
        # permissions answer, so it is not a 403.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "not_seeded",
                    "detail": "Demo principals are not seeded; run `callosum init`."},
        )

    principal_id = str(row["id"])

    try:
        with store.pg(store.DEFAULT_WORKSPACE_ID) as conn:
            resolve_principal_by_id(conn, principal_id, workspace_id=store.DEFAULT_WORKSPACE_ID)
    except PrincipalNotFound as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"code": deps.FORBIDDEN, "detail": "Not available to you."},
        ) from exc

    try:
        raw = request.session
    except AssertionError as exc:
        # `SessionMiddleware` is installed only when a signing secret is configured
        # (`api/main.py`), so writing a session without one raises an `AssertionError`
        # — a 500, for a configuration problem the operator fixes in one line.
        # `deps.current_session` already answers 503 for exactly this; a route that
        # WRITES the session needs the same treatment as one that reads it.
        #
        # Found by CI, not locally: a developer `.env` supplies the secret, so the
        # middleware is always installed here and this path never ran.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": deps.SESSION_NOT_CONFIGURED,
                "detail": "Sessions are not configured on this server; set MERIDIAN_SESSION_SECRET.",
            },
        ) from exc

    sess.establish(
        raw,
        principal_id=principal_id,
        provider="demo-selector",
        subject=email,
    )
    sess.select_workspace(raw, store.DEFAULT_WORKSPACE_ID)

    # Echoes the symbol and the provider marker, and nothing else. `auth.select_workspace`
    # returns `clearance` and `role`; this deliberately does not. Those are authorization
    # facts, and a public demo picker that reports them hands a visitor the model for
    # free. The UI learns what this identity may see the same way every other caller
    # does — by making the next request.
    return {"identity": selection.identity, "provider": "demo-selector"}
