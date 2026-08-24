"""Document intake, reads, and institutional memory lifecycle (Meridian P4).

This module owns document ingestion, chunking, embedding generation, Neo4j chunk
bridging, verified extraction, clearance-gated document retrieval, and quarantine
reporting.

---------------------------------------------------------------------------
INVARIANTS
---------------------------------------------------------------------------
1. **Never returns raw corpus text**: `_COLUMNS` excludes `raw_text`, `content_hash`,
   and `metadata`. A board surface renders a document's identity, not its contents.
2. **Clearance-filtered (fail-closed)**: `clearance` is a required argument on **every**
   read path, quarantine included. A document above the caller's clearance is absent
   (404), never redacted.
3. **No zero-vector corruption (Option A)**: If embedding generation fails, intake
   aborts immediately with `EmbeddingProviderError` without writing corrupt vectors.
4. **Graph bridge integrity, by replay rather than by compensation**: chunk ids are
   derived deterministically, so the graph write is idempotent and a crashed intake
   heals on retry. See `_chunk_id`.
5. **Deduplication**: Multi-tenant deduplication by `(workspace_id, content_hash)`.
6. **Mandatory verified extraction**: All ingested chunks undergo quote verification;
   verified claims are queued in `proposed_change` and unverified claims in
   `extraction_failure`. Extraction holds **no** database connection.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg

from callosum import extract, graph, ingest, llm, store
from callosum.store import DEFAULT_WORKSPACE_ID
from meridian import audit

log = logging.getLogger(__name__)

#: Columns a board reader may see. Excludes raw_text, content_hash, and metadata.
_COLUMNS = "id, title, doc_type, source_uri, sensitivity, authored_at, ingested_at"

#: The full clearance ladder, from `schema/postgres.sql`. Mirrored as a constant so the
#: gap below is checkable in a test rather than being two numbers in two files that
#: drift apart silently.
LADDER_LEVELS = (0, 1, 2, 3, 4)  # public, investor, internal, confidential, restricted

#: What intake accepts. **Deliberately narrower than the ladder** — `4 restricted` is
#: founder-only and reserved pending the policy questions in #143: who may create at
#: that level, whether founder-only is a role or a clearance, and what audit it carries.
#: Widening this without answering them would open the write-side hole that
#: `SensitivityAboveClearanceError` exists to close, at the most sensitive tier there is.
ACCEPTED_SENSITIVITIES = (0, 1, 2, 3)

#: Namespace for the deterministic document/chunk ids minted below. A fixed constant,
#: never regenerated — changing it would make every future retry mint new ids and
#: silently break the replay-safety this exists to provide.
_INTAKE_NAMESPACE = uuid.UUID("038ccca2-775d-569a-8895-712bfe0451bd")

#: Reason recorded when extraction *raised* for a chunk, as opposed to running and
#: rejecting an edge. Deliberately not a `callosum.ontology.FailureReason`: those four
#: values are verdicts the verifier reached about an edge the model emitted, and this is
#: the absence of any edge at all. Adding it to that enum would also mean an
#: `ONTOLOGY_VERSION` bump, which would restamp every eval row for a product-layer
#: concern.
_EXTRACTION_ERROR = "extraction_error"


def _chunk_id(workspace_id: uuid.UUID, content_hash: str, ordinal: int) -> uuid.UUID:
    """The chunk's id, derived rather than random — so a retry replays onto the graph.

    `AGENTS.md` invariant 7 makes graph-first writes safe *because* `MERGE` is
    idempotent: a crash is repaired by re-running. A `uuid4()` per attempt breaks that —
    a retry does not replay onto the same nodes, it MERGEs a **second** set, and because
    the first attempt never committed to Postgres the content-hash pre-check does not
    catch the retry either. Those orphans have ids that exist nowhere in Postgres, so
    nothing can ever collect them.

    **`workspace_id` is in the key, and that is not decoration.** Migration `0022`
    deliberately scopes dedup to `(workspace_id, content_hash)` so two tenants may hold
    byte-identical documents. Derive the id from the hash alone and those two tenants
    mint the *same* chunk ids — and `MERGE` would then fuse their bridge nodes into one,
    which is a cross-tenant leak created by the very migration that permits the
    duplicate. Verified: `uuid5(ns, f"{h}:0")` collides across workspaces;
    `uuid5(ns, f"{ws}:{h}:0")` does not.
    """
    return uuid.uuid5(_INTAKE_NAMESPACE, f"{workspace_id}:{content_hash}:{ordinal}")


def _document_id(workspace_id: uuid.UUID, content_hash: str) -> uuid.UUID:
    """The document's id, derived on the same principle and the same key material.

    Consistent with the `(workspace_id, content_hash)` unique index: one document per
    content per tenant, so its identity may as well *be* that pair. A retry after a
    crashed intake therefore rebuilds the identical document and chunk nodes rather than
    a parallel set.
    """
    return uuid.uuid5(_INTAKE_NAMESPACE, f"{workspace_id}:{content_hash}")


class DocumentError(Exception):
    """Base for document domain errors."""


class DocumentNotFound(DocumentError):
    """No such document, or one above the caller's clearance."""


