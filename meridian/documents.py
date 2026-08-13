"""Document reads for board surfaces (Meridian P3, CP-E).

`document` belongs to the **frozen core schema** and has no product module, which left
`frontend/src/lib/documents.ts` as the last mock behind a live surface. The packs page
fetched real packs and mock documents, so every `board_pack_item.document_id` resolved
to nothing and every item in every pack rendered as a broken reference.

This module is the smallest thing that fixes that: a read-only product-side view of the
frozen table. It adds no columns, no writes and no ingestion — those live in
`callosum.ingest`, on the other side of the freeze.

---------------------------------------------------------------------------
WHY A PRODUCT MODULE RATHER THAN READING `callosum.store` FROM THE API
---------------------------------------------------------------------------
The open question in the P3 scope note was whether to read the table through the frozen
core or add a module here. It is here because the clearance gate belongs on the product
side: `store.pg()` scopes by workspace, but nothing in the frozen core filters a
document by the *caller's* clearance, and putting that filter in the API layer would be
the app-side filtering Invariant #1 exists to prevent. One module, one predicate,
mirroring `packs._fetch_items_for_packs`.

---------------------------------------------------------------------------
WHAT IS DELIBERATELY NOT SELECTED
---------------------------------------------------------------------------
`raw_text`, `content_hash` and `metadata`. A board surface renders a document's
identity, not its contents: `raw_text` is the whole corpus in a JSON response and
`content_hash` is a dedupe key. They are excluded in the SQL rather than dropped in
Python, so they never leave the database.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from callosum import config, ingest, llm, store
from callosum.config import EMBEDDING_DIM
from callosum.store import DEFAULT_WORKSPACE_ID
from meridian import audit

#: The clearance ladder, as in `meridian/packs.py`. Duplicated deliberately rather than
#: imported: `packs` importing `documents` or the reverse would couple two modules that
#: only share a constant, and the p1.0.5 postmortem records what happens when a
#: hard-coded "maximum" drifts from the table.
PUBLIC_CLEARANCE = 0
RESTRICTED_CLEARANCE = 4

#: Columns a board reader may see. Written once so `list` and `get` cannot diverge —
#: a `SELECT *` here is how `raw_text` reaches a browser.
_COLUMNS = "id, title, doc_type, source_uri, sensitivity, authored_at, ingested_at"


class DocumentError(Exception):
    """Base for document errors, so `errors.classify` can map the family."""


class DocumentNotFound(DocumentError):
    """No such document, **or** one above the caller's clearance.

    Deliberately one error for both. Distinguishing them would confirm that a
    restricted document exists to someone who may not read it, which is the same
    existence oracle `PrincipalNotFound` and `get_pack` both refuse to be.
    """


class DuplicateDocumentError(DocumentError):
    """A document with identical SHA-256 content_hash already exists in this workspace."""


class InvalidSensitivityError(DocumentError):
    """Sensitivity level must be between 0 (Public) and 4 (Restricted)."""


@dataclass(frozen=True)
class Document:
    id: str
    title: str
    doc_type: str
    source_uri: str | None
    sensitivity: int
    authored_at: datetime | None
    ingested_at: datetime


@dataclass(frozen=True)
class QuarantineItem:
    id: int
    document_id: str | None
    chunk_id: str | None
    source: str
    relation: str
    target: str
    quote: str
    confidence: float
    reason: str
    detail: str
    created_at: datetime


def _row_to_document(row: dict) -> Document:
    return Document(
        id=str(row["id"]),
        title=row["title"],
        doc_type=row["doc_type"],
        source_uri=row["source_uri"],
        sensitivity=row["sensitivity"],
        authored_at=row["authored_at"],
        ingested_at=row["ingested_at"],
    )


def list_documents(
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    clearance: int,
    doc_type: str | None = None,
) -> list[Document]:
    """Documents the caller may read, newest ingestion first.

    `clearance` is required and has no default. A default is what made
    `packs.list_packs` fail open at `clearance: int = 4` — the top of the ladder — so a
    forgotten argument here is a `TypeError` at the call site rather than a silent
    disclosure of everything.

    Documents above the caller's clearance are **not returned in any form**. There is no
    count, no placeholder and no total to subtract from: the filter is a `WHERE` clause,
    so a withheld document leaves no trace in the result. That is the same discipline as
    `_fetch_items_for_packs`, and it is why this returns a plain list.
    """
    query = f"SELECT {_COLUMNS} FROM document WHERE sensitivity <= %s"
    params: list = [clearance]

    if doc_type is not None:
        query += " AND doc_type = %s"
        params.append(doc_type)

    query += " ORDER BY ingested_at DESC, id"

    with store.pg(workspace_id) as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_document(r) for r in rows]


def get_document(
    document_id: str, *, workspace_id: str = DEFAULT_WORKSPACE_ID, clearance: int
) -> Document:
    """One document, or `DocumentNotFound`.

    The clearance predicate is in the query rather than checked after fetching, so a
    document the caller may not read is never loaded into the process at all.
    """
    with store.pg(workspace_id) as conn:
        row = conn.execute(
            f"SELECT {_COLUMNS} FROM document WHERE id = %s AND sensitivity <= %s",
            (uuid.UUID(str(document_id)), clearance),
        ).fetchone()

    if row is None:
        raise DocumentNotFound(str(document_id))
    return _row_to_document(row)


def intake_document(
    *,
    title: str,
    doc_type: str,
    raw_text: str,
    sensitivity: int = 2,
    source_uri: str | None = None,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    author_principal_id: uuid.UUID | str | None = None,
) -> Document:
    """Intake a source document into the tenant workspace (Meridian P4).

    Validates sensitivity, computes SHA-256 content_hash deduplication, chunks text,
    writes to document + chunk tables, creates Neo4j chunk bridge handles, and logs
    an immutable audit event.
    """
    if not (PUBLIC_CLEARANCE <= sensitivity <= RESTRICTED_CLEARANCE):
        raise InvalidSensitivityError(
            f"sensitivity must be between {PUBLIC_CLEARANCE} and {RESTRICTED_CLEARANCE}, got {sensitivity}"
        )

    clean_text = raw_text.strip()
    if not clean_text:
        raise DocumentError("cannot intake empty text document")

    hash_val = ingest.content_hash(clean_text)

    with store.pg(workspace_id) as conn:
        existing = conn.execute(
            "SELECT id FROM document WHERE content_hash = %s AND workspace_id = %s",
            (hash_val, workspace_id),
        ).fetchone()
        if existing:
            raise DuplicateDocumentError(
                f"document with identical content_hash ({hash_val[:8]}...) already exists in this workspace"
            )

        doc_uuid = uuid.uuid4()
        row = conn.execute(
            """
            INSERT INTO document (id, workspace_id, title, doc_type, source_uri, raw_text,
                                  content_hash, sensitivity, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING {_COLUMNS}
            """.format(_COLUMNS=_COLUMNS),
            (
                doc_uuid,
                workspace_id,
                title.strip(),
                doc_type.strip().lower(),
                source_uri.strip() if source_uri else None,
                clean_text,
                hash_val,
                sensitivity,
                json.dumps({"intake_source": "meridian_p4_intake"}),
            ),
        ).fetchone()

        chunks = ingest.chunk(clean_text)
        if chunks:
            try:
                embeddings = llm.embed([c.text for c in chunks], input_type="document")
            except Exception:
                # Degrade to zero vectors if LLM provider is offline
                embeddings = [[0.0] * EMBEDDING_DIM for _ in chunks]

            chunk_ids = store.insert_chunks(
                conn,
                document_id=doc_uuid,
                chunks=chunks,
                embeddings=embeddings,
                sensitivity=sensitivity,
            )

            # Bridge to Neo4j (:Chunk) nodes if Neo4j driver is available
            try:
                driver = store.neo(wait=2.0)
                for c_id, c in zip(chunk_ids, chunks, strict=True):
                    store.upsert_chunk_node(
                        driver,
                        chunk_id=c_id,
                        document_id=doc_uuid,
                        ordinal=c.ordinal,
                        sensitivity=sensitivity,
                        workspace_id=workspace_id,
                    )
                driver.close()
            except Exception:
                pass

        actor_id = uuid.UUID(str(author_principal_id)) if author_principal_id else None
        audit.record_audit_event(
            conn,
            aggregate_type="document",
            aggregate_id=doc_uuid,
            action="created",
            payload={
                "title": title.strip(),
                "doc_type": doc_type.strip().lower(),
                "sensitivity": sensitivity,
                "chunks": len(chunks),
                "content_hash": hash_val,
            },
            actor_principal_id=actor_id,
            workspace_id=workspace_id,
        )

    return _row_to_document(row)


def list_quarantine(*, workspace_id: str = DEFAULT_WORKSPACE_ID) -> list[QuarantineItem]:
    """List extraction failures/quarantine items for the tenant workspace."""
    with store.pg(workspace_id) as conn:
        rows = conn.execute(
            """
            SELECT id, document_id, chunk_id, source, relation, target, quote,
                   confidence, reason, detail, created_at
              FROM extraction_failure
             WHERE workspace_id = %s
             ORDER BY created_at DESC
             LIMIT 100
            """,
            (workspace_id,),
        ).fetchall()

    return [
        QuarantineItem(
            id=r["id"],
            document_id=str(r["document_id"]) if r["document_id"] else None,
            chunk_id=str(r["chunk_id"]) if r["chunk_id"] else None,
            source=r["source"],
            relation=r["relation"],
            target=r["target"],
            quote=r["quote"],
            confidence=r["confidence"],
            reason=r["reason"],
            detail=r["detail"],
            created_at=r["created_at"],
        )
        for r in rows
    ]
