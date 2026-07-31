"""Document read endpoints (Meridian P3, CP-E — ADR-014).

1:1 with `meridian/documents.py`, minus `workspace_id` **and** `clearance`, both of
which come from `deps.current_principal` (ADR-013).

This closes the last mock behind a live surface. The packs page fetched real packs and
mock documents, so every `board_pack_item.document_id` resolved to nothing and every
item rendered as a broken reference — a live surface making a false statement about
real data, which is the failure mode the data-honesty work has been chasing since the
dashboard's repository-metadata figures.

**Read-only, and that is the boundary not an omission.** Documents enter through
`callosum.ingest`, on the frozen side. An upload endpoint is P4 intake, and adding one
here would put the product in the ingestion business without the extraction, quote
verification or quarantine that makes an ingested document trustworthy.
"""

import uuid

from fastapi import APIRouter

from meridian import documents as domain
from meridian.api.deps import CurrentPrincipal

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("")
def list_documents(
    principal: CurrentPrincipal, doc_type: str | None = None
) -> list[domain.Document]:
    """Documents the caller may read, newest ingestion first.

    `doc_type` is an ordinary filter over data the caller can already see. `clearance`
    is not a filter and is not accepted — it decides *what may be seen at all*, so it
    comes from the caller's active membership and `tests/test_openapi_input_guard.py`
    fails the build if it ever appears in the schema.
    """
    return domain.list_documents(
        workspace_id=principal.workspace_id,
        clearance=principal.clearance,
        doc_type=doc_type,
    )


@router.get("/{document_id}")
def get_document(document_id: uuid.UUID, principal: CurrentPrincipal) -> domain.Document:
    """One document.

    A document above the caller's clearance raises `DocumentNotFound` and arrives as a
    404 — the same answer as one that does not exist. Distinguishing them would confirm
    that a restricted document exists to someone who may not read it.
    """
    return domain.get_document(
        str(document_id), workspace_id=principal.workspace_id, clearance=principal.clearance
    )
