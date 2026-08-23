"""Document API endpoints (Meridian P4).

Exposes HTTP routes for document intake, clearance-gated document listing, single
document retrieval, and extraction quarantine inspection.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict

from meridian import documents as domain
from meridian.api.deps import CurrentPrincipal

router = APIRouter(prefix="/api/documents", tags=["documents"])


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    doc_type: str
    source_uri: str | None = None
    sensitivity: int
    authored_at: datetime | None = None
    ingested_at: datetime
    #: 1-based position in the supersession chain (`0024_document_version`).
    revision: int = 1
    #: The revision that replaced this one, or null if this is the current revision.
    superseded_by_id: str | None = None


class QuarantineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    document_id: uuid.UUID | None = None
    chunk_id: uuid.UUID | None = None
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


class IntakeDocumentRequest(BaseModel):
    title: str
    doc_type: str
    raw_text: str
    #: Required, with no default (#143). It used to default to `0` — *public*, the
    #: widest visibility the system has — so a caller who simply omitted the field
    #: published the document to everyone. That is fail-open by default on the one
    #: surface whose purpose is putting confidential material into the system.
    #:
    #: Deriving a default from the caller's clearance would be safer than `0` and is a
    #: reasonable future behaviour, but it is still a guess about a security level.
    #: Automatic classification is its own product decision; until it is taken, intake
    #: requires a deliberate one.
    sensitivity: int
    source_uri: str | None = None


class SupersedeDocumentRequest(IntakeDocumentRequest):
    """The corrected revision's content.

    Identical to intake, because a supersession *is* an intake plus a link — the new
    revision is chunked, embedded, bridged and extracted exactly like any other document.
    Subclassing rather than restating keeps `sensitivity` required with no default, which
    is the decision recorded on the parent (#143); a copied model is a copy that can
    quietly reacquire a default.
    """


class DocumentChainResponse(BaseModel):
    """One document's revision history, as this caller is permitted to see it."""

    #: Readable revisions, oldest first.
    revisions: list[DocumentResponse]
    #: How many revisions in this chain the caller may not see. The whole disclosure —
    #: never a title, an id, or a date (`rules.md` §2, P4's exit criterion).
    withheld: int
    #: The current revision's id, or null when the current revision is withheld.
    #:
    #: Null rather than the newest *readable* revision. That fallback would mark a
    #: superseded document as current, which is worse than saying nothing: the reader
    #: would act on a document the board has already corrected, with no signal.
    current_id: str | None


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    principal: CurrentPrincipal, doc_type: str | None = None
) -> list[domain.Document]:
    """List documents readable by the authenticated principal in their active workspace."""
    return domain.list_documents(
        workspace_id=principal.workspace_id,
        clearance=principal.clearance,
        doc_type=doc_type,
    )


@router.get("/quarantine", response_model=list[QuarantineResponse])
def list_quarantine(principal: CurrentPrincipal) -> list[domain.QuarantineItem]:
    """Quarantined extractions readable by the caller, at their own clearance.

    A quarantine row exposes a quote, a proposed graph fact and a document id, so it is
    a clearance-filtered surface exactly like the document list — not an internal
    diagnostics feed.
    """
    return domain.list_quarantine(
        workspace_id=principal.workspace_id,
        clearance=principal.clearance,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: uuid.UUID, principal: CurrentPrincipal) -> domain.Document:
    """Retrieve a single document by ID, subject to clearance verification."""
    return domain.get_document(
        document_id,
        workspace_id=principal.workspace_id,
        clearance=principal.clearance,
    )


@router.post("/intake", status_code=status.HTTP_201_CREATED, response_model=DocumentResponse)
def intake_document(
    req: IntakeDocumentRequest, principal: CurrentPrincipal
) -> domain.Document:
    """Intake a source document into tenant memory."""
    return domain.intake_document(
        title=req.title,
        doc_type=req.doc_type,
        raw_text=req.raw_text,
        sensitivity=req.sensitivity,
        # The ceiling is enforced in the domain, so the value here is only ever a
        # request — never a permission. A client that offers the levels a caller may
        # pick is a convenience; the refusal does not depend on it having done so.
        author_clearance=principal.clearance,
        workspace_id=principal.workspace_id,
        author_principal_id=principal.id,
        source_uri=req.source_uri,
    )


@router.get("/{document_id}/versions", response_model=DocumentChainResponse)
def get_version_chain(document_id: uuid.UUID, principal: CurrentPrincipal) -> domain.DocumentChain:
    """Every revision of one document, filtered to what this caller may read.

    404 when the named document is above the caller's clearance — a chain read must not
    be a way around `get_document`'s gate.

    Registered *after* `/{document_id}`, unlike `/quarantine`, which had to come first.
    The extra path segment makes this unambiguous: `/quarantine` could be read as a
    document id, `/{id}/versions` cannot.
    """
    return domain.version_chain(
        str(document_id),
        workspace_id=principal.workspace_id,
        clearance=principal.clearance,
    )


@router.post(
    "/{document_id}/supersede",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentResponse,
)
def supersede_document(
    document_id: uuid.UUID, req: SupersedeDocumentRequest, principal: CurrentPrincipal
) -> domain.Document:
    """File a corrected revision of an existing document.

    Returns the **new** revision, matching what `POST /intake` returns and what a 201
    means: this is the resource that was created. The predecessor is unchanged apart from
    its forward link, and the caller can re-read it or the chain if they want it.

    There is no `expected_version`. `document` carries no version counter, and that is
    deliberate: a document's mutable state is one nullable pointer, so "already
    superseded" *is* the concurrency conflict and it answers 409 like any other.
    """
    new_document, _old_document = domain.supersede_document(
        str(document_id),
        title=req.title,
        doc_type=req.doc_type,
        raw_text=req.raw_text,
        sensitivity=req.sensitivity,
        # As on intake: the ceiling is enforced in the domain, so this is a request and
        # never a permission. The downgrade floor is enforced there too, against the
        # predecessor's own level rather than anything the client sent.
        author_clearance=principal.clearance,
        workspace_id=principal.workspace_id,
        author_principal_id=principal.id,
        source_uri=req.source_uri,
    )
    return new_document