class DuplicateDocumentError(DocumentError):
    """Document with identical content hash already exists in this tenant workspace."""


class InvalidSensitivityError(DocumentError):
    """Sensitivity level outside the range intake accepts (0..3).

    **Not the full ladder.** `schema/postgres.sql` defines five levels, 0..4, and
    `4 restricted` (founder-only) is deliberately not reachable through intake — see
    the decision on #143. Until it is settled who may create restricted documents,
    whether founder-only is a role or a clearance, and what audit that carries, the
    bound stays at 3 by decision rather than by oversight.

    This docstring used to read "the valid clearance ladder (0..3)", which is what made
    an intentional bound look like an off-by-one against a five-level ladder.
    """


class SensitivityAboveClearanceError(DocumentError):
    """A principal tried to file a document above their own clearance.

    Named for the authority rule rather than the comparison: the caller is not
    permitted to create at that level, which is a different statement from the value
    being out of range (`InvalidSensitivityError`). The two must stay distinguishable —
    a client that cannot tell them apart cannot tell the user whether to pick a lower
    level or ask for clearance.

    **The refusal is a refusal, never a clamp** (#143). Filing at a lower level than
    asked would tell the caller their document is protected at a level it is not.
    """


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


def _row_to_document(row: dict[str, Any]) -> Document:
    return Document(
        id=str(row["id"]),
        title=row["title"],
        doc_type=row["doc_type"],
        source_uri=row["source_uri"],
        sensitivity=row["sensitivity"],
        authored_at=row["authored_at"],
        ingested_at=row["ingested_at"],
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


def list_documents(
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    clearance: int,
    doc_type: str | None = None,
) -> list[Document]:
    """Documents the caller may read, newest ingestion first.

    `clearance` is required. Documents above clearance are omitted in the SQL WHERE
    clause, leaving no trace in the response.
    """
    query = f"SELECT {_COLUMNS} FROM document WHERE sensitivity <= %s"
    params: list[Any] = [clearance]

    if doc_type is not None:
        query += " AND doc_type = %s"
        params.append(doc_type)

    query += " ORDER BY ingested_at DESC, id"

    with store.pg(workspace_id) as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_document(r) for r in rows]


