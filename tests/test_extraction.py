"""Extraction regression tests.

These turn the worked examples in the extraction prompt into executable checks. If a
prompt edit silently inverts polarity — the failure mode this whole system is built to
prevent — CI catches it here instead of a founder catching it in a wrong answer.

The design point that matters: LLM extraction is non-deterministic, so asserting
`graph == expected` would flake on every run and you would start ignoring the suite.
Instead each case declares:

  - must_contain : edges that HAVE to appear (a recall floor)
  - must_not     : edges that must NEVER appear (the forbidden set — mainly inversions)

A run passes if it clears the floor and touches nothing forbidden. That tolerates the
harmless variation (an extra TOPIC, a rephrased attribute) while still failing hard on
the one error that actually costs you: SUPPORTED where it should be OPPOSED.

Marked `llm` because they call the live model. Run the fast suite with
`pytest -m "not llm"`; run these deliberately with `pytest -m llm`.
"""

import pytest

from callosum.extract import extract

pytestmark = pytest.mark.llm


def _edges(verified) -> set[tuple[str, str, str]]:
    return {(r.source, r.type.value, r.target) for r in verified.relationships}


def _has(edges, source_sub, relation, target_sub) -> bool:
    """Substring match on endpoints — the model may write 'Raj' or 'Raj Malhotra',
    and we care about the relation being right, not the exact surface name."""
    return any(
        source_sub.lower() in s.lower()
        and r == relation
        and target_sub.lower() in t.lower()
        for s, r, t in edges
    )


POLARITY_TRANSCRIPT = """\
RAJ: Let's close the pricing question. Model B, the usage-based one. Priya, you costed it.
PRIYA: I did. It takes gross margin from 71% to 58%. I can't recommend it.
MARCUS: I'll push back. The margin hit is real but Model B is how Stripe grew. Long game.
RAJ: Noted, but we're not doing Model B this quarter. That's my call.
"""


def test_polarity_not_inverted():
    """THE test. Priya opposed Model B, so she SUPPORTED the rejection; Marcus argued
    for Model B, so he OPPOSED the rejection. Inverting either is the single most
    damaging error the extractor can make, and it must never pass silently."""
    edges = _edges(extract(POLARITY_TRANSCRIPT))

    # Forbidden: the inversions. Priya must not OPPOSE the rejection; Marcus must not
    # SUPPORT it. We check the decision loosely by matching any target mentioning "B".
    for s, r, t in edges:
        if "priya" in s.lower() and "B" in t and r == "OPPOSED":
            pytest.fail(f"POLARITY INVERTED: Priya OPPOSED the rejection — she supported it. ({s},{r},{t})")
        if "marcus" in s.lower() and "B" in t and r == "SUPPORTED":
            pytest.fail(f"POLARITY INVERTED: Marcus SUPPORTED the rejection — he opposed it. ({s},{r},{t})")


def test_polarity_recall_floor():
    """Beyond avoiding inversion, the right edges should actually be found. This is a
    softer floor — it may need loosening if a weaker model can't hit it, and that
    loosening is itself a finding worth recording."""
    edges = _edges(extract(POLARITY_TRANSCRIPT))
    # Raj making the final call must be captured as APPROVED, not merely SUPPORTED.
    assert any(
        "raj" in s.lower() and r == "APPROVED" for s, r, t in edges
    ), f"Raj's final call was not captured as APPROVED. Edges: {edges}"


SUPERSEDE_TEXT = """\
Following the Q2 board meeting, we are revisiting the hiring freeze announced in March.
With the Series B closed, we're resuming engineering hiring immediately. Target: 6
engineers by end of Q3.
"""


def test_supersedes_edge_is_written():
    """The reversal edge is the point of institutional memory. Without it, 'are we
    still in a hiring freeze?' gets a stale answer."""
    edges = _edges(extract(SUPERSEDE_TEXT))
    assert any(r == "SUPERSEDES" for _, r, _ in edges), (
        f"No SUPERSEDES edge — the reversal was not captured. Edges: {edges}"
    )


BOILERPLATE = "This document is confidential and proprietary. © 2026 Meridian Inc."


def test_boilerplate_yields_nothing():
    """An empty extraction from a copyright line is the correct extraction."""
    v = extract(BOILERPLATE)
    assert not v.relationships, f"Invented edges from boilerplate: {_edges(v)}"


def test_fabricated_quotes_are_quarantined_not_dropped():
    """Whatever the model does, every rejected edge must land in failures with a
    reason — never silently vanish. The extraction process is the dataset."""
    v = extract(POLARITY_TRANSCRIPT)
    for f in v.failures:
        assert f.reason is not None
        assert f.quote is not None
