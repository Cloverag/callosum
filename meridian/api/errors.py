"""Domain exception → HTTP status, in one place (Meridian P3, §5.3).

Every endpoint needs this and no endpoint should own a copy of it. A mapping
scattered across route handlers drifts: one returns 400 where another returns 422 for
the same failure, and a client cannot tell a retryable conflict from a bad request.

Three things shape the design.

**Mapped by type, not by name.** `DecisionNotFound` exists as three *different*
classes — in `decisions.py`, `resolutions.py` and `commitments.py` — and
`BoardMemberNotFound` and `ResolutionNotFound` likewise. A dict keyed on class name
would silently collapse them; `isinstance` against the actual classes cannot.

**A structural fallback, so the map cannot rot.** There are 48 domain exception
classes today and every future checkpoint adds more. An unregistered exception falling
through to a 500 is a taxonomy that quietly stops working, so the naming conventions
this codebase already follows — `Stale*`, `*NotFound`, `*Locked*`, `*Validation*` —
are honoured as a second pass. A new `StaleWidgetError` maps correctly on the day it
is written.

**Authorization failures do not explain themselves.** `PrincipalNotFound` deliberately
conflates "no such person" with "not a member here" to avoid a membership oracle;
echoing its message back would undo that at the HTTP boundary. Those get a fixed
string. Domain errors keep their detail, because "title must not be empty" and
"expected version 3, current 4" are exactly what the caller needs.
"""

from dataclasses import dataclass
from http import HTTPStatus

from callosum.identity import PrincipalNotFound
from meridian import (
    agenda,
    audit,
    board_members,
    commitments,
    decisions,
    documents,
    meetings,
    minutes,
    packs,
    resolutions,
)
from meridian.tenancy import WorkspaceRequired

# --- The wire shape --------------------------------------------------------


@dataclass(frozen=True)
class ApiError:
    """What an endpoint returns when a domain call raises.

    `code` is the machine-readable half. A client needs to distinguish "refetch and
    retry" from "fix your input" without parsing prose, and both are 4xx.
    """

    status: int
    code: str
    detail: str

    def as_response(self) -> dict:
        return {"error": {"code": self.code, "detail": self.detail}}


# --- Codes -----------------------------------------------------------------

NOT_FOUND = "not_found"
STALE = "stale_resource"
CONFLICT = "conflict"
INVALID = "invalid"
FORBIDDEN = "forbidden"
BAD_WORKSPACE = "workspace_required"
INTERNAL = "internal"

#: What a caller is told when authorization fails, regardless of why.
_FORBIDDEN_DETAIL = "Not available to you."


# --- Pass 1: explicit, for anything needing more than its suffix implies ----

_EXPLICIT: tuple[tuple[type[BaseException], int, str, str | None], ...] = (
    # Authorization. Fixed detail: the exception message names the principal the
    # caller asked about, and the whole point of PrincipalNotFound is that "unknown"
    # and "not a member" are indistinguishable.
    (PrincipalNotFound, HTTPStatus.FORBIDDEN, FORBIDDEN, _FORBIDDEN_DETAIL),
    (audit.ActorNotInWorkspace, HTTPStatus.FORBIDDEN, FORBIDDEN, _FORBIDDEN_DETAIL),
    # A missing or malformed workspace is the caller's error, not a permission
    # failure — but it must never be a 500, because that is what the fail-open
    # default in store.pg would otherwise have looked like.
    (WorkspaceRequired, HTTPStatus.BAD_REQUEST, BAD_WORKSPACE, None),
    # `InvalidTransition` breaks the suffix convention; it is a lifecycle conflict.
    (meetings.InvalidTransition, HTTPStatus.CONFLICT, CONFLICT, None),
)


# --- Pass 2: the naming conventions this codebase already follows -----------
#
# Checked most-specific-first. `StaleBoardPackError` must match `Stale` before it
# would match anything else, and `*ValidationError` before a bare `*Error`.

_BY_NAME: tuple[tuple[tuple[str, ...], int, str], ...] = (
    (("Stale",), HTTPStatus.CONFLICT, STALE),
    (("NotFound",), HTTPStatus.NOT_FOUND, NOT_FOUND),
    (("Locked",), HTTPStatus.CONFLICT, CONFLICT),
    (("Validation",), HTTPStatus.UNPROCESSABLE_ENTITY, INVALID),
)

