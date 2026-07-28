"""Coverage for the HTTP error taxonomy (`meridian/api/errors.py`, P3 §5.3).

Pure mapping tests — no database, no HTTP server.

The load-bearing test is `test_every_domain_exception_maps`, which discovers the
exception classes by walking the modules rather than listing them. A hand-written list
would go stale the first time a checkpoint adds an aggregate, and the failure mode of a
stale taxonomy is a 500 where a 409 belonged.
"""

import inspect

import pytest

from callosum.identity import IdentityNotProvisioned, PrincipalNotFound
from meridian import (
    agenda,
    audit,
    board_members,
    commitments,
    decisions,
    meetings,
    minutes,
    packs,
    resolutions,
)
from meridian.api.errors import (
    BAD_WORKSPACE,
    CONFLICT,
    COVERED_MODULES,
    FORBIDDEN,
    INVALID,
    NOT_FOUND,
    STALE,
    ApiError,
    classify,
    status_for,
)
from meridian.tenancy import WorkspaceRequired


def _domain_exceptions(module) -> list[type[BaseException]]:
    """Every exception class *defined in* this module (not imported into it)."""
    return [
        obj
        for _, obj in inspect.getmembers(module, inspect.isclass)
        if issubclass(obj, BaseException) and obj.__module__ == module.__name__
    ]


class TestCompleteness:
    def test_the_modules_actually_define_exceptions(self):
        # Guards the guard: if the discovery helper silently found nothing, the
        # completeness test below would pass vacuously.
        total = sum(len(_domain_exceptions(m)) for m in COVERED_MODULES)
        assert total >= 40, f"expected the P2 aggregates' exception classes, found {total}"

    @pytest.mark.parametrize("module", COVERED_MODULES, ids=lambda m: m.__name__)
    def test_every_domain_exception_maps(self, module):
        """No domain exception may fall through to a 500.

        Discovered by walking the module, so a new aggregate's exceptions are covered
        the day they are written — or this fails and says which one is not.
        """
        for exc_type in _domain_exceptions(module):
            mapped = classify(exc_type("something went wrong"))
            assert mapped.status != 500, (
                f"{module.__name__}.{exc_type.__name__} falls through to 500; "
                "add it to _EXPLICIT or give it a conventional name"
            )
            assert 400 <= mapped.status < 500

    def test_the_base_error_classes_map_too(self):
        """`DecisionError` and friends are raised by nothing directly, but a handler
        catching a base class must still get a sane status rather than a 500."""
        for module in COVERED_MODULES:
            for exc_type in _domain_exceptions(module):
                if exc_type.__name__.endswith("Error") and "Validation" not in exc_type.__name__:
                    assert classify(exc_type("x")).status != 500


class TestStaleIsA409:
    """The mapping the frontend depends on most.

    A stale write is retryable — refetch, re-apply, resubmit. A 500 would tell the UI
    nothing was wrong with the request, and a 400 would tell it not to retry. Only 409
    says "your copy is out of date", which is the one thing that is true.
    """

    @pytest.mark.parametrize(
        "exc",
        [
            meetings.StaleMeetingError("meeting x: expected version 3, current 4"),
            agenda.StaleAgendaItemError("x"),
            packs.StaleBoardPackError("x"),
            minutes.StaleMinutesError("x"),
            decisions.StaleDecisionError("x"),
            board_members.StaleBoardMemberError("x"),
            resolutions.StaleResolutionError("x"),
            commitments.StaleCommitmentError("x"),
        ],
        ids=lambda e: type(e).__name__,
    )
    def test_every_stale_exception_is_409(self, exc):
        mapped = classify(exc)
        assert mapped.status == 409
        assert mapped.code == STALE

    def test_the_version_detail_survives(self):
        """The client needs the numbers to decide what to refetch."""
        exc = meetings.StaleMeetingError("meeting x: expected version 3, current 4")
        assert "expected version 3, current 4" in classify(exc).detail


class TestTheOtherStatuses:
    @pytest.mark.parametrize(
        "exc,status,code",
        [
            (meetings.MeetingNotFound("x"), 404, NOT_FOUND),
            (resolutions.ResolutionNotFound("x"), 404, NOT_FOUND),
            (commitments.CommitmentNotFound("x"), 404, NOT_FOUND),
            (packs.BoardPackLockedError("x"), 409, CONFLICT),
            (minutes.MinutesLockedError("x"), 409, CONFLICT),
            (commitments.CommitmentLockedError("x"), 409, CONFLICT),
            (meetings.InvalidTransition("draft -> completed"), 409, CONFLICT),
            (decisions.DecisionValidationError("bad"), 422, INVALID),
            (audit.AuditValidationError("bad"), 422, INVALID),
            (WorkspaceRequired("missing"), 400, BAD_WORKSPACE),
        ],
        ids=lambda v: v if isinstance(v, (int, str)) else type(v).__name__,
    )
    def test_status_and_code(self, exc, status, code):
        mapped = classify(exc)
        assert (mapped.status, mapped.code) == (status, code)

    def test_invalid_transition_is_a_conflict_despite_its_name(self):
        """It breaks the suffix convention, so it is mapped explicitly.

        "Invalid" in the name would otherwise pull it to 422, but a rejected lifecycle
        move is a conflict with current state, not a malformed request.
        """
        assert classify(meetings.InvalidTransition("x")).status == 409


class TestAuthorizationDoesNotExplainItself:
    """`PrincipalNotFound` conflates "no such person" with "not a member here" so it
    cannot be used as a membership oracle. Echoing its message at the HTTP boundary
    would undo that."""

    @pytest.mark.parametrize(
        "exc",
        [
            PrincipalNotFound("Raj Malhotra"),
            audit.ActorNotInWorkspace("11111111-1111-1111-1111-111111111111"),
            # Subclass of PrincipalNotFound. The taxonomy matches on isinstance, so a
            # new subclass inherits the right status without being registered — which
            # is the property that keeps the map from rotting as auth grows.
            IdentityNotProvisioned("no principal is provisioned for that identity"),
        ],
        ids=lambda e: type(e).__name__,
    )
    def test_is_403_with_a_fixed_detail(self, exc):
        mapped = classify(exc)
        assert mapped.status == 403
        assert mapped.code == FORBIDDEN
        assert mapped.detail == "Not available to you."

    def test_the_subject_never_reaches_the_client(self):
        mapped = classify(PrincipalNotFound("Raj Malhotra"))
        assert "Raj" not in mapped.detail
        assert "Raj" not in str(mapped.as_response())


class TestUnknownExceptions:
    def test_an_unexpected_exception_is_a_500_with_no_detail(self):
        # An internal message must not reach a client. The completeness test is what
        # keeps *domain* errors out of this branch.
        mapped = classify(RuntimeError("connection string: postgres://user:hunter2@db"))
        assert mapped.status == 500
        assert "hunter2" not in mapped.detail
        assert mapped.detail == "Internal error."


class TestWireShape:
    def test_response_body_is_stable(self):
        err = ApiError(409, STALE, "expected version 3, current 4")
        assert err.as_response() == {
            "error": {"code": STALE, "detail": "expected version 3, current 4"}
        }

    def test_status_for_agrees_with_classify(self):
        exc = packs.StaleBoardPackError("x")
        assert status_for(exc) == classify(exc).status
