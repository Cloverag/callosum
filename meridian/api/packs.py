"""Board pack endpoints (Meridian P3, CP-C reads · CP-D writes — ADR-014).

**The highest-risk read path in the codebase**, and the one place where the ADR-013
rule earns its keep twice over.

`list_packs` and `get_pack` take BOTH `workspace_id` and `clearance`. Neither is a
request parameter. `workspace_id` comes from the session as everywhere else; so does
`clearance`, via `deps.current_principal`, which resolves it from the caller's active
membership on every request. A client that could name its own clearance could read
every restricted document in the workspace — which is precisely what
`tests/test_openapi_input_guard.py` fails the build over.

Two contract properties travel through this endpoint unchanged, and the frontend tests
assert both against live data:

  - items are clearance-filtered and then RENUMBERED from 1, so a withheld item
    leaves no gap and no position to infer;
  - `position` is therefore a per-caller ordinal, not an identity;
  - `withheld_items` says HOW MANY the caller may not read — and nothing else about
    them. That is ADR-018: a published pack claims to be the material for a meeting,
    so a director preparing from one has to know when it is not all of it. The count
    and the renumbering are not alternatives; the second closes a covert channel, the
    first replaces it with a bounded, deliberate disclosure.

Nothing here re-implements either. `_fetch_items_for_packs` does the filtering inside
the domain, and this endpoint returns what it produced.

---------------------------------------------------------------------------
CP-D — WRITES
---------------------------------------------------------------------------
**`clearance` is a required argument on four of the write functions, and it comes from
the session on every one of them.** `update_pack`, `publish_pack`, `supersede_pack` and
`reorder_pack_items` all return the pack, and returning a pack means returning its
items — so they filter on the way out exactly as the reads do. A caller who could name
its own clearance could publish a pack and read back every restricted item in it, which
is the read vulnerability wearing a write endpoint as a disguise.

**A write never widens a read.** A low-clearance member may edit a pack they can see,
and the response is still filtered to their clearance. There is a test asserting the
response to a *write* is filtered, not just the response to a read.

**`add_pack_item` and `remove_pack_item` carry no `expected_version`, but they do bump
the pack's.** They are guarded by the pack's *status* rather than by a counter — a
published pack refuses them outright, which is stronger than a version check because
there is no value that succeeds. What they still do is `version = version + 1` on the
pack, so a concurrent editor holding the old number is refused on their next versioned
call. Adding an item is a change to the pack even though it does not edit a pack column.

The practical consequence, which cost a test: after adding items you must re-read the
pack's `version` before publishing. The number the create call returned is stale.
"""

import uuid

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict

from meridian import packs as domain
from meridian.api.deps import CurrentPrincipal


class PackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meeting_id: uuid.UUID
    title: str


class PackPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int
    title: str | None = None


class PackItemAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: uuid.UUID
    agenda_item_id: uuid.UUID | None = None
    position: int | None = None
    note: str | None = None