#: Every module whose exceptions this taxonomy claims to cover. The completeness
#: test walks these, so adding a module without adding it here fails loudly.
COVERED_MODULES = (
    agenda,
    audit,
    board_members,
    commitments,
    decisions,
    documents,
    meetings,
    minutes,
    packs,
    resolutions,
)


def classify(exc: BaseException) -> ApiError:
    """Maps a domain exception to its HTTP representation.

    Anything unrecognised becomes a 500 with no detail — an unexpected exception must
    not leak an internal message to a client, and the completeness test exists so this
    branch is not reached by a *domain* error.
    """
    for exc_type, status, code, fixed_detail in _EXPLICIT:
        if isinstance(exc, exc_type):
            return ApiError(int(status), code, fixed_detail or str(exc))

    name = type(exc).__name__
    for needles, status, code in _BY_NAME:
        if any(needle in name for needle in needles):
            # Detail passes through: "expected version 3, current 4" is precisely what
            # a client needs in order to refetch and retry.
            return ApiError(int(status), code, str(exc))

    # Pass 3: a domain exception that matched no convention.
    #
    # The per-aggregate base classes (`MeetingError`, `BoardPackError`, …) land here:
    # they end in `Error` but carry none of the specific suffixes, and nothing raises
    # them directly. A handler that catches a base class must still get a 4xx, and a
    # future subclass named off-convention should degrade to "you did something the
    # domain refused" rather than "the server broke".
    #
    # Scoped by module rather than by name, because `RuntimeError` also ends in
    # `Error` and must NOT be laundered into a 4xx — an unexpected failure is a 500,
    # and only exceptions this package defines get the benefit of the doubt.
    if _is_domain_exception(exc):
        return ApiError(int(HTTPStatus.UNPROCESSABLE_ENTITY), INVALID, str(exc))

    return ApiError(int(HTTPStatus.INTERNAL_SERVER_ERROR), INTERNAL, "Internal error.")


def _is_domain_exception(exc: BaseException) -> bool:
    """True for exceptions defined by this product or by the identity module.

    Deliberately module-based. A name-based check would sweep in `RuntimeError`,
    `ValueError` and every psycopg error, turning genuine internal failures into 4xx
    responses that tell a client to fix input it got right.
    """
    module = type(exc).__module__ or ""
    return module.startswith("meridian.") or module == "callosum.identity"


def status_for(exc: BaseException) -> int:
    """Convenience for handlers that only need the code."""
    return classify(exc).status


def install_exception_handlers(app) -> None:
    """Registers `classify()` as the app's handler for every domain exception.

    Without this each endpoint would need its own try/except, and the mapping would
    drift the moment one route caught something a sibling did not — the exact
    scattering this module exists to prevent. Registering centrally also means CP-C's
    endpoints inherit correct statuses without doing anything.

    Handlers are attached to the *base* classes. Starlette dispatches on the closest
    registered ancestor, so `StaleResolutionError` is caught by the `ResolutionError`
    handler and `IdentityNotProvisioned` by the `PrincipalNotFound` one — subclasses
    added later are covered without being registered.
    """
    from fastapi.exceptions import HTTPException
    from fastapi.responses import JSONResponse

    async def handle(_request, exc: BaseException):
        mapped = classify(exc)
        return JSONResponse(status_code=mapped.status, content=mapped.as_response())

    async def handle_http_exception(_request, exc: HTTPException):
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            code = exc.detail["code"]
            detail = exc.detail.get("detail", str(exc.detail))
        else:
            code = (
                FORBIDDEN if exc.status_code == 403
                else "unauthorized" if exc.status_code == 401
                else BAD_WORKSPACE if exc.status_code == 409
                else INVALID if exc.status_code == 422
                else INTERNAL
            )
            detail = str(exc.detail) if exc.detail else "An error occurred."
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": code, "detail": detail}},
        )

    bases: list[type[BaseException]] = [
        agenda.AgendaItemError,
        audit.AuditValidationError,
        board_members.BoardMemberError,
        commitments.CommitmentError,
        decisions.DecisionError,
        documents.DocumentError,
        meetings.MeetingError,
        minutes.MinutesError,
        packs.BoardPackError,
        resolutions.ResolutionError,
        PrincipalNotFound,
        WorkspaceRequired,
    ]
    for base in bases:
        app.add_exception_handler(base, handle)

    app.add_exception_handler(HTTPException, handle_http_exception)
