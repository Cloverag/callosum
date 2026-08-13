"""Document API endpoints (Meridian P4).

Exposes HTTP routes for document intake, clearance-gated document listing, single
document retrieval, and extraction quarantine inspection.
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, Field

from meridian import documents as domain
from meridian.api.deps import CurrentPrincipal

router = APIRouter(prefix="/api/documents", tags=["documents"])


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    doc_type: str
    source_uri: str | None = None
    raw_text: str
    content_hash: str
    sensitivity: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


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
    sensitivity: int = 0
    source_uri: str | None = None
    extract_proposals: bool = False


@router.get("", response_model=list[DocumentResponse])
def list_documents(principal: CurrentPrincipal) -> list[domain.Document]:
    """List documents readable by the authenticated principal in their active workspace."""
    return domain.list_documents(
        workspace_id=principal.workspace_id,
        clearance=principal.clearance,
    )


@router.get("/quarantine", response_model=list[QuarantineResponse])
def list_quarantine(principal: CurrentPrincipal) -> list[domain.QuarantineItem]:
    """List extraction failures and quarantined relationships for the workspace."""
    return domain.list_quarantine(workspace_id=principal.workspace_id)


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
        workspace_id=principal.workspace_id,
        author_principal_id=principal.id,
        source_uri=req.source_uri,
        extract_proposals=req.extract_proposals,
    )
