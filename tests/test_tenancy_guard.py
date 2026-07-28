"""Coverage for the fail-closed workspace guard (`meridian/tenancy.py`, P3 §5.1).

These are pure-validation tests and run in the fast suite — no database needed for
most of them, which is the point: the guard has to reject bad input before anything
opens a connection.

The behaviour under test is a *negative* one. `store.pg()` turns a missing workspace
into the Default Workspace, so every case here asserts that the guard raises where the
frozen helper would have silently succeeded.
"""

import uuid

import pytest

from callosum import store
from meridian.tenancy import (
    WorkspaceRequired,
    is_default_workspace,
    require_workspace,
)


class TestRejectsWhatStoreWouldHaveDefaulted:
    """Each of these reaches `store.pg()` as a Default Workspace read, unguarded."""

    def test_none_is_refused(self):
        with pytest.raises(WorkspaceRequired):
            require_workspace(None)

    def test_empty_string_is_refused(self):
        with pytest.raises(WorkspaceRequired):
            require_workspace("")

    def test_whitespace_only_is_refused(self):
        # `store.pg("   ")` would not default — it would set a nonsense GUC and match
        # no rows. Still wrong, and still better caught here.
        with pytest.raises(WorkspaceRequired):
            require_workspace("   ")

    def test_a_non_uuid_string_is_refused(self):
        for bad in ("default", "1", "workspace-a", "00000000-0000-0000-0000"):
            with pytest.raises(WorkspaceRequired):
                require_workspace(bad)

    def test_a_wrong_type_is_refused(self):
        for bad in (1, 1.5, [], {}, object()):
            with pytest.raises(WorkspaceRequired):
                require_workspace(bad)

    def test_the_frozen_helper_really_does_default(self):
        """Pins the behaviour this guard exists for.

        If `store.pg()` ever stops defaulting, this fails and the guard can be
        reconsidered — better than the guard quietly outliving its reason.
        """
        import inspect

        source = inspect.getsource(store.pg)
        assert "or DEFAULT_WORKSPACE_ID" in source, (
            "store.pg no longer defaults a missing workspace; re-evaluate this guard"
        )


class TestAcceptsAndCanonicalises:
    def test_a_uuid_object_is_accepted(self):
        ws = uuid.uuid4()
        assert require_workspace(ws) == str(ws)

    def test_a_uuid_string_is_accepted(self):
        ws = str(uuid.uuid4())
        assert require_workspace(ws) == ws

    def test_surrounding_whitespace_is_tolerated(self):
        ws = str(uuid.uuid4())
        assert require_workspace(f"  {ws}  ") == ws

    def test_variant_spellings_collapse_to_one_value(self):
        """Two spellings must not become two different `app.workspace_id` values.

        Uppercase, braced and urn forms are all the same UUID. Passing them through
        unnormalised would set GUCs that compare unequal in RLS predicates while
        naming the same tenant.
        """
        ws = uuid.uuid4()
        canonical = str(ws)
        for variant in (
            canonical.upper(),
            f"{{{canonical}}}",
            f"urn:uuid:{canonical}",
            canonical.replace("-", ""),
        ):
            assert require_workspace(variant) == canonical

    def test_the_default_workspace_is_a_legitimate_value(self):
        # The defect is *arriving* there by accident, not the workspace itself.
        assert require_workspace(store.DEFAULT_WORKSPACE_ID) == store.DEFAULT_WORKSPACE_ID


class TestIsDefaultWorkspace:
    def test_identifies_the_default(self):
        assert is_default_workspace(store.DEFAULT_WORKSPACE_ID) is True
        assert is_default_workspace(store.DEFAULT_WORKSPACE_ID.upper()) is True

    def test_any_other_workspace_is_not_the_default(self):
        assert is_default_workspace(str(uuid.uuid4())) is False

    def test_invalid_input_is_not_the_default_rather_than_an_error(self):
        # This is a display helper, not a gate. It must not raise on junk, and it must
        # not answer True — "unparseable" is not "the default one".
        for bad in (None, "", "nonsense", 7):
            assert is_default_workspace(bad) is False


class TestScopedConnection:
    def test_a_bad_workspace_raises_before_any_connection_is_opened(self):
        """Validation must come first.

        If `scoped()` connected and then validated, a bad workspace would still have
        opened a session — and under an API that is a connection per bad request.
        Patching the connector to explode proves nothing reached it.
        """
        import meridian.tenancy as tenancy

        def explode(*args, **kwargs):  # pragma: no cover - must never run
            raise AssertionError("store.pg was called despite an invalid workspace")

        original = tenancy.store.pg
        tenancy.store.pg = explode
        try:
            for bad in (None, "", "not-a-uuid"):
                with pytest.raises(WorkspaceRequired):
                    with tenancy.scoped(bad):
                        pass
        finally:
            tenancy.store.pg = original


@pytest.mark.integration
def test_scoped_yields_a_working_connection_set_to_that_workspace():
    """The GUC actually lands, which is what every RLS policy reads."""
    import os

    if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
        pytest.skip("set CALLOSUM_RUN_INTEGRATION=1")

    from meridian.tenancy import scoped

    ws = store.DEFAULT_WORKSPACE_ID
    with scoped(ws) as conn:
        got = conn.execute("SELECT current_setting('app.workspace_id', true) AS ws").fetchone()
        assert got["ws"] == ws
