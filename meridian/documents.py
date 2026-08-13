"""Document intake and institutional memory lifecycle (Meridian P4).

This module owns document ingestion, chunking, embedding generation, Neo4j chunk
bridging, verified extraction integration, clearance-gated document retrieval, and
quarantine reporting.

Invariants strictly enforced:
  1. No zero-vector corruption: if embedding generation fails, intake fails loudly.
  2. Neo4j graph bridge integrity: chunk nodes must be successfully upserted.
  3. Database-level deduplication: content_hash unique constraint per workspace.
  4. Verified extraction pipeline: verified claims queued for human approval; unverified claims quarantined.
  5. Clearance filtering: documents above caller clearance are completely invisible (fail-closed).
"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg

from callosum import extract, ingest, llm, store
from callosum.store import DEFAULT_WORKSPACE_ID
from meridian import audit


class DocumentError(Exception):
    """Base exception for document operations."""


class DocumentNotFound(DocumentError):
    """Document does not exist or caller clearance is insufficient to observe it."""


class DuplicateDocumentError(DocumentError):
    """Document with identical content hash already exists in this tenant workspace."""


class InvalidSensitivityError(DocumentError):
    """Sensitivity level outside the valid clearance ladder (0..3)."""


class EmbeddingProviderError(DocumentError):
    """Embedding generation failed; cannot index document into vector store."""


class GraphStoreError(DocumentError):
    """Neo4j graph store operation failed during chunk node bridging."""


@dataclass(frozen=True)
class Document:
    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    doc_type: str
    source_uri: str | None
    raw_text: str
    content_hash: str
    sensitivity: int
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class QuarantineItem:
    id: uuid.UUID
    workspace_id: uuid.UUID
    document_id: uuid.UUID | None
    chunk_id: uuid.UUID | None
    source: str
    relation: str
    target: str
    quote: str
    confidence: float
    reason: str
    detail: str
    provider: str
    extractor_model: str
    created_at: datetime


_COLUMNS = (
    "id, workspace_id, title, doc_type, source_uri, raw_text, content_hash, "
    "sensitivity, metadata, created_at, updated_at"
)


def _row_to_document(row: dict[str, Any]) -> Document:
    meta = row["metadata"]
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}
    elif meta is None:
        meta = {}

    return Document(
        id=row["id"],
        workspace_id=row["workspace_id"],
        title=row["title"],
        doc_type=row["doc_type"],
        source_uri=row["source_uri"],
        raw_text=row["raw_text"],
        content_hash=row["content_hash"],
        sensitivity=row["sensitivity"],
        metadata=meta,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_quarantine(row: dict[str, Any]) -> QuarantineItem:
    return QuarantineItem(
        id=row["id"],
        workspace_id=row["workspace_id"],
        document_id=row["document_id"],
        chunk_id=row["chunk_id"],
        source=row["source"],
        relation=row["relation"],
        target=row["target"],
        quote=row["quote"] or "",
        confidence=float(row["confidence"] or 0.0),
        reason=row["reason"],
        detail=row["detail"] or "",
        provider=row["provider"],
        extractor_model=row["extractor_model"],
        created_at=row["created_at"],
    )


def intake_document(
    *,
    title: str,
    doc_type: str,
    raw_text: str,
    sensitivity: int,
    workspace_id: str | uuid.UUID = DEFAULT_WORKSPACE_ID,
    author_principal_id: str | uuid.UUID | None = None,
    source_uri: str | None = None,
    extract_proposals: bool = False,
) -> Document:
    """Intake a source document into tenant memory.

    Performs deduplication, chunking, embedding, graph bridge node creation,
    optional verified extraction, and audit logging within an atomic transaction.
    """
    if not title or not title.strip():
        raise DocumentError("Document title cannot be empty.")
    if sensitivity not in (0, 1, 2, 3):
        raise InvalidSensitivityError(f"Invalid sensitivity: {sensitivity}. Must be 0, 1, 2, or 3.")

    clean_text = raw_text.strip()
    if not clean_text:
        raise DocumentError("Document text cannot be empty.")

    ws_uuid = uuid.UUID(str(workspace_id))
    hash_val = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()

    # Pre-check deduplication
    with store.pg(str(ws_uuid)) as check_conn:
        existing = check_conn.execute(
            "SELECT id FROM document WHERE workspace_id = %s AND content_hash = %s",
            (ws_uuid, hash_val),
        ).fetchone()
        if existing:
            raise DuplicateDocumentError(
                f"Document with content hash '{hash_val}' already exists in this workspace"
            )

    # Chunk text with true character offsets
    chunks = ingest.chunk(clean_text)
    embeddings: list[list[float]] = []
    if chunks:
        try:
            embeddings = llm.embed([c.text for c in chunks], input_type="document")
        except Exception as exc:
            raise EmbeddingProviderError(f"Embedding generation failed: {exc}") from exc

    doc_uuid = uuid.uuid4()
    with store.pg(str(ws_uuid)) as conn:
        try:
            row = conn.execute(
                f"""
                INSERT INTO document (id, workspace_id, title, doc_type, source_uri, raw_text,
                                      content_hash, sensitivity, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING {_COLUMNS}
                """,
                (
                    doc_uuid,
                    ws_uuid,
                    title.strip(),
                    doc_type.strip().lower(),
                    source_uri.strip() if source_uri else None,
                    clean_text,
                    hash_val,
                    sensitivity,
                    json.dumps({"intake_source": "meridian_p4_intake"}),
                ),
            ).fetchone()
        except psycopg.errors.UniqueViolation as exc:
            raise DuplicateDocumentError(
                f"Document with content hash '{hash_val}' already exists in this workspace"
            ) from exc

        chunk_ids: list[uuid.UUID] = []
        if chunks:
            chunk_ids = store.insert_chunks(
                conn,
                document_id=doc_uuid,
                chunks=chunks,
                embeddings=embeddings,
                sensitivity=sensitivity,
                workspace_id=str(ws_uuid),
            )

            # Bridge to Neo4j (:Chunk) nodes
            try:
                driver = store.neo(wait=2.0)
                for c_id, c in zip(chunk_ids, chunks, strict=True):
                    store.upsert_chunk_node(
                        driver,
                        chunk_id=c_id,
                        document_id=doc_uuid,
                        ordinal=c.ordinal,
                        sensitivity=sensitivity,
                        workspace_id=str(ws_uuid),
                    )
            except Exception as exc:
                raise GraphStoreError(f"Failed to upsert Neo4j chunk nodes: {exc}") from exc

        # Optional verified extraction into proposals and quarantine
        queued_count = 0
        quarantine_count = 0
        if extract_proposals and chunks:
            stamp = extract.stamp()
            for cid, c in zip(chunk_ids, chunks, strict=True):
                verified = extract.extract(c.text)
                q, bad = store.queue_proposals(
                    conn,
                    document_id=doc_uuid,
                    chunk_id=cid,
                    chunk_start=c.start_char,
                    chunk_text=c.text,
                    verified=verified,
                    stamp=stamp,
                    workspace_id=str(ws_uuid),
                )
                queued_count += q
                quarantine_count += bad

        # Record structured audit event
        audit.record_audit_event(
            conn,
            aggregate_type="document",
            aggregate_id=doc_uuid,
            action="created",
            actor_principal_id=author_principal_id,
            payload={
                "title": title.strip(),
                "doc_type": doc_type.strip().lower(),
                "sensitivity": sensitivity,
                "content_hash": hash_val,
                "chunks_count": len(chunks),
                "proposals_queued": queued_count,
                "quarantined_failures": quarantine_count,
            },
            workspace_id=str(ws_uuid),
        )

        return _row_to_document(row)


def get_document(
    document_id: str | uuid.UUID,
    *,
    workspace_id: str | uuid.UUID = DEFAULT_WORKSPACE_ID,
    clearance: int = 0,
) -> Document:
    """Fetch a document by ID, enforcing clearance and tenant isolation."""
    doc_uuid = uuid.UUID(str(document_id))
    ws_uuid = uuid.UUID(str(workspace_id))

    with store.pg(str(ws_uuid)) as conn:
        row = conn.execute(
            f"""
            SELECT {_COLUMNS}
            FROM document
            WHERE id = %s AND workspace_id = %s
            """,
            (doc_uuid, ws_uuid),
        ).fetchone()

        if not row:
            raise DocumentNotFound(f"Document {document_id} not found")

        # Fail-closed clearance gate: higher sensitivity document is invisible
        if row["sensitivity"] > clearance:
            raise DocumentNotFound(f"Document {document_id} not found or above clearance")

        return _row_to_document(row)


def list_documents(
    *,
    workspace_id: str | uuid.UUID = DEFAULT_WORKSPACE_ID,
    clearance: int = 0,
) -> list[Document]:
    """List documents in a workspace filtered by caller clearance."""
    ws_uuid = uuid.UUID(str(workspace_id))

    with store.pg(str(ws_uuid)) as conn:
        rows = conn.execute(
            f"""
            SELECT {_COLUMNS}
            FROM document
            WHERE workspace_id = %s AND sensitivity <= %s
            ORDER BY created_at DESC
            """,
            (ws_uuid, clearance),
        ).fetchall()

        return [_row_to_document(r) for r in rows]


def list_quarantine(
    *,
    workspace_id: str | uuid.UUID = DEFAULT_WORKSPACE_ID,
) -> list[QuarantineItem]:
    """List extraction failures / quarantine items for the tenant workspace."""
    ws_uuid = uuid.UUID(str(workspace_id))

    with store.pg(str(ws_uuid)) as conn:
        rows = conn.execute(
            """
            SELECT id, workspace_id, document_id, chunk_id, source, relation, target,
                   quote, confidence, reason, detail, provider, extractor_model, created_at
            FROM extraction_failure
            WHERE workspace_id = %s
            ORDER BY created_at DESC
            """,
            (ws_uuid,),
        ).fetchall()

        return [_row_to_quarantine(r) for r in rows]
