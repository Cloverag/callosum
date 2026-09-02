"""Enforces the `integration` marker, which was declared but never enforced.

`pyproject.toml:39` declares the marker. Nothing read it. Every one of the 37 gated
files hand-rolls the same check instead:

    if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
        pytest.skip(..., allow_module_level=True)

---------------------------------------------------------------------------
WHY A HOOK AND NOT MORE OF THE SAME
---------------------------------------------------------------------------
The module-level form gates a whole file, and four tests that need Postgres live in
files that are *mixed* — `test_backend_security_hardening.py` is six tests of which
five are genuinely static (env guards, error-envelope shape, router registration) and
one connects. Applying the module skip there would silently disable five good tests to
gate one, which is almost certainly why those four were left ungated in the first
place.

So the fix has to be per-test, and a per-test marker needs something that reads it.

---------------------------------------------------------------------------
WHAT THIS DOES NOT CHANGE
---------------------------------------------------------------------------
Nothing, for the 37 files that already gate themselves. Measured rather than assumed:
37 files use the marker, 37 carry the module-level env check, and the set difference is
**empty**. Their `pytest.skip(allow_module_level=True)` runs at import and never reaches
collection, so this hook is behaviourally redundant everywhere it already applies.

That redundancy is the reason the discrimination test in `test_conftest_gate.py`
matters: because the hook changes nothing for existing files, watching the four newly
marked tests skip proves nothing that a hook skipping *everything* would not also
produce. The property worth testing is that a DB-free test in the same file still runs.
"""

import os

import pytest

#: Set by the gated invocation: `CALLOSUM_RUN_INTEGRATION=1 pytest`.
_ENV = "CALLOSUM_RUN_INTEGRATION"


def pytest_collection_modifyitems(config, items):
    """Skip `integration`-marked tests unless the gate variable is set.

    Deliberately a collection hook rather than a fixture: it applies to any test
    carrying the marker however it was applied — decorator, class-level `pytestmark`, or
    module-level — without each test having to opt in to a fixture that gates it.
    """
    if os.environ.get(_ENV) == "1":
        return
    skip = pytest.mark.skip(reason=f"needs a live Postgres — set {_ENV}=1 to run")
    for item in items:
        # `get_closest_marker`, not `"integration" in item.keywords`: `keywords` is a
        # namespace of node *names* as well as markers, so a class or module literally
        # named `integration` would be gated by its name rather than by its marker. No
        # such name exists today — this is hardening, not a fix — but a gate that can be
        # satisfied by a coincidence of naming is discriminating on the wrong axis, which
        # is the defect this whole file is about.
        if item.get_closest_marker("integration") is not None:
            item.add_marker(skip)