def get_document(
    document_id: str,
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    clearance: int,
) -> Document:
    """One document, or `DocumentNotFound` if absent or above clearance."""
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
    sensitivity: int,
    author_clearance: int,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    author_principal_id: str | None = None,
    source_uri: str | None = None,
) -> Document:
    """Intake a source document into tenant memory.

    Validation → dedup → chunking → embeddings → Neo4j bridge → Postgres commit →
    audit → verified extraction, in that order.

    **The graph is written before Postgres commits, and that ordering is deliberate**
    (`AGENTS.md` invariant 7). It is safe here for the same reason it is safe in
    `store.approve()`: the write is idempotent, because `MERGE` is idempotent *and* the
    ids are derived rather than random. A crash between the two stores leaves bridge
    nodes that the next attempt MERGEs onto rather than duplicating. The compensating
    delete below is a fast path that spares the retry, not the thing correctness rests
    on.

    Extraction happens last and holds **no** connection while it runs.
    """
    if not title or not title.strip():
        raise DocumentError("Document title cannot be empty.")
    if sensitivity not in ACCEPTED_SENSITIVITIES:
        raise InvalidSensitivityError(f"Invalid sensitivity: {sensitivity}. Must be 0, 1, 2, or 3.")
    # Enforced here rather than at the API boundary so it holds for every caller, not
    # only the HTTP one. The read paths have always filtered on clearance; until #143
    # this write path consulted it nowhere, so a clearance-1 principal could file a
    # confidential document and then be unable to read back what they had just created.
    if sensitivity > author_clearance:
        raise SensitivityAboveClearanceError(
            f"Sensitivity {sensitivity} is above your clearance ({author_clearance}). "
            f"You may file at level {author_clearance} or below."
        )

    clean_text = raw_text.strip()
    if not clean_text:
        raise DocumentError("Document text cannot be empty.")

    ws_uuid = uuid.UUID(str(workspace_id))
    hash_val = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()

    # Pre-check deduplication in the workspace.
    #
    # **There is deliberately no clearance predicate here, and it is not an oversight
    # (#147, ADR-016).** A caller at any clearance who submits content already filed in
    # this workspace is told so, even when the existing document sits above their
    # clearance.
    #
    # That is a one-bit existence hint, and it was accepted rather than closed because
    # the alternatives are worse:
    #
    #   * Adding `AND sensitivity <= %s` does not close it. The pre-check then passes,
    #     the INSERT hits `uq_document_workspace_content_hash`, and the handler below
    #     raises the identical `DuplicateDocumentError` — after burning an embedding
    #     round-trip and a Neo4j write on the way. The oracle is a property of
    #     content-addressed dedup, not of where the predicate sits.
    #   * Answering as though the ingest succeeded returns a 201 for a document that
    #     does not exist, which every client that trusts the response would display.
    #   * Filing a second row at the caller's level means dropping the per-workspace
    #     hash uniqueness `0022` established, and the same text in the corpus twice.
    #
    # The disclosure is bounded by what triggering it costs: the caller must submit the
    # exact bytes, so they already hold the entire content. They learn one bit about
    # their own workspace and nothing about the document.
    #
    # **Accepted is not the same as ignored: it is made visible instead.** Every
    # duplicate refusal is audited — including the ones the caller could have read, so
    # that the presence of an audit row is not itself the disclosure (ADR-016). Probing
    # this oracle therefore leaves a trail, which is the control that replaces the
    # closure we could not have.
    #
    # **The error must never name the matched document.** `existing["id"]` is in scope
    # here and is deliberately discarded — returning it would turn a content-existence
    # hint into a title disclosure, which is the first item in P4's exit criterion.
    # Cross-workspace is prevented twice over, by the predicate below and by RLS.
    with store.pg(str(ws_uuid)) as check_conn:
        existing = check_conn.execute(
            "SELECT id, sensitivity FROM document WHERE workspace_id = %s AND content_hash = %s",
            (ws_uuid, hash_val),
        ).fetchone()
        if existing:
            _record_duplicate_refusal(
                workspace_id=ws_uuid,
                existing_id=existing["id"],
                existing_sensitivity=existing["sensitivity"],
                actor_principal_id=author_principal_id,
                author_clearance=author_clearance,
                content_hash=hash_val,
            )
            raise DuplicateDocumentError(
                f"Document with content hash '{hash_val}' already exists in this workspace"
            )

    # Chunk text preserving exact character offsets.
    chunks = ingest.chunk(clean_text)

    # No try/except here on purpose. `llm.embed` is the provider boundary and already
    # raises `EmbeddingProviderError` for every way a backend can fail; re-wrapping a
    # bare `Exception` at this call site would relabel a `TypeError` in our own code as
    # "provider unreachable", which sends an operator to check a service that is up.
    embeddings: list[list[float]] = (
        llm.embed([c.text for c in chunks], input_type="document") if chunks else []
    )

    doc_uuid = _document_id(ws_uuid, hash_val)
    chunk_ids = [_chunk_id(ws_uuid, hash_val, c.ordinal) for c in chunks]

    neo_driver = None
    try:
        if chunks:
            try:
                neo_driver = store.neo(wait=2.0)
                _bridge_chunk_nodes(
                    neo_driver,
                    doc_uuid=doc_uuid,
                    chunk_ids=chunk_ids,
                    chunks=chunks,
                    sensitivity=sensitivity,
                    workspace_id=ws_uuid,
                )
            except Exception as exc:
                raise graph.GraphStoreError(
                    f"Failed to bridge chunk nodes to Neo4j: {exc}"
                ) from exc

        # Insert into Postgres
        try:
            with store.pg(str(ws_uuid)) as conn:
                row = conn.execute(
                    """
                    INSERT INTO document (id, workspace_id, title, doc_type, source_uri, raw_text,
                                          content_hash, sensitivity, authored_by, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, title, doc_type, source_uri, sensitivity, authored_at, ingested_at
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
                        uuid.UUID(str(author_principal_id)) if author_principal_id else None,
                        json.dumps({"intake_source": "meridian_p4_intake"}),
                    ),
                ).fetchone()

                # Insert chunks with the derived chunk UUIDs
                for c, cid, vector in zip(chunks, chunk_ids, embeddings, strict=True):
                    conn.execute(
                        """
                        INSERT INTO chunk (id, workspace_id, document_id, ordinal, text, start_char, end_char,
                                           sensitivity, embedding)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (cid, ws_uuid, doc_uuid, c.ordinal, c.text, c.start_char, c.end_char, sensitivity, vector),
                    )

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
                    },
                    workspace_id=str(ws_uuid),
                )
        except psycopg.errors.UniqueViolation as exc:
            _try_unbridge(neo_driver, chunk_ids, ws_uuid)
            # The race: another intake committed the same content between the pre-check
            # and this INSERT. The caller receives the identical 409, so they learn the
            # identical fact — auditing only the pre-check path would leave a hole in
            # the trail exactly where concurrency put it. Re-queried rather than assumed,
            # because the row that won the race is the one this refusal is about.
            _audit_race_refusal(
                workspace_id=ws_uuid,
                content_hash=hash_val,
                actor_principal_id=author_principal_id,
                author_clearance=author_clearance,
            )
            raise DuplicateDocumentError(
                f"Document with content hash '{hash_val}' already exists in this workspace"
            ) from exc
        except Exception:
            _try_unbridge(neo_driver, chunk_ids, ws_uuid)
            raise
    finally:
        # `store.neo()` builds a fresh driver — and therefore a fresh connection pool —
        # on every call. The CLI is one-shot and never had to care; this is a request
        # path, so without this every intake leaks one.
        if neo_driver is not None:
            neo_driver.close()

    # --- Verified extraction, holding nothing -------------------------------------
    #
    # Extract first, with no connection open, then write in one short transaction.
    # The previous shape called `extract.extract()` — a provider round trip with a 300s
    # timeout — *inside* an open transaction, once per chunk: a 20-chunk document could
    # hold a write transaction for an hour and a half. Worse, `queue_proposals` wrote
    # into that same transaction, so a failure on chunk 19 rolled back the 18 sets of
    # proposals already queued, and a bare `except: pass` then swallowed the fact that
    # anything had happened at all.
    #
    # That combination could discard rejected extractions, which `AGENTS.md` invariant 3
    # forbids outright: "Never discard a rejected extraction." A chunk whose extraction
    # *raises* is now recorded too — as a quarantine row with `_EXTRACTION_ERROR` and the
    # exception in `detail` — so "nothing was extracted here" is never silently
    # indistinguishable from "nothing was found here".
    if chunks:
        stamp = extract.stamp()
        extracted: list[tuple[uuid.UUID, Any, Any]] = []
        failed: list[tuple[uuid.UUID, Any, Exception]] = []

        for cid, c in zip(chunk_ids, chunks, strict=True):
            try:
                extracted.append((cid, c, extract.extract(c.text)))
            except Exception as exc:  # noqa: BLE001 — recorded, not swallowed
                log.exception(
                    "extraction failed for chunk %s of document %s", cid, doc_uuid
                )
                failed.append((cid, c, exc))

        try:
            with store.pg(str(ws_uuid)) as ext_conn:
                for cid, c, verified in extracted:
                    store.queue_proposals(
                        ext_conn,
                        document_id=doc_uuid,
                        chunk_id=cid,
                        chunk_start=c.start_char,
                        chunk_text=c.text,
                        verified=verified,
                        stamp=stamp,
                        workspace_id=str(ws_uuid),
                    )
                for cid, c, exc in failed:
                    _record_extraction_error(
                        ext_conn,
                        document_id=doc_uuid,
                        chunk_id=cid,
                        chunk_text=c.text,
                        exc=exc,
                        stamp=stamp,
                        workspace_id=ws_uuid,
                    )
        except Exception:
            # The document and its chunks are committed and correct; the proposal queue
            # is not. Logged with the exception rather than passed, so a systematically
            # empty queue is visible instead of looking like a corpus with nothing in it.
            log.exception(
                "failed to record extraction results for document %s; the document is "
                "committed but its proposals and quarantine rows are not",
                doc_uuid,
            )

    return _row_to_document(row)


