"""`callosum init` must not grant Default Workspace membership to every principal (#201)."""

from pathlib import Path

from callosum.cli import DEMO_PRINCIPALS

_CLI = Path("src/callosum/cli.py").read_text(encoding="utf-8")


def test_init_membership_sql_is_scoped_to_demo_emails():
    assert "WHERE p.email = ANY(%s)" in _CLI
    assert "Sourced by SELECT rather than from DEMO_PRINCIPALS" not in _CLI


def test_demo_principal_emails_are_exactly_the_three_seeds():
    emails = {email for _name, email, _role, _clr, _org in DEMO_PRINCIPALS}
    assert emails == {
        "raj@callosum.inc",
        "priya@callosum.inc",
        "marcus@sequoia.com",
    }
