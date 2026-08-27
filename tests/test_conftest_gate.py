"""The `integration` gate must discriminate, not just skip.

`conftest.py`'s hook is behaviourally redundant across all 37 files that already gate
themselves at module level, so the obvious check — "the four newly marked tests skip" —
proves almost nothing. **A hook that skipped every test in the suite would produce that
same observation.**

The property worth asserting is the one that separates those two hooks: in a file holding
both kinds of test, the DB-requiring one skips *and the DB-free ones still run*.

`test_backend_security_hardening.py` is exactly that file — six tests, of which five are
static (env guard, error-envelope shape, router registration) and one connects to
Postgres. It is also the reason #171 could not be fixed with the module-level
`pytest.skip(allow_module_level=True)` pattern the other 37 files use: doing so would
have disabled five good tests to gate one.

Ungated, so it runs in the fast tier — which is the tier whose honesty it defends.
"""

import subprocess
import sys

#: The mixed file: 5 DB-free tests + 1 that needs Postgres.
_MIXED = "tests/test_backend_security_hardening.py"


def _run_ungated(*args: str) -> str:
    """Collect `_MIXED` with the gate variable explicitly absent."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", _MIXED, "-q", "--no-header", *args],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": "/tmp"},
    ).stdout


def test_the_gate_skips_the_db_test_and_runs_the_rest():
    """5 passed, 1 skipped — not 6 skipped, and not 6 run."""
    out = _run_ungated()
    assert "5 passed" in out, f"the DB-free tests stopped running:\n{out}"
    assert "1 skipped" in out, f"the DB test was not gated:\n{out}"


def test_the_skipped_one_is_the_database_test_by_name():
    """Naming it, so a future reshuffle cannot satisfy the counts with the wrong test."""
    out = _run_ungated("-rs")
    assert "test_composite_tenant_foreign_key_constraint" in out, out
