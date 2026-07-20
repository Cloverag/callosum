"""Unit tests for the deterministic mechanism gate's aggregation + pass/fail logic.

These are DB-free: they exercise MechanismReport's counting and the `passed` invariant on
synthetic results. The live numbers (candidate 21/21, traversal 100%, RBAC) come from
scripts/eval_mechanism.sh against a seeded tenant DB — that's the integration gate, not this.

The `passed` contract (see docs/proposals/2026-07-20-eval-mechanism-split.md):
every applicable check must be perfect AND each tier must actually have run (a tier with
zero applicable items means a broken harness, not a pass).
"""

from callosum.evaluate import GoldItem, MechanismReport, MechanismResult


def _gold(id_: str, stratum: str = "multi_hop", as_user: str = "raj") -> GoldItem:
    return GoldItem(
        id=id_, stratum=stratum, question="q", as_user=as_user,
        expect_answer=[], forbid_answer=[], expect_facts=[{"a": 1}],
        expect_entities=["E"],
    )


def _perfect_result(id_: str) -> MechanismResult:
    """One item that passes all three tiers."""
    return MechanismResult(
        _gold(id_), candidate_applicable=True, candidate_hit=True,
        traversal_applicable=True, traversal_recall=1.0,
        rbac_applicable=True, rbac_pass=True,
    )


def _all_perfect(n: int = 3) -> MechanismReport:
    return MechanismReport([_perfect_result(f"Q{i}") for i in range(n)])


def test_all_perfect_passes():
    r = _all_perfect()
    assert r.candidate_hits == r.candidate_total == 3
    assert r.traversal_full == r.traversal_total == 3
    assert r.traversal_recall_mean == 1.0
    assert r.rbac_pass == r.rbac_total == 3
    assert r.passed


def test_one_candidate_miss_fails():
    results = [_perfect_result("Q0"), _perfect_result("Q1")]
    results[1].candidate_hit = False
    r = MechanismReport(results)
    assert r.candidate_hits == 1 and r.candidate_total == 2
    assert not r.passed


def test_partial_traversal_recall_fails():
    """Traversal is gated on FULL recall — 0.5 is not a pass even though it's non-zero."""
    results = [_perfect_result("Q0")]
    results[0].traversal_recall = 0.5
    r = MechanismReport(results)
    assert r.traversal_full == 0 and r.traversal_total == 1
    assert not r.passed


def test_rbac_leak_fails():
    results = [_perfect_result("Q0")]
    results[0].rbac_pass = False
    r = MechanismReport(results)
    assert r.rbac_pass == 0 and r.rbac_total == 1
    assert not r.passed


def test_empty_tier_is_not_a_pass():
    """A harness that never exercised RBAC (wrong gold / unseeded DB) must NOT report green."""
    res = _perfect_result("Q0")
    res.rbac_applicable = False  # no forbid_answer item ran
    res.rbac_pass = True
    r = MechanismReport([res])
    assert r.rbac_total == 0
    assert not r.passed  # perfect on the tiers that ran, but RBAC never ran → fail closed


def test_non_applicable_items_excluded_from_denominator():
    """A lookup with no gold entity/facts/forbid contributes to no denominator."""
    perfect = _perfect_result("Q0")
    lookup = MechanismResult(
        _gold("Q1", stratum="lookup"), candidate_applicable=False, candidate_hit=False,
        traversal_applicable=False, traversal_recall=0.0,
        rbac_applicable=False, rbac_pass=True,
    )
    r = MechanismReport([perfect, lookup])
    assert r.candidate_total == 1 and r.traversal_total == 1 and r.rbac_total == 1
    assert r.passed
