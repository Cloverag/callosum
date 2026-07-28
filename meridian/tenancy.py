"""Fail-closed workspace scoping for the product layer (Meridian P3, §5.1).

`store.pg()` is the frozen engine's connection helper, and it defaults a missing
workspace to the Default Workspace:

    (workspace_id or DEFAULT_WORKSPACE_ID,)     # src/callosum/store.py:50

Under the CLI that is a convenience — single-tenant callers land where they expect.
Behind an HTTP API it is a **fail-open default**: any bug that loses the workspace
reads the Default Workspace's data instead of raising, and it fails in the direction
that looks like success. A silent wrong answer is worse than an error.

`store.py` is one of the five frozen files (`CONTRIBUTING.md`), so the default cannot
be changed at source without an eval-justified exception. It does not need to be. The
product layer simply must never hand it a value that could be `None`, and this module
is where that is enforced rather than remembered.

**Use `require_workspace()` at the boundary** — where a workspace id arrives from a
session — and pass the validated result onward. Domain modules keep their existing
signatures; nothing here redesigns them.

This module deliberately does NOT check membership. Whether a principal may act in a
workspace is `identity.resolve_principal()`'s job, and duplicating that check here
would create the second source of truth that CP5b had to unwind.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

import psycopg

from callosum import store


class WorkspaceRequired(ValueError):
    """No usable workspace id was supplied.

    Raised instead of falling back to a default. The whole point of this module is
    that "no workspace" is an error, not a synonym for "the first one".
    """


def require_workspace(workspace_id: object) -> str:
    """Validates a workspace id and returns it canonicalised, or raises.

    Accepts a `UUID` or a string form of one. Rejects `None`, empty and whitespace-only
    strings, and anything that is not a UUID — each of which would otherwise reach
    `store.pg()` and silently become the Default Workspace.

    Returns the canonical lowercase hyphenated form, so two spellings of the same id
    cannot produce two different `app.workspace_id` values.
    """
    if workspace_id is None:
        raise WorkspaceRequired("workspace_id is required; it must not be None")

    if isinstance(workspace_id, UUID):
        return str(workspace_id)

    if not isinstance(workspace_id, str):
        raise WorkspaceRequired(
            f"workspace_id must be a UUID or its string form, got {type(workspace_id).__name__}"
        )

    candidate = workspace_id.strip()
    if not candidate:
        raise WorkspaceRequired("workspace_id is required; it must not be empty")

    try:
        # UUID() also accepts braced and urn forms; normalising through str() means a
        # caller cannot smuggle in a variant spelling that compares unequal downstream.
        return str(UUID(candidate))
    except ValueError as exc:
        raise WorkspaceRequired(f"workspace_id is not a valid UUID: {workspace_id!r}") from exc


@contextmanager
def scoped(workspace_id: object) -> Iterator[psycopg.Connection]:
    """`store.pg()`, but a missing workspace raises instead of defaulting.

    For product code that needs a connection directly. Domain modules already take a
    `workspace_id` and open their own connection; they are unchanged.
    """
    validated = require_workspace(workspace_id)
    with store.pg(validated) as conn:
        yield conn


def is_default_workspace(workspace_id: object) -> bool:
    """True when this id is the well-known Default Workspace.

    Not a security check — it is for tests and for surfaces that want to say "you are
    looking at demo data". The Default Workspace is a legitimate tenant; the defect
    this module prevents is *arriving* there by accident, not the workspace itself.
    """
    try:
        return require_workspace(workspace_id) == store.DEFAULT_WORKSPACE_ID
    except WorkspaceRequired:
        return False
