"""The eval resolves its principals the same way the product does (#187).

`evaluate._resolve_principal` used to build a `Principal` straight off
`principal.role` and `principal.clearance` — a second construction of the
authorization object, parallel to `callosum.identity`'s, which drifted from it once
#166 made `membership.role` authoritative. The consequence was a MEASUREMENT defect
rather than a leak: the eval's RBAC scoring graded `retrieve.py`'s frozen clearance
gate against an authorization model the product had stopped using.

These tests exist because the fix has to be provably measurement-neutral, and
because it can stop being neutral later without anyone touching `evaluate.py`.
"""

import os

import pytest

from callosum.cli import DEMO_PRINCIPALS
from callosum.identity import ROLE_TO_CLEARANCE


def test_every_demo_principal_agrees_with_the_role_mapping():
    """DB-free, and the one that actually guards the baseline.

    `eval-baseline-v3` was measured while `evaluate.py` read `principal.clearance`
    directly. It is unchanged by #187's fix only because, for every principal the
    eval resolves, the stored clearance and the mapped clearance are equal:

        Raj Malhotra   founder   4 == ROLE_TO_CLEARANCE["founder"]
        Priya Nair     exec      3 == ROLE_TO_CLEARANCE["exec"]
        Marcus Webb    investor  1 == ROLE_TO_CLEARANCE["investor"]

    That is a property of today's `DEMO_PRINCIPALS`, not a law. Seed a fourth demo
    principal as `('director', 2)` — the exact disagreement #182 documents in fifteen
    fixtures — and the eval's numbers would move for a reason that has nothing to do
    with retrieval. **This test fails first, naming the cause, instead of the shift
    being found later as an unexplained baseline change.**

    It also fails if someone changes `ROLE_TO_CLEARANCE` itself without re-measuring.
    """
    for name, _email, role, stored_clearance, _org in DEMO_PRINCIPALS:
        assert role in ROLE_TO_CLEARANCE, (
            f"{name} is seeded with role {role!r}, which is not one of the seven "
            f"approved on #166 — `callosum init` would fail 0027's CHECK"
        )
        assert ROLE_TO_CLEARANCE[role] == stored_clearance, (
            f"{name}: DEMO_PRINCIPALS seeds clearance {stored_clearance} beside role "
            f"{role!r}, which maps to {ROLE_TO_CLEARANCE[role]}. The eval resolves "
            f"through the mapping (#187), so this disagreement WOULD MOVE THE "
            f"EVAL BASELINE. Re-measure deliberately or fix the seed — do not "
            f"silence this test."
        )


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1",
    reason="set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests",
)
def test_the_eval_resolves_the_same_clearances_as_the_stored_column():
    """The same claim, end to end, against a seeded database.

    The unit test above compares two Python structures. This one runs the real
    resolution `evaluate()` performs and compares its result to the column the old
    implementation read — so the neutrality claim rests on the resolved object, not
    on the mapping alone.

    Depends on `callosum init` having been run, which the eval requires anyway and
    CI does before the suite.
    """
    import psycopg
    from psycopg.rows import dict_row

    from callosum import store
    from callosum.config import settings
    from callosum.evaluate import _resolve_principal

    with psycopg.connect(settings().postgres_dsn, row_factory=dict_row) as admin:
        seeded = admin.execute(
            "SELECT name, role, clearance FROM principal WHERE email = ANY(%s)",
            ([p[1] for p in DEMO_PRINCIPALS],),
        ).fetchall()

    assert seeded, "no demo principals in this database — run `callosum init`"

    with store.pg(store.DEFAULT_WORKSPACE_ID) as conn:
        for row in seeded:
            resolved = _resolve_principal(conn, row["name"])
            assert resolved is not None, (
                f"{row['name']} is in `principal` but did not resolve — they hold no "
                f"ACTIVE membership in the Default Workspace. That is the fail-closed "
                f"behaviour the old implementation did not have, and `callosum init` "
                f"is what grants the membership."
            )
            assert resolved.clearance == ROLE_TO_CLEARANCE[row["role"]]
            assert resolved.clearance == row["clearance"], (
                f"{row['name']}: the eval now resolves clearance "
                f"{resolved.clearance} where the old implementation read "
                f"{row['clearance']} from principal.clearance. The baseline is no "
                f"longer measuring the same thing."
            )
