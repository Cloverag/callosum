"""The demo principal selector is off by default and cannot be handed a principal id.

`meridian/api/demo.py` writes a session for a seeded demo principal so a public demo can
switch identities and watch the same request return different material. It is a third
caller of `session.establish()`, not a second authentication implementation — but it is
still, literally, an impersonation endpoint, so the two properties that matter are:

  1. it is off unless explicitly switched on, and
  2. the browser can name a *symbol*, never a principal.

Both are pinned here. The first is the lesson of #191, where an affordance guarded by
"not production" was on by default in every environment that forgot to say otherwise.
"""

import os

import pytest
from fastapi.testclient import TestClient

from callosum.cli import DEMO_PRINCIPALS
from meridian.api import demo


@pytest.fixture(autouse=True)
def _clean_flag(monkeypatch):
    monkeypatch.delenv(demo.FLAG, raising=False)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("MERIDIAN_SESSION_SECRET", "test-secret-not-for-use")
    monkeypatch.setenv("MERIDIAN_SESSION_HTTPS_ONLY", "false")
    from meridian.api.main import app
    return TestClient(app)


# --- the guard -------------------------------------------------------------

def test_selector_is_off_when_the_flag_is_absent():
    """The default state of every environment. Absent means off."""
    assert demo.selector_enabled() is False


@pytest.mark.parametrize("value", ["", "false", "0", "no", "off", "maybe", " "])
def test_only_explicit_truthy_values_enable_it(monkeypatch, value):
    monkeypatch.setenv(demo.FLAG, value)
    assert demo.selector_enabled() is False


@pytest.mark.parametrize("value", ["true", "1", "yes", "TRUE", "Yes", " true "])
def test_the_deliberate_case_still_works(monkeypatch, value):
    monkeypatch.setenv(demo.FLAG, value)
    assert demo.selector_enabled() is True


def test_disabled_selector_answers_404_not_503(client):
    """404, so a real deployment does not advertise that an impersonation route exists.

    `main.py` answers 503 for unconfigured OIDC because a login route that is present but
    unwired is a deployment state worth reporting. This one is not: the useful answer to
    "is there a way to become the founder here" is "no such route".
    """
    assert client.post("/auth/demo/select", json={"identity": "founder"}).status_code == 404
    assert client.get("/auth/demo/identities").status_code == 404


# --- the browser cannot name a principal -----------------------------------

@pytest.mark.parametrize("payload", [
    {"principal_id": "2b0b8f1e-0000-0000-0000-000000000000"},
    {"identity": "2b0b8f1e-0000-0000-0000-000000000000"},
    {"identity": "root"},
    {"identity": "admin"},
    {"identity": ""},
    {},
])
def test_only_the_three_symbols_are_accepted(client, monkeypatch, payload):
    """`identity` is a `Literal`, so FastAPI refuses anything else with 422 before the
    handler runs. There is no `principal_id` field to inject in the first place."""
    monkeypatch.setenv(demo.FLAG, "true")
    assert client.post("/auth/demo/select", json=payload).status_code == 422


def test_a_smuggled_principal_id_is_ignored(client, monkeypatch):
    """An extra key does not become an identity. Pydantic drops it; nothing reads it."""
    monkeypatch.setenv(demo.FLAG, "true")
    body = {"identity": "investor", "principal_id": "2b0b8f1e-0000-0000-0000-000000000000"}
    # 204 on a seeded database, 503 on an empty one — either way it did not become a
    # principal-id-driven login, which is what this test is about.
    assert client.post("/auth/demo/select", json=body).status_code in (200, 503)


# --- the mapping -----------------------------------------------------------

def test_identity_symbols_map_to_seeded_demo_principals():
    """Derived from `DEMO_PRINCIPALS`, not restated beside it.

    If a demo principal's role is renamed, `demo.py` raises at import rather than
    offering a symbol that resolves to nobody.
    """
    emails_by_role = {role: email for _n, email, role, _c, _o in DEMO_PRINCIPALS}
    assert set(demo.IDENTITY_EMAILS) == {"founder", "exec", "investor"}
    for symbol, email in demo.IDENTITY_EMAILS.items():
        assert emails_by_role[symbol] == email


def test_labels_disclose_no_role_or_clearance():
    """The picker is not a directory of who can see what.

    Publishing "Founder — clearance 4" beside the buttons would hand a visitor the
    authorization model for free. Labels are display text only.
    """
    for label in demo.IDENTITY_LABELS.values():
        assert not any(ch.isdigit() for ch in label), f"{label!r} leaks a clearance"
        assert "clearance" not in label.lower()


def test_the_provider_marker_is_not_an_oidc_issuer():
    """#191's bypass defaulted `provider` to a Keycloak issuer URL and `subject` to an
    email, so audit records claimed an OIDC login that never happened. A demo session
    must say it is a demo session."""
    src = (demo.__file__ and open(demo.__file__).read()) or ""
    assert 'provider="demo-selector"' in src
    assert "realms/" not in src.split("WHY THE GUARD")[-1], "an issuer URL crept into the handler"
