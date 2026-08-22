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