class PackVersioned(BaseModel):
    """For `publish` — the whole body is the concurrency check."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int


class PackSupersede(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_title: str
    expected_version: int


class PackReorder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ordered_item_ids: list[uuid.UUID]


class PackSupersession(BaseModel):
    """Both halves — the caller needs each."""

    superseded: domain.BoardPack
    replacement: domain.BoardPack

router = APIRouter(prefix="/api/packs", tags=["packs"])


@router.get("")
def list_packs(
    meeting_id: uuid.UUID,
    principal: CurrentPrincipal,
    status: str | None = None,
) -> list[domain.BoardPack]:
    """Board packs for a meeting, `version_no DESC, created_at DESC`.

    `meeting_id` is required: a pack is a pre-read *for a meeting*, and a
    workspace-wide list of every pack is not a question any surface asks.
    """
    return domain.list_packs(
        meeting_id,
        workspace_id=principal.workspace_id,
        status=status,
        clearance=principal.clearance,
    )


@router.get("/{pack_id}")
def get_pack(pack_id: uuid.UUID, principal: CurrentPrincipal) -> domain.BoardPack:
    return domain.get_pack(
        pack_id,
        workspace_id=principal.workspace_id,
        clearance=principal.clearance,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_pack(payload: PackCreate, principal: CurrentPrincipal) -> domain.BoardPack:
    """Creates an empty `draft` pack against a meeting."""
    return domain.create_pack(
        str(payload.meeting_id), payload.title, workspace_id=principal.workspace_id
    )


@router.patch("/{pack_id}")
def update_pack(
    pack_id: uuid.UUID, payload: PackPatch, principal: CurrentPrincipal
) -> domain.BoardPack:
    """Renames a draft pack under optimistic concurrency.

    `clearance` is the caller's, so the returned pack is filtered to what they may see —
    editing a pack does not reveal an item they could not read a moment ago.
    """
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("expected_version", None)
    return domain.update_pack(
        str(pack_id),
        expected_version=payload.expected_version,
        workspace_id=principal.workspace_id,
        clearance=principal.clearance,
        **changes,
    )


@router.post("/{pack_id}/items", status_code=status.HTTP_201_CREATED)
def add_pack_item(
    pack_id: uuid.UUID, payload: PackItemAdd, principal: CurrentPrincipal
) -> domain.BoardPackItem:
    """Adds a document to a draft pack.

    **Pack membership does not widen access.** The document is referenced, not copied,
    and its sensitivity travels with it — adding a restricted document to a pack does
    not make it readable by members who could not read it directly. That is a CP3 exit
    criterion and the negative test lives with the reads.

    No `expected_version` on the call, but it **bumps the pack's** — see the module
    docstring. Re-read the pack before publishing.
    """
    return domain.add_pack_item(
        str(pack_id),
        str(payload.document_id),
        workspace_id=principal.workspace_id,
        agenda_item_id=str(payload.agenda_item_id) if payload.agenda_item_id else None,
        position=payload.position,
        note=payload.note,
    )


@router.delete("/items/{pack_item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_pack_item(pack_item_id: uuid.UUID, principal: CurrentPrincipal) -> None:
    """Removes an item from a draft pack and closes the gap in `position`.

    Addressed by the item's own id rather than as `/{pack_id}/items/{item_id}`. The
    domain identifies an item by itself, so a pack id in the path would be a parameter
    nothing verifies — and a caller could reasonably assume it was checked.
    """
    domain.remove_pack_item(str(pack_item_id), workspace_id=principal.workspace_id)


@router.post("/{pack_id}/publish")
def publish_pack(
    pack_id: uuid.UUID, payload: PackVersioned, principal: CurrentPrincipal
) -> domain.BoardPack:
    """Freezes a pack. After this it is amended by supersession, never by editing.

    That is what makes a published pack citable: the version a director read is still
    the version that exists.
    """
    return domain.publish_pack(
        str(pack_id),
        expected_version=payload.expected_version,
        workspace_id=principal.workspace_id,
        clearance=principal.clearance,
    )


@router.post("/{pack_id}/supersede", status_code=status.HTTP_201_CREATED)
def supersede_pack(
    pack_id: uuid.UUID, payload: PackSupersede, principal: CurrentPrincipal
) -> PackSupersession:
    """Issues a new version of a published pack, copying its items forward.

    The domain returns `(new, old)` — named here rather than passed through, because
    two values of the same type in a tuple swap silently if you get it wrong.
    """
    new, old = domain.supersede_pack(
        str(pack_id),
        payload.new_title,
        expected_version=payload.expected_version,
        workspace_id=principal.workspace_id,
        clearance=principal.clearance,
    )
    return PackSupersession(superseded=old, replacement=new)


@router.post("/{pack_id}/reorder")
def reorder_pack_items(
    pack_id: uuid.UUID, payload: PackReorder, principal: CurrentPrincipal
) -> domain.BoardPack:
    """Reorders a draft pack's items.

    **The caller must send every item id, and a low-clearance caller cannot see them
    all** — so this is a legitimately privileged operation, not a bug to route around.
    The domain refuses a list that is not exactly the pack's items, which means a
    reorder attempted from a filtered view fails rather than silently dropping the
    items the caller could not see.
    """
    return domain.reorder_pack_items(
        str(pack_id),
        [str(i) for i in payload.ordered_item_ids],
        workspace_id=principal.workspace_id,
        clearance=principal.clearance,
    )
