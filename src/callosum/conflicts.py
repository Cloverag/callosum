"""Entity conflict detection — finds candidate alias pairs by name similarity.

This module is deliberately separate from the frozen pipeline core (ingest, extract,
retrieve, store). It is a post-ingest advisory scan, not a write path. Nothing it
produces reaches Neo4j without a human approval via store.approve().

Design contract:
  - Detection is deterministic and side-effect-free on the graph.
  - A detected conflict is queued in Postgres entity_conflict as 'pending'.
  - Approval routes through the normal proposed_change → store.approve() path:
    it queues an add_relationship(ALIAS_OF) proposal, then calls approve() on it.
  - Rejection writes status='rejected' and the pair is never re-queued.
  - Pairs are only compared within the same EntityType.
  - Similarity is token-sort ratio (rapidfuzz), threshold 0.0–1.0.

Security invariants preserved:
  - The conflict row stores max(sensitivity of the two source chunks).
  - review-conflicts only shows rows where the principal's clearance >= sensitivity.
  - Approval produces a normal proposed_change which goes through apply_relationship(),
    which validates the rel type against RelationType — ALIAS_OF is valid in v3.
"""

import json
import uuid
from typing import Iterator

import psycopg
from neo4j import Driver
from rapidfuzz import fuzz

from callosum import store
from callosum.graph import GraphContext, GraphGateway
from callosum.ontology import ONTOLOGY_VERSION, RelationType

# ---------------------------------------------------------------------------
# Similarity configuration
# ---------------------------------------------------------------------------

# Minimum token-sort ratio (0–100 int, rapidfuzz scale) to flag a pair.
# 75 catches abbreviated names like "R. Malhotra" / "Rajesh Malhotra" (~77)
# while keeping "Raj Malhotra" / "Raj Patel" (~57) safely below the line.
DEFAULT_THRESHOLD = 75.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _chunk_quote(conn: psycopg.Connection, chunk_id: str) -> str | None:
    """Return the first sentence of a chunk as the introductory quote."""
    row = conn.execute(
        "SELECT text FROM chunk WHERE id = %s", (uuid.UUID(chunk_id),)
    ).fetchone()
    if not row:
        return None
    text = row["text"].strip()
    # Return up to the first sentence break or 200 chars — whichever is shorter.
    for sep in (".", "!", "?", "\n"):
        idx = text.find(sep)
        if 0 < idx < 200:
            return text[: idx + 1].strip()
    return text[:200].strip()


def _already_known(
    conn: psycopg.Connection, gw: GraphGateway, ctx: GraphContext,
    name_a: str, type_a: str, name_b: str, type_b: str,
) -> bool:
    """Return True if this pair should be skipped.

    Skips if:
    - An entity_conflict row already exists in either direction (pending/approved/rejected)
    - An ALIAS_OF edge already exists in Neo4j (workspace-scoped via the gateway)
    """
    # Check Postgres conflict table (both directions). RLS on entity_conflict scopes this to the
    # caller's workspace already.
    existing = conn.execute(
        """
        SELECT 1 FROM entity_conflict
        WHERE (name_a = %s AND type_a = %s AND name_b = %s AND type_b = %s)
           OR (name_a = %s AND type_a = %s AND name_b = %s AND type_b = %s)
        """,
        (name_a, type_a, name_b, type_b, name_b, type_b, name_a, type_a),
    ).fetchone()
    if existing:
        return True

    # Check Neo4j for an existing ALIAS_OF edge — through the gateway, so it is workspace-scoped
    # by construction (no raw session here; D-001).
    return gw.alias_edge_exists(ctx, name_a, type_a, name_b, type_b)


def _candidate_pairs(
    entities: list[dict], threshold: float
) -> Iterator[tuple[dict, dict, float]]:
    """Yield (entity_a, entity_b, score) for all same-type pairs above threshold.

    Only compares entities of the same EntityType. Never compares a name to itself.
    O(n²) — acceptable for the small entity graphs this prototype targets.
    """
    typed: dict[str, list[dict]] = {}
    for e in entities:
        typed.setdefault(e["type"], []).append(e)

    for etype, group in typed.items():
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                if a["name"] == b["name"]:
                    continue  # Exact match — already the same node in Neo4j
                score = fuzz.token_sort_ratio(a["name"], b["name"])
                if score >= threshold:
                    yield a, b, score / 100.0  # normalise to 0.0–1.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_conflicts(
    conn: psycopg.Connection,
    driver: Driver,
    *,
    workspace_id: str = store.DEFAULT_WORKSPACE_ID,
    threshold: float = DEFAULT_THRESHOLD,
) -> int:
    """Scan entities for similar name pairs and queue new conflict proposals.

    Scoped to a single workspace: the scan, the already-known check, and the queued row
    all carry `workspace_id`, so tenants are never cross-paired and the row lands in the
    caller's tenant (must match the RLS session on `conn`).

    For each candidate pair above `threshold` (token-sort ratio, 0–100):
    - Skip if a conflict row or ALIAS_OF edge already exists.
    - Find the introductory source quote for each entity.
    - Insert a 'pending' entity_conflict row.

    Returns the count of newly queued conflicts.
    """
    ctx = GraphContext(workspace_id=workspace_id)
    gw = GraphGateway(driver)
    entities = gw.entity_mentions(ctx)
    queued = 0

    for entity_a, entity_b, score in _candidate_pairs(entities, threshold):
        name_a, type_a = entity_a["name"], entity_a["type"]
        name_b, type_b = entity_b["name"], entity_b["type"]

        # Always store the pair in a canonical order (alphabetical) so the
        # UNIQUE constraint catches both (A,B) and (B,A) as the same pair.
        if (name_a, type_a) > (name_b, type_b):
            name_a, type_a, name_b, type_b = name_b, type_b, name_a, type_a
            entity_a, entity_b = entity_b, entity_a

        if _already_known(conn, gw, ctx, name_a, type_a, name_b, type_b):
            continue

        chunk_id_a = entity_a.get("chunk_id")
        chunk_id_b = entity_b.get("chunk_id")
        quote_a = _chunk_quote(conn, chunk_id_a) if chunk_id_a else None
        quote_b = _chunk_quote(conn, chunk_id_b) if chunk_id_b else None

        # Sensitivity of the conflict = max of the two source chunks.
        # A reviewer needs clearance >= this to see the pair.
        sensitivity = max(
            entity_a.get("sensitivity", 1), entity_b.get("sensitivity", 1)
        )

        try:
            conn.execute(
                """
                INSERT INTO entity_conflict
                    (name_a, type_a, name_b, type_b, similarity,
                     chunk_id_a, chunk_id_b, quote_a, quote_b, sensitivity, workspace_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (name_a, type_a, name_b, type_b) DO NOTHING
                """,
                (
                    name_a, type_a, name_b, type_b, score,
                    uuid.UUID(chunk_id_a) if chunk_id_a else None,
                    uuid.UUID(chunk_id_b) if chunk_id_b else None,
                    quote_a, quote_b,
                    sensitivity,
                    uuid.UUID(workspace_id),
                ),
            )
            queued += 1
        except psycopg.errors.UndefinedTable as exc:
            # A fresh database has no entity_conflict table (migration 0005). Name the
            # cause instead of surfacing a bare "relation does not exist" from the
            # middle of a scan.
            #
            # This deliberately still RAISES. The rejected alternative was to log and
            # return the count queued so far, which reports a missing migration as
            # "no conflicts found" — a scan that silently examines nothing is worse
            # than one that stops.
            raise RuntimeError(
                "entity_conflict table is missing — apply migration 0005 before scanning "
                "for conflicts."
            ) from exc

    return queued


