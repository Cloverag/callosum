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

from callosum import graph, llm
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
    workspaces,
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

#: Machine-readable error codes. Stable strings, not HTTP status numbers: the
#: frontend switches on these.
BAD_WORKSPACE = "bad_workspace"
CONFLICT = "conflict"
FORBIDDEN = "forbidden"
INVALID = "invalid"
NOT_FOUND = "not_found"
STALE = "stale_resource"
SERVICE_UNAVAILABLE = "service_unavailable"
INTERNAL = "internal"

_FORBIDDEN_DETAIL = "Not available to you."


# --- Pass 1: explicit type registrations ------------------------------------
#
# These MUST come first. If an exception matches both an explicit entry and a
# naming pattern below, the explicit entry wins.

_EXPLICIT: tuple[tuple[type[BaseException], int, str, str | None], ...] = (
    (PrincipalNotFound, HTTPStatus.FORBIDDEN, FORBIDDEN, _FORBIDDEN_DETAIL),
    (audit.ActorNotInWorkspace, HTTPStatus.FORBIDDEN, FORBIDDEN, _FORBIDDEN_DETAIL),
    # A missing or malformed workspace is the caller's error, not a permission
    # failure — but it must never be a 500, because that is what the fail-open
    # default in store.pg would otherwise have looked like.
    (WorkspaceRequired, HTTPStatus.BAD_REQUEST, BAD_WORKSPACE, None),
    # `InvalidTransition` breaks the suffix convention; it is a lifecycle conflict.
    (meetings.InvalidTransition, HTTPStatus.CONFLICT, CONFLICT, None),
    # Both break the suffix convention too, and both would otherwise fall to the 422
    # default — telling a caller to fix a request that was fine.
    (meetings.MaterialAlreadyAssignedError, HTTPStatus.CONFLICT, CONFLICT, None),
    # 404, and the detail is NOT suppressed to `_FORBIDDEN_DETAIL`: this answer is
    # returned both when the document is not assigned and when it is above the caller's
    # clearance, and it has to look identical in both cases. A distinguishable 403 would
    # make the endpoint an existence oracle — see `meetings.assign_material`.
    (meetings.MaterialNotAssignedError, HTTPStatus.NOT_FOUND, NOT_FOUND, None),
    (documents.DuplicateDocumentError, HTTPStatus.CONFLICT, CONFLICT, None),
    (documents.InvalidSensitivityError, HTTPStatus.UNPROCESSABLE_ENTITY, INVALID, None),
    # 403, not 422: the request is well-formed and the value is in range — the caller
    # simply may not create at that level (#143). The detail is NOT suppressed to
    # `_FORBIDDEN_DETAIL` the way the others are, because the only thing it discloses is
    # the caller's own clearance, which is theirs to know, and without it a client
    # cannot tell them to pick a lower level rather than request access.
    (documents.SensitivityAboveClearanceError, HTTPStatus.FORBIDDEN, FORBIDDEN, None),
    # 409, and it MUST be explicit. `DocumentAlreadySupersededError` carries none of the
    # suffixes pass 2 recognises — no `Stale`, no `Locked` — so without this entry it
    # would fall through to pass 3's 422 and tell the client to fix a request that was
    # correct. The state refused it; the caller's move is to re-read the chain, not to
    # edit their input.
    (documents.DocumentAlreadySupersededError, HTTPStatus.CONFLICT, CONFLICT, None),
    # 403 with the detail intact, for the same reason as the clearance ceiling above: the
    # message names the level being revised, which the caller can already read (they were
    # permitted to read the document to get here), and without it a client cannot tell
    # them to file higher rather than request access.
    (documents.SensitivityDowngradeError, HTTPStatus.FORBIDDEN, FORBIDDEN, None),
    # 403 with the detail intact, for the same reason as the two entries above: the
    # message names the ROLE being requested, which the caller already supplied, and
    # never the acting principal's own clearance or the target's — see the class
    # docstring in workspaces.py for why that distinction matters (#166 step 5).
    (workspaces.EscalationDeniedError, HTTPStatus.FORBIDDEN, FORBIDDEN, None),
    # Infrastructure, not domain. A provider being down or a graph write failing is not
    # the caller's mistake, so 503 rather than a 4xx — see `test_api_errors.py`, which
    # asserts no *domain* exception falls through to a 500. These two are exempt by
    # meaning rather than by module: they are defined outside `meridian.*` precisely so
    # the completeness walk does not claim them as domain errors.
    (llm.EmbeddingProviderError, HTTPStatus.SERVICE_UNAVAILABLE, SERVICE_UNAVAILABLE, None),
    (graph.GraphStoreError, HTTPStatus.SERVICE_UNAVAILABLE, SERVICE_UNAVAILABLE, None),
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
    workspaces,
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
    from fastapi.exceptions import HTTPException, RequestValidationError
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
                else CONFLICT if exc.status_code == 409
                else INVALID if exc.status_code in (400, 422)
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
        workspaces.WorkspaceError,
        PrincipalNotFound,
        WorkspaceRequired,
        llm.EmbeddingProviderError,
        graph.GraphStoreError,
    ]
    for base in bases:
        app.add_exception_handler(base, handle)

    app.add_exception_handler(HTTPException, handle_http_exception)

    # Request-shape failures answered in the SAME envelope as domain failures.
    #
    # Without this, FastAPI replies to a missing field with its own
    # `{"detail": [{"loc": ..., "msg": ...}]}` body, so a client switching on
    # `error.code` — which every surface in this repo does — sees nothing it
    # recognises and reports the error as unknown.
    #
    # This became load-bearing when `sensitivity` stopped having a default (#143): the
    # decision requires a missing value to be refused with a *clear* validation error,
    # and `test_intake_invalid_sensitivity_422` already fixes the shape of that answer
    # for an out-of-range value. A missing one must not answer in a different format
    # than an invalid one.
    async def handle_request_validation(_request, exc: RequestValidationError):
        errors = exc.errors()
        if errors:
            first = errors[0]
            # `loc` is ("body", "sensitivity"); the field name is the tail. Naming the
            # field is the difference between an actionable error and "invalid input".
            location = ".".join(str(part) for part in first.get("loc", ()) if part != "body")
            detail = f"{location}: {first.get('msg', 'invalid value')}" if location else str(first.get("msg", "Invalid request."))
        else:
            detail = "Invalid request."
        return JSONResponse(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            content={"error": {"code": INVALID, "detail": detail}},
        )

    app.add_exception_handler(RequestValidationError, handle_request_validation)
