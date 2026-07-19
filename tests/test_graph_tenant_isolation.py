"""Live-store break-in tests for P1 Neo4j multi-tenant isolation (Meridian, Brick 3.3).

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``. These are the
adversarial proofs that the graph is partitioned by workspace: two tenants are given
DELIBERATELY COLLIDING entity names, and we assert that neither can reach the other's
nodes or edges — through the seed match, the traversal path gate, or the direct
chunk→entity lookup. Each test seeds uniquely-tokened data and deletes only its own.

Neo4j has no Row-Level Security, so isolation is structural (workspace_id in entity
identity) plus query-level predicates. These tests defend both.
"""

import os
import uuid

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

from callosum import store
from callosum.ontology import EntityType, RelationType
from callosum.retrieve import Principal, graph_search

pytestmark = pytest.mark.integration

WA = "000000aa-0000-0000-0000-0000000000aa"
WB = "000000bb-0000-0000-0000-0000000000bb"


def _seed_pair(driver, tok):
    """Same 'Shared' entity name in two workspaces, each linked to a workspace-local peer."""
    shared, aonly, bonly = f"Shared-{tok}", f"AOnly-{tok}", f"BOnly-{tok}"
    rel = next(iter(RelationType)).value
    ids = {}
    for ws, peer, key in ((WA, aonly, "a"), (WB, bonly, "b")):
        chunk, doc = uuid.uuid4(), uuid.uuid4()
        ids[key] = chunk
        store.upsert_chunk_node(driver, chunk_id=chunk, document_id=doc, ordinal=0,
                                sensitivity=1, workspace_id=ws)
        for name in (shared, peer):
            store.apply_entity(driver, {"name": name, "type": EntityType.TOPIC.value,
                                        "attributes": {}, "chunk_id": str(chunk), "workspace_id": ws})
        store.apply_relationship(driver, {"source": shared, "target": peer, "type": rel,
                                          "quote": "q", "chunk_id": str(chunk), "workspace_id": ws})
    return shared, aonly, bonly, ids


def _cleanup(driver, names, chunk_ids):
    with driver.session() as s:
        s.run("MATCH (e:Entity) WHERE e.name IN $n DETACH DELETE e", n=names)
        s.run("MATCH (c:Chunk) WHERE c.id IN $ids DETACH DELETE c",
              ids=[str(c) for c in chunk_ids])


def test_entity_identity_is_partitioned_by_workspace():
    """A colliding entity name is two separate nodes, one per workspace — never shared."""
    driver = store.neo(wait=5)
    store.ensure_constraints(driver)
    tok = uuid.uuid4().hex[:8]
    shared, aonly, bonly, ids = _seed_pair(driver, tok)
    try:
        with driver.session() as s:
            ws = sorted(r["w"] for r in s.run(
                "MATCH (e:Entity {name:$n}) RETURN e.workspace_id AS w", n=shared).data())
        assert ws == [WA, WB], ws
    finally:
        _cleanup(driver, [shared, aonly, bonly], ids.values())
        driver.close()


def test_graph_search_cannot_cross_workspace():
    """Traversal from a shared name returns only the caller's workspace edges."""
    driver = store.neo(wait=5)
    store.ensure_constraints(driver)
    tok = uuid.uuid4().hex[:8]
    shared, aonly, bonly, ids = _seed_pair(driver, tok)
    try:
        pa = Principal(id=None, name="a", role="founder", clearance=4, workspace_id=WA)
        pb = Principal(id=None, name="b", role="founder", clearance=4, workspace_id=WB)
        facts_a, _ = graph_search(driver, [shared], pa)
        facts_b, _ = graph_search(driver, [shared], pb)
        assert any(aonly in f for f in facts_a) and not any(bonly in f for f in facts_a)
        assert any(bonly in f for f in facts_b) and not any(aonly in f for f in facts_b)
    finally:
        _cleanup(driver, [shared, aonly, bonly], ids.values())
        driver.close()


def test_entity_names_for_chunks_is_workspace_scoped():
    """Supplying another workspace's chunk id yields none of its entities."""
    driver = store.neo(wait=5)
    store.ensure_constraints(driver)
    tok = uuid.uuid4().hex[:8]
    shared, aonly, bonly, ids = _seed_pair(driver, tok)
    try:
        # Ask as workspace A, but hand it BOTH chunks (A's and B's).
        names = store.entity_names_for_chunks(driver, [ids["a"], ids["b"]], 4, workspace_id=WA)
        assert aonly in names and shared in names
        assert bonly not in names
    finally:
        _cleanup(driver, [shared, aonly, bonly], ids.values())
        driver.close()


def test_conflict_scan_cannot_cross_workspace():
    """F2 regression: the entity-conflict scan is workspace-scoped.

    Two tenants hold the same 'Shared' name plus a workspace-local peer. A scan run for
    workspace A must see only A's entities, so a colliding name can never be paired with
    another tenant's entity into a conflict proposal.
    """
    from callosum.graph import GraphContext, GraphGateway
    driver = store.neo(wait=5)
    store.ensure_constraints(driver)
    tok = uuid.uuid4().hex[:8]
    shared, aonly, bonly, ids = _seed_pair(driver, tok)
    try:
        gw = GraphGateway(driver)
        names_a = {m["name"] for m in gw.entity_mentions(GraphContext(workspace_id=WA))}
        assert shared in names_a and aonly in names_a   # sees its own workspace
        assert bonly not in names_a                      # never the other tenant's entities
    finally:
        _cleanup(driver, [shared, aonly, bonly], ids.values())
        driver.close()


def test_wrong_workspace_principal_sees_nothing():
    """A principal in a third workspace sees neither tenant's graph."""
    driver = store.neo(wait=5)
    store.ensure_constraints(driver)
    tok = uuid.uuid4().hex[:8]
    shared, aonly, bonly, ids = _seed_pair(driver, tok)
    try:
        stranger = Principal(id=None, name="c", role="founder", clearance=4,
                             workspace_id="000000cc-0000-0000-0000-0000000000cc")
        facts, chunk_ids = graph_search(driver, [shared], stranger)
        assert facts == [] and chunk_ids == []
    finally:
        _cleanup(driver, [shared, aonly, bonly], ids.values())
        driver.close()