def approve_conflict(
    conn: psycopg.Connection,
    driver: Driver,
    conflict_id: uuid.UUID,
    reviewer_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Approve a conflict: queue an ALIAS_OF proposal and immediately approve it.

    The ALIAS_OF edge goes through the normal proposed_change → store.approve() path
    so all provenance invariants are preserved (graph written first, then Postgres marked
    approved). Returns the change_id of the approved proposal.
    """
    row = conn.execute(
        "SELECT name_a, type_a, name_b, type_b, chunk_id_a, workspace_id FROM entity_conflict "
        "WHERE id = %s AND status = 'pending'",
        (conflict_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"No pending entity conflict: {conflict_id}")

    # Use chunk_id_a as the provenance anchor for the ALIAS_OF edge.
    chunk_id = str(row["chunk_id_a"]) if row["chunk_id_a"] else str(uuid.uuid4())

    payload = {
        "source": row["name_a"],
        "type": RelationType.ALIAS_OF.value,
        "target": row["name_b"],
        "quote": f"{row['name_a']} is an alias of {row['name_b']}",
        "chunk_id": chunk_id,
        # Stamp the conflict's workspace so apply_relationship matches the right tenant's
        # entities, not the default workspace.
        "workspace_id": str(row["workspace_id"]),
    }

    # Queue the proposed_change (entities must already be in the graph — they are, since
    # they were detected from existing MENTIONS edges).
    change_row = conn.execute(
        """
        INSERT INTO proposed_change
            (workspace_id, chunk_id, kind, payload, confidence,
             provider, extractor_model, prompt_version, ontology_version)
        VALUES (%s, %s, 'add_relationship', %s, 1.0,
                'human', 'human-review', 'conflict-review-v1', %s)
        RETURNING id
        """,
        (
            row["workspace_id"],
            uuid.UUID(chunk_id),   # always a valid UUID string here (uuid4() fallback above)
            json.dumps(payload),
            ONTOLOGY_VERSION,
        ),
    ).fetchone()
    change_id = change_row["id"]

    # Immediately approve — this is a human decision, not an LLM proposal.
    store.approve(conn, driver, change_id, reviewer_id)

    # Mark the conflict row as approved and link to the change.
    conn.execute(
        """
        UPDATE entity_conflict
        SET status = 'approved', reviewed_by = %s, reviewed_at = now(), change_id = %s
        WHERE id = %s
        """,
        (reviewer_id, change_id, conflict_id),
    )

    return change_id


def reject_conflict(
    conn: psycopg.Connection,
    conflict_id: uuid.UUID,
    reviewer_id: uuid.UUID | None = None,
) -> None:
    """Reject a conflict — marks the pair as definitively distinct.

    The pair will never appear in the review queue again.
    No graph change is made.
    """
    updated = conn.execute(
        """
        UPDATE entity_conflict
        SET status = 'rejected', reviewed_by = %s, reviewed_at = now()
        WHERE id = %s AND status = 'pending'
        RETURNING id
        """,
        (reviewer_id, conflict_id),
    ).fetchone()
    if not updated:
        raise ValueError(f"No pending entity conflict: {conflict_id}")


def pending_conflicts(
    conn: psycopg.Connection,
    *,
    clearance: int = 4,
    limit: int = 50,
) -> list[dict]:
    """Return pending conflicts the reviewer is allowed to see.

    Ordered by similarity descending — high-confidence matches first,
    because those are the most likely true aliases and the cheapest to review.
    """
    return conn.execute(
        """
        SELECT id, name_a, type_a, name_b, type_b,
               similarity, quote_a, quote_b, sensitivity, created_at
        FROM entity_conflict
        WHERE status = 'pending' AND sensitivity <= %s
        ORDER BY similarity DESC, created_at ASC
        LIMIT %s
        """,
        (clearance, limit),
    ).fetchall()
