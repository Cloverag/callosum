"""Live-store integration coverage for R12 candidate RBAC.

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``. The test creates
unique Postgres documents/chunks and matching Neo4j nodes, then deletes only those records.
It does not reset shared local volumes.
"""

import os
import uuid

import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip("set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests", allow_module_level=True)

from callosum import store
from callosum.ontology import EntityType
from callosum.retrieve import Principal, candidate_entities

pytestmark = pytest.mark.integration


def test_candidate_entities_enforce_postgres_and_neo4j_clearance(monkeypatch):
    """A private name stays hidden even if its chunk UUID is supplied directly.

    This covers the complete R12 candidate route: pgvector ranking filters chunks by
    clearance, and the Neo4j ``MENTIONS`` lookup repeats the same clearance predicate.
    """
    import callosum.retrieve as retrieve

    token = uuid.uuid4().hex
    public_name = f"Public candidate {token}"
    restricted_name = f"Restricted candidate {token}"
    public_doc = restricted_doc = public_chunk = restricted_chunk = None
    driver = store.neo(wait=5)

    vector = [1.0] + [0.0] * 1023  # cosine indexes exclude zero vectors
    monkeypatch.setattr(retrieve, "embed", lambda _texts, input_type: [vector])
    low = Principal(id=None, name="integration-low", role="investor", clearance=1)
    high = Principal(id=None, name="integration-high", role="founder", clearance=3)

    try:
        with store.pg() as conn:
            def add_document(title, sensitivity):
                row = conn.execute(
                    """
                    INSERT INTO document (title, doc_type, raw_text, content_hash, sensitivity)
                    VALUES (%s, 'memo', %s, %s, %s)
                    RETURNING id
                    """,
                    (title, title, f"candidate-rbac-{token}-{sensitivity}", sensitivity),
                ).fetchone()
                return row["id"]

            def add_chunk(document_id, sensitivity):
                row = conn.execute(
                    """
                    INSERT INTO chunk (document_id, ordinal, text, start_char, end_char,
                                       sensitivity, embedding)
                    VALUES (%s, 0, %s, 0, %s, %s, %s)
                    RETURNING id
                    """,
                    (document_id, f"candidate boundary {token}",
                     len(f"candidate boundary {token}"), sensitivity, vector),
                ).fetchone()
                return row["id"]

            public_doc = add_document(f"public-candidate-{token}", 1)
            restricted_doc = add_document(f"restricted-candidate-{token}", 3)
            public_chunk = add_chunk(public_doc, 1)
            restricted_chunk = add_chunk(restricted_doc, 3)

            store.upsert_chunk_node(
                driver, chunk_id=public_chunk, document_id=public_doc, ordinal=0, sensitivity=1
            )
            store.upsert_chunk_node(
                driver, chunk_id=restricted_chunk, document_id=restricted_doc, ordinal=0,
                sensitivity=3,
            )
            store.apply_entity(driver, {
                "name": public_name, "type": EntityType.TOPIC.value,
                "attributes": {}, "chunk_id": str(public_chunk),
            })
            store.apply_entity(driver, {
                "name": restricted_name, "type": EntityType.TOPIC.value,
                "attributes": {}, "chunk_id": str(restricted_chunk),
            })
            # Neo4j must see this committed bridge before a separate candidate query reads it.
            conn.commit()

            assert store.entity_names_for_chunks(
                driver, [public_chunk, restricted_chunk], clearance=3
            ) == [public_name, restricted_name]

            # Full candidate route: pgvector must withhold the sensitivity-3 chunk for low.
            # candidate_entities returns (names, chunk_texts); the RBAC assertion is on names.
            # Assert inclusion and exclusion rather than exact list equality, so pre-existing
            # corpus data in shared development databases does not fail the RBAC test (#55).
            low_candidates = candidate_entities(conn, driver, f"candidate boundary {token}", low)[0]
            assert public_name in low_candidates
            assert restricted_name not in low_candidates

            high_candidates = candidate_entities(conn, driver, f"candidate boundary {token}", high)[0]
            assert public_name in high_candidates
            assert restricted_name in high_candidates

            # Defense in depth: the Neo4j helper must also reject a caller-supplied private ID.
            assert store.entity_names_for_chunks(
                driver, [public_chunk, restricted_chunk], clearance=1
            ) == [public_name]
    finally:
        with driver.session() as session:
            session.run(
                "MATCH (c:Chunk) WHERE c.id IN $ids DETACH DELETE c",
                ids=[str(chunk_id) for chunk_id in (public_chunk, restricted_chunk) if chunk_id],
            )
            session.run(
                "MATCH (e:Entity) WHERE e.name IN $names DETACH DELETE e",
                names=[name for name in (public_name, restricted_name)],
            )
        if public_doc or restricted_doc:
            with store.pg() as conn:
                conn.execute(
                    "DELETE FROM document WHERE id = ANY(%s)",
                    ([doc_id for doc_id in (public_doc, restricted_doc) if doc_id],),
                )
        driver.close()
