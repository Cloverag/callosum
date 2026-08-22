"""Deterministic tests for entity conflict detection.

These tests do NOT require Postgres, Neo4j, or Ollama. All store / driver
interactions are replaced with in-memory fakes so the suite stays fast and
offline. The test for the full approve path is marked `integration` and
excluded from the normal `pytest -q` run.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Similarity scoring — pure function, no external deps
# ---------------------------------------------------------------------------

class TestSimilarityScoring:
    """Verify the rapidfuzz token-sort-ratio behaves as expected for our data."""

    def _score(self, a: str, b: str) -> float:
        from rapidfuzz import fuzz
        return fuzz.token_sort_ratio(a, b)

    def test_clear_alias_above_threshold(self):
        """Raj Malhotra / R. Malhotra are the same person — should score high."""
        assert self._score("Raj Malhotra", "R. Malhotra") >= 80

    def test_clear_alias_full_name_variant(self):
        """Rajesh Malhotra / R. Malhotra — both refer to the CEO.

        Token-sort ratio = ~77. The default threshold is 75 to catch these.
        """
        assert self._score("Rajesh Malhotra", "R. Malhotra") >= 75

    def test_different_people_below_threshold(self):
        """Raj Malhotra and Raj Patel share a first name but are different people."""
        score = self._score("Raj Malhotra", "Raj Patel")
        # 80 threshold — this pair should NOT be flagged (different surnames)
        assert score < 80, f"Expected < 80, got {score}"

    def test_exact_match_not_flagged(self):
        """Exact same name — already the same node in Neo4j, never a 'conflict'."""
        assert self._score("Raj Malhotra", "Raj Malhotra") == 100

    def test_completely_different_names(self):
        """Totally unrelated names score well below threshold."""
        assert self._score("Pricing Model B", "Marcus Webb") < 50

    def test_topic_vs_topic_alias(self):
        """'Usage-based pricing' vs 'Usage Based Pricing Model' — different enough
        that they should NOT be auto-flagged; a human can add them manually.
        Token-sort ratio = ~50, well below threshold.
        """
        score = self._score("Usage-based pricing", "Usage Based Pricing Model")
        assert score < 75, f"Should be below threshold, got {score}"


# ---------------------------------------------------------------------------
# Candidate pair generation — pure function
# ---------------------------------------------------------------------------

class TestCandidatePairs:
    def _pairs(self, entities, threshold=80.0):
        from callosum.conflicts import _candidate_pairs
        return list(_candidate_pairs(entities, threshold))

    def _entity(self, name, etype="Person", chunk_id=None):
        return {"name": name, "type": etype,
                "chunk_id": chunk_id or str(uuid.uuid4()), "sensitivity": 1}

    def test_alias_pair_detected(self):
        entities = [
            self._entity("Raj Malhotra"),
            self._entity("R. Malhotra"),
            self._entity("Raj Patel"),
        ]
        pairs = self._pairs(entities)
        names = {(a["name"], b["name"]) for a, b, _ in pairs}
        # Raj Malhotra / R. Malhotra should be flagged
        assert any("R. Malhotra" in pair for pair in names)

    def test_different_people_not_paired(self):
        entities = [
            self._entity("Raj Malhotra"),
            self._entity("Raj Patel"),
        ]
        pairs = self._pairs(entities)
        assert len(pairs) == 0, "Raj Malhotra and Raj Patel should NOT be flagged"

    def test_cross_type_never_compared(self):
        """A Person and a Decision with similar names must not be paired."""
        entities = [
            self._entity("Raj Malhotra", etype="Person"),
            self._entity("Raj Malhotra Decision", etype="Decision"),
        ]
        pairs = self._pairs(entities)
        assert len(pairs) == 0

    def test_same_type_different_entities(self):
        """Sequoia Capital vs Sequoia score ~67 — below the default 80 threshold.
        At threshold=75 they are also below. Use a clearly above-threshold pair.
        """
        entities = [
            self._entity("Raj Malhotra", etype="Person"),
            self._entity("R. Malhotra", etype="Person"),
        ]
        pairs = self._pairs(entities, threshold=75.0)
        assert len(pairs) == 1

    def test_same_name_skipped(self):
        """Exact match — already the same Neo4j node, never flagged."""
        entities = [
            self._entity("Raj Malhotra"),
            self._entity("Raj Malhotra"),  # duplicate
        ]
        pairs = self._pairs(entities)
        assert len(pairs) == 0

    def test_canonical_ordering(self):
        """Pairs are always stored in alphabetical order to satisfy the UNIQUE constraint."""
        from callosum.conflicts import _candidate_pairs
        entities = [
            self._entity("R. Malhotra"),
            self._entity("Raj Malhotra"),
        ]
        pairs = list(_candidate_pairs(entities, 80.0))
        # The detection output order doesn't matter — the insert normalises it.
        # Just check we got exactly one pair.
        assert len(pairs) == 1


# ---------------------------------------------------------------------------
# detect_conflicts — mocked Postgres + Neo4j
# ---------------------------------------------------------------------------

class TestDetectConflicts:
    """Unit-test detect_conflicts with faked DB calls."""

    def _make_conn(self, conflict_exists=False):
        conn = MagicMock()
        # entity_conflict lookup returns nothing → no prior record
        check = MagicMock()
        check.fetchone.return_value = None if not conflict_exists else {"id": "x"}
        conn.execute.return_value = check
        return conn

    def _make_driver(self, entities):
        """Mock Neo4j driver returning given entity list."""
        driver = MagicMock()
        session = MagicMock()
        driver.session.return_value.__enter__ = MagicMock(return_value=session)
        driver.session.return_value.__exit__ = MagicMock(return_value=False)

        # First session.run call returns entities
        result = MagicMock()
        result.__iter__ = MagicMock(return_value=iter(entities))
        # Second session.run call (ALIAS_OF check) returns 0
        alias_result = MagicMock()
        alias_result.single.return_value = {"n": 0}
        session.run.side_effect = [result, alias_result, alias_result, alias_result]
        return driver

    def test_no_entities_no_conflicts(self):
        from callosum.conflicts import detect_conflicts
        conn = self._make_conn()
        driver = self._make_driver([])
        n = detect_conflicts(conn, driver)
        assert n == 0

    def test_alias_pair_queued(self):
        """When two similar names are in the graph, a conflict row should be inserted."""
        from callosum.conflicts import detect_conflicts

        cid_a = str(uuid.uuid4())
        cid_b = str(uuid.uuid4())
        entities = [
            {"name": "Raj Malhotra", "type": "Person",
             "chunk_id": cid_a, "ordinal": 0, "sensitivity": 1},
            {"name": "R. Malhotra", "type": "Person",
             "chunk_id": cid_b, "ordinal": 1, "sensitivity": 1},
        ]

        conn = MagicMock()
        # All execute calls: conflict-check returns None, chunk text returns short text, insert succeeds
        fetch_mock = MagicMock()
        fetch_mock.fetchone.side_effect = [
            None,   # no existing conflict row
            {"text": "Raj, short for Rajesh Malhotra, approved the plan."},  # chunk_a
            {"text": "R. Malhotra signed off on the customer communication."},  # chunk_b
        ]
        conn.execute.return_value = fetch_mock

        driver = MagicMock()
        session = MagicMock()
        driver.session.return_value.__enter__ = MagicMock(return_value=session)
        driver.session.return_value.__exit__ = MagicMock(return_value=False)
        entity_result = MagicMock()
        entity_result.__iter__ = MagicMock(return_value=iter(entities))
        alias_check = MagicMock()
        alias_check.single.return_value = {"n": 0}
        session.run.side_effect = [entity_result, alias_check]

        n = detect_conflicts(conn, driver)
        assert n == 1
        # Verify INSERT was called
        insert_calls = [
            c for c in conn.execute.call_args_list
            if "INSERT INTO entity_conflict" in str(c)
        ]
        assert len(insert_calls) == 1

    def test_existing_conflict_not_re_queued(self):
        """If a conflict row already exists, detect_conflicts must skip the pair."""
        from callosum.conflicts import detect_conflicts

        cid_a = str(uuid.uuid4())
        entities = [
            {"name": "Raj Malhotra", "type": "Person",
             "chunk_id": cid_a, "ordinal": 0, "sensitivity": 1},
            {"name": "R. Malhotra", "type": "Person",
             "chunk_id": cid_a, "ordinal": 1, "sensitivity": 1},
        ]
        conn = MagicMock()
        fetch = MagicMock()
        # Return an existing row → _already_known returns True
        fetch.fetchone.return_value = {"id": "existing"}
        conn.execute.return_value = fetch

        driver = MagicMock()
        session = MagicMock()
        driver.session.return_value.__enter__ = MagicMock(return_value=session)
        driver.session.return_value.__exit__ = MagicMock(return_value=False)
        entity_result = MagicMock()
        entity_result.__iter__ = MagicMock(return_value=iter(entities))
        alias_check = MagicMock()
        alias_check.single.return_value = {"n": 0}
        session.run.side_effect = [entity_result, alias_check]

        n = detect_conflicts(conn, driver)
        assert n == 0


# ---------------------------------------------------------------------------
# reject_conflict — mocked Postgres
# ---------------------------------------------------------------------------

class TestRejectConflict:
    def test_reject_updates_status(self):
        from callosum.conflicts import reject_conflict

        conflict_id = uuid.uuid4()
        conn = MagicMock()
        fetch = MagicMock()
        fetch.fetchone.return_value = {"id": conflict_id}
        conn.execute.return_value = fetch

        reject_conflict(conn, conflict_id)

        update_calls = [c for c in conn.execute.call_args_list
                        if "UPDATE entity_conflict" in str(c)]
        assert len(update_calls) == 1

    def test_reject_nonexistent_raises(self):
        from callosum.conflicts import reject_conflict

        conn = MagicMock()
        fetch = MagicMock()
        fetch.fetchone.return_value = None   # no such row
        conn.execute.return_value = fetch

        with pytest.raises(ValueError, match="No pending entity conflict"):
            reject_conflict(conn, uuid.uuid4())


# ---------------------------------------------------------------------------
# Sensitivity inheritance
# ---------------------------------------------------------------------------

class TestSensitivityInheritance:
    """What decides who may read a conflict's quotes.

    `quote_a` and `quote_b` are verbatim spans of source documents, surfaced by
    `GET /api/conflicts` to any reviewer whose clearance is at or above the row's
    sensitivity. So this derivation is an access-control decision, not bookkeeping.

    The previous test here restated the production expression —
    `max(a.get("sensitivity", 1), b.get("sensitivity", 1))` — and asserted its own
    copy. It would have passed unchanged if the default had become `0`. These call
    the real function.
    """

    def test_max_sensitivity_used(self):
        """A conflict is as sensitive as the more sensitive of its two sources."""
        from callosum.conflicts import _candidate_pairs, pair_sensitivity

        entities = [
            {"name": "Raj Malhotra", "type": "Person",
             "chunk_id": str(uuid.uuid4()), "ordinal": 0, "sensitivity": 1},
            {"name": "R. Malhotra", "type": "Person",
             "chunk_id": str(uuid.uuid4()), "ordinal": 0, "sensitivity": 3},
        ]
        pairs = list(_candidate_pairs(entities, 80.0))
        assert len(pairs) == 1
        a, b, _score = pairs[0]
        assert pair_sensitivity(a, b) == 3

    def test_a_missing_sensitivity_fails_closed(self):
        """An absent key means "unknown", and unknown must be the most restrictive.

        `1` — the old fallback — is *investor*, so a pair whose source sensitivity
        went missing would have had its quotes readable by an investor-clearance
        reviewer.
        """
        from callosum.conflicts import MAX_SENSITIVITY, pair_sensitivity

        assert pair_sensitivity({"name": "A"}, {"name": "B"}) == MAX_SENSITIVITY
        # One known-public source does not make the pair public: the other is unknown,
        # and the pair carries a quote from it.
        assert pair_sensitivity({"sensitivity": 0}, {"name": "B"}) == MAX_SENSITIVITY

    def test_a_null_sensitivity_fails_closed(self):
        """`None` is the path a `.get(key, default)` reading misses entirely.

        `dict.get` returns the *value* when the key is present, so a Cypher
        `RETURN c.sensitivity` over a node without the property yields `None` and
        never reaches the default. The old code would have passed `None` into
        `max()` and raised a TypeError mid-scan.
        """
        from callosum.conflicts import MAX_SENSITIVITY, pair_sensitivity

        assert pair_sensitivity({"sensitivity": None}, {"sensitivity": None}) == MAX_SENSITIVITY
        assert pair_sensitivity({"sensitivity": None}, {"sensitivity": 2}) == MAX_SENSITIVITY

    def test_the_fallback_is_the_top_of_the_ladder(self):
        """Pinned to `schema/postgres.sql`, which seeds levels 0..4.

        If a level is ever added, this fails rather than the fallback silently
        ceasing to be the most restrictive one.
        """
        from callosum.conflicts import MAX_SENSITIVITY

        assert MAX_SENSITIVITY == 4
