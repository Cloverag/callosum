"""The development auto-login affordance is off unless twice asked for (#187-adjacent).

`meridian/api/deps.py` carries a development convenience: a request with no session at
all can be auto-authenticated as the first seeded principal. That principal is
`ORDER BY p.created_at ASC LIMIT 1`, which under `cli.DEMO_PRINCIPALS` is the founder at
clearance 4 — so the affordance is not merely an authentication bypass, it is one that
lands on the highest privilege in the system.

It was guarded by `env != "production"` with the environment *defaulting to
"development"*. That is a denylist of one string, and it was fail-open three ways:

    ENVIRONMENT unset        -> "development" -> bypass eligible
    ENVIRONMENT=""           -> ""            -> bypass eligible
    ENVIRONMENT=prod         -> "prod"        -> bypass eligible

Only the first of those is dramatic, and only the first is what a fresh deployment
looks like. The pre-existing `test_dev_auto_auth_environment_guard` covered exactly one
case — `ENVIRONMENT` explicitly set to `production` — which is the case a careful
operator produces, not the case a hurried one does. The property it pinned was "the
guard works when you remember it", and the property that was missing is "the guard works
when you forget".

These tests pin the allowlist instead: anything not explicitly a development
environment is not one.
"""

import pytest
from fastapi import HTTPException

from meridian.api import deps

#: Every variable that can influence the decision. Cleared before each case so a test
#: can never pass because of something the *developer's* shell happened to export.
_ENV_VARS = ("ENVIRONMENT", "APP_ENV", "MERIDIAN_DEV_AUTO_AUTH")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# The unit the guard reduces to.
# ---------------------------------------------------------------------------

def test_unset_environment_does_not_enable_auto_auth(monkeypatch):
    """THE REGRESSION. A fresh deployment sets nothing; nothing must mean off.

    This is the case the old guard got wrong and the old test did not cover.
    """
    monkeypatch.setenv("MERIDIAN_DEV_AUTO_AUTH", "true")
    assert deps._dev_auto_auth_enabled() is False


def test_empty_environment_does_not_enable_auto_auth(monkeypatch):
    """`ENVIRONMENT=` in a .env file is unset-with-extra-steps, not a development box."""
    monkeypatch.setenv("ENVIRONMENT", "")
    monkeypatch.setenv("MERIDIAN_DEV_AUTO_AUTH", "true")
    assert deps._dev_auto_auth_enabled() is False


@pytest.mark.parametrize("value", ["production", "PRODUCTION", " production ", "Production"])
def test_production_spellings_do_not_enable_auto_auth(monkeypatch, value):
    monkeypatch.setenv("ENVIRONMENT", value)
    monkeypatch.setenv("MERIDIAN_DEV_AUTO_AUTH", "true")
    assert deps._dev_auto_auth_enabled() is False


@pytest.mark.parametrize("value", ["prod", "production-eu", "staging", "dev", "develop", "ci"])
def test_unrecognised_environments_do_not_enable_auto_auth(monkeypatch, value):
    """The denylist hole. `prod` is not `production`, and under the old guard that
    misspelling silently enabled founder auto-login on a production host."""
    monkeypatch.setenv("ENVIRONMENT", value)
    monkeypatch.setenv("MERIDIAN_DEV_AUTO_AUTH", "true")
    assert deps._dev_auto_auth_enabled() is False


def test_development_without_the_flag_does_not_enable_auto_auth(monkeypatch):
    """Both conditions are required. Being on a dev box is not a request."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    assert deps._dev_auto_auth_enabled() is False


@pytest.mark.parametrize("env_var", ["ENVIRONMENT", "APP_ENV"])
@pytest.mark.parametrize("env_value", ["development", "test", "local"])
@pytest.mark.parametrize("flag", ["true", "1", "yes", "TRUE", "Yes"])
def test_the_deliberate_case_still_works(monkeypatch, env_var, env_value, flag):
    """The affordance is hardened, not removed — it must still be reachable on purpose.

    A guard that also broke the legitimate path would be traded for a different defect,
    and the next person would loosen it back rather than debug it.
    """
    monkeypatch.setenv(env_var, env_value)
    monkeypatch.setenv("MERIDIAN_DEV_AUTO_AUTH", flag)
    assert deps._dev_auto_auth_enabled() is True


def test_empty_environment_falls_through_to_app_env(monkeypatch):
    """`os.environ.get("ENVIRONMENT", <fallback>)` returns "" for an empty variable and
    never consults the fallback. Both spellings must reach the same allowlist."""
    monkeypatch.setenv("ENVIRONMENT", "")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("MERIDIAN_DEV_AUTO_AUTH", "true")
    assert deps._dev_auto_auth_enabled() is True


# ---------------------------------------------------------------------------
# The property that actually matters, through the request path.
# ---------------------------------------------------------------------------

def test_sessionless_request_in_an_unset_environment_is_401_not_a_founder(monkeypatch):
    """End-to-end through `current_session`, and DB-free on purpose.

    `store.pg` is replaced with a sentinel that raises. Reaching it means the auto-auth
    branch was entered, so the mutation of this guard fails *deterministically* rather
    than as a Postgres connection error that could be mistaken for an environment
    problem.
    """
    monkeypatch.setenv("MERIDIAN_DEV_AUTO_AUTH", "true")

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError(
            "current_session entered the auto-auth branch with no ENVIRONMENT set — "
            "a sessionless request would have been authenticated as the founder"
        )

    monkeypatch.setattr(deps.store, "pg", _must_not_be_called)

    class FakeRequest:
        session = {}

    with pytest.raises(HTTPException) as exc:
        deps.current_session(FakeRequest())

    assert exc.value.status_code == 401
    assert exc.value.detail["code"] == deps.NOT_AUTHENTICATED