def _bridge_chunk_nodes(
    driver,
    *,
    doc_uuid: uuid.UUID,
    chunk_ids: list[uuid.UUID],
    chunks: list,
    sensitivity: int,
    workspace_id: uuid.UUID,
) -> None:
    """Write the `(:Chunk)` bridge nodes for this document.

    Lives here rather than in `store.py` because it contains no Cypher of its own — it
    is a loop over the already-public `store.upsert_chunk_node`, so nothing about it
    needs the frozen core or the gateway. It is also not called `..._batch`: it opens one
    session per node, and a name that promises batching the implementation does not do is
    worse than no name at all. Making it a true `UNWIND` batch means a new gateway method,
    which is worth doing when the node count justifies it and not before.
    """
    for cid, c in zip(chunk_ids, chunks, strict=True):
        store.upsert_chunk_node(
            driver,
            chunk_id=cid,
            document_id=doc_uuid,
            ordinal=c.ordinal,
            sensitivity=sensitivity,
            workspace_id=str(workspace_id),
        )


def _try_unbridge(driver, chunk_ids: list[uuid.UUID], workspace_id: uuid.UUID) -> None:
    """Best-effort removal of bridge nodes after a failed Postgres write.

    **Guarded, and deliberately so.** If this raises, its exception would replace the one
    that actually explains the failure — and the likeliest cause of the Postgres write
    failing is an outage that will take this down too, so the failure you would most want
    to read is exactly the one that would be masked. The original propagates; this one is
    logged.

    Correctness does not rest on this succeeding. The ids are derived (`_chunk_id`), so a
    retry MERGEs onto the same nodes rather than orphaning a second set. This only spares
    the retry the work.
    """
    if driver is None or not chunk_ids:
        return
    try:
        gateway = graph.GraphGateway(driver)
        ctx = graph.GraphContext(workspace_id=str(workspace_id))
        gateway.delete_chunk_nodes(ctx, list(chunk_ids))
    except Exception:  # noqa: BLE001 — must never mask the original failure
        log.exception(
            "compensating delete of %d chunk node(s) failed; they will be reclaimed by "
            "MERGE on the next intake of the same document",
            len(chunk_ids),
        )


