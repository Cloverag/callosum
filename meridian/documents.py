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

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from callosum import store
from callosum.store import DEFAULT_WORKSPACE_ID

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


@dataclass(frozen=True)
class Document:
    id: str
    title: str
    doc_type: str
    source_uri: str | None
    sensitivity: int
    authored_at: datetime | None
    ingested_at: datetime


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