def _record_extraction_error(
    conn: psycopg.Connection,
    *,
    document_id: uuid.UUID,
    chunk_id: uuid.UUID,
    chunk_text: str,
    exc: Exception,
    stamp: dict[str, str],
    workspace_id: uuid.UUID,
) -> None:
    """Quarantine a chunk whose extraction raised, rather than losing it.

    `source`, `relation`, `target` and `quote` are left NULL because no edge was ever
    emitted — this row says "extraction did not run to completion here", which is a
    different fact from "the verifier rejected this edge", and writing a synthetic edge
    to fill the columns would record a claim the model never made.
    """
    conn.execute(
        """
        INSERT INTO extraction_failure
            (workspace_id, document_id, chunk_id, reason, detail,
             provider, extractor_model, prompt_version, ontology_version, chunk_chars)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            workspace_id,
            document_id,
            chunk_id,
            _EXTRACTION_ERROR,
            f"{type(exc).__name__}: {exc}",
            stamp["provider"],
            stamp["extractor_model"],
            stamp["prompt_version"],
            stamp["ontology_version"],
            len(chunk_text),
        ),
    )



def _record_duplicate_refusal(
    *,
    workspace_id: uuid.UUID,
    existing_id: uuid.UUID,
    existing_sensitivity: int,
    actor_principal_id: str | None,
    author_clearance: int,
    content_hash: str,
) -> None:
    """Record that intake refused a submission as a duplicate (ADR-016).

    The dedup pre-check is an existence oracle: submitting content already filed above
    your clearance returns 409, which tells you the workspace holds it. That cannot be
    closed cheaply — the alternatives are in the ADR — so it is accepted and made
    **detectable** instead. This is the trail.

    **Every refusal is recorded, not only the ones the actor could not read.** If only
    the hidden collisions produced a row, the presence of a row would itself be the
    disclosure, and the audit trail would become a second copy of the oracle for whoever
    can read it. `actor_could_read` carries the distinction in the payload instead.

    Written on its own connection, deliberately. `record_audit_event`'s contract is that
    it runs inside the mutating transaction so the two roll back together — but here
    there is no mutation to be atomic with. The intake is refused; the only thing to
    persist is that it was attempted.

    Failure to audit must not convert a 409 into a 500: the caller's answer is correct
    either way, and losing the trail is worse reported than raised. `AGENTS.md` invariant
    3's discipline applies — logged with the exception, never silently passed.

    **Depends on D7.** `aggregate_id` is the existing document's id, which is the correct
    aggregate for this event and is also the identifier the oracle would disclose. There
    is no audit read endpoint today. If one is built, it must be clearance-aware or this
    row hands back exactly what the refusal withheld.
    """
    actor_could_read = existing_sensitivity <= author_clearance
    try:
        with store.pg(str(workspace_id)) as conn:
            audit.record_audit_event(
                conn,
                aggregate_type="document",
                aggregate_id=existing_id,
                action="intake_duplicate_refused",
                actor_principal_id=actor_principal_id,
                payload={
                    "content_hash": content_hash,
                    "actor_clearance": author_clearance,
                    "actor_could_read": actor_could_read,
                },
                workspace_id=str(workspace_id),
            )
    except Exception:  # noqa: BLE001 — a lost trail must not become a 500
        log.exception(
            "failed to audit a refused duplicate intake in workspace %s "
            "(content_hash=%s); the refusal itself is unaffected",
            workspace_id,
            content_hash,
        )



def _audit_race_refusal(
    *,
    workspace_id: uuid.UUID,
    content_hash: str,
    actor_principal_id: str | None,
    author_clearance: int,
) -> None:
    """Audit a duplicate refusal that came from the unique index rather than the pre-check.

    Separate from `_record_duplicate_refusal` only because the winning row's id and
    sensitivity are not in hand here — the INSERT failed, it did not return anything. One
    extra SELECT on the failure path is cheap, and guessing would put a wrong
    `aggregate_id` in an append-only trail.

    Silent when the row cannot be found: by the time this runs the winner could have been
    deleted, and inventing an event for a document that is not there would be recording
    something that did not happen.
    """
    try:
        with store.pg(str(workspace_id)) as conn:
            row = conn.execute(
                "SELECT id, sensitivity FROM document WHERE workspace_id = %s AND content_hash = %s",
                (workspace_id, content_hash),
            ).fetchone()
    except Exception:  # noqa: BLE001 — see `_record_duplicate_refusal`
        log.exception("failed to look up the winning row for a raced duplicate intake")
        return

    if row is None:
        return

    _record_duplicate_refusal(
        workspace_id=workspace_id,
        existing_id=row["id"],
        existing_sensitivity=row["sensitivity"],
        actor_principal_id=actor_principal_id,
        author_clearance=author_clearance,
        content_hash=content_hash,
    )


def list_quarantine(
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    clearance: int,
) -> list[QuarantineItem]:
    """Quarantined extractions the caller may see, newest first.

    **`clearance` is required, for the same reason it is required on `list_documents`.**
    A quarantine row carries `quote` — text the model lifted while reading a chunk — plus
    `source`/`relation`/`target`, which are graph facts, and `document_id`, which is the
    existence of a document. Returning those unfiltered would let an investor-clearance
    caller read material derived from a board-confidential document, which is `rules.md`
    §2 ("withheld sources are disclosed as a count only — never their content, title, or
    existence beyond that count") and P4's own exit criterion ("restricted titles, text,
    quotes, graph facts, and hints cannot leak").

    The filter is an **INNER JOIN**, so a row whose `document_id` is NULL is excluded
    rather than shown. That is the fail-closed reading: a row that cannot be attributed
    to a document cannot be shown to be safe, and every row this module writes has a
    document. RLS already scopes the workspace; this scopes the clearance *within* it.
    """
    ws_uuid = uuid.UUID(str(workspace_id))

    with store.pg(str(ws_uuid)) as conn:
        rows = conn.execute(
            """
            SELECT ef.id, ef.workspace_id, ef.document_id, ef.chunk_id,
                   ef.source, ef.relation, ef.target, ef.quote, ef.confidence,
                   ef.reason, ef.detail, ef.provider, ef.extractor_model, ef.created_at
            FROM extraction_failure ef
            JOIN document d
              ON d.id = ef.document_id
             AND d.workspace_id = ef.workspace_id
            WHERE ef.workspace_id = %s
              AND d.sensitivity <= %s
            ORDER BY ef.created_at DESC
            """,
            (ws_uuid, clearance),
        ).fetchall()

        return [_row_to_quarantine(r) for r in rows]

