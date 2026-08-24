"""ADR-018: every clearance-filtered collection declares which disclosure rule it follows.

Ungated and database-free, unlike `tests/test_p4_leak_sweep.py`, which this complements.
The sweep there calls live endpoints and proves that restricted material does not appear
in a response body. This file proves something the sweep structurally cannot: that a
collection which *withholds* material has **decided** whether to say so.

The two failures are different. A leak is material escaping. This is the opposite —
material disappearing with no acknowledgement, on a surface where a reader will act on
what is left as though it were everything. `version_chain` exists because a superseded
document read as current is a real harm; a board pack silently missing three items is the
same harm, one object over.

---------------------------------------------------------------------------
WHY THIS IS STATIC AND WHY THAT IS THE POINT
---------------------------------------------------------------------------
ADR-018's rule is a property of a function's *contract*, not of any one response, so it
can be checked without a database and therefore in the fast tier — where a new collection
is cheapest to catch, before anyone has written a client against it.

The enumeration is mechanical: any public domain function taking `clearance` is a
clearance-filtered read, and a new one joins this test by existing. That is deliberate.
A hand-maintained list of surfaces proves whatever was on the list the day it was written,
which is exactly how `packs` and `version_chain` came to disagree without anyone noticing.

---------------------------------------------------------------------------
THE CLASSIFIER, AND THE PROPERTY IT LEANS ON
---------------------------------------------------------------------------
A **collection container** is a dataclass with a `list[...]` field. It is the only place a
count can live, which gives ADR-018 a structural consequence worth stating:

    a function returning a bare `list[X]` CANNOT disclose a count, so it must be on
    the erase list — the type system makes the choice visible.

To move a surface onto the count side, someone has to introduce a container dataclass.
That is a deliberate act which shows up in review, rather than a filter quietly added to a
WHERE clause.
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import pkgutil
import typing

import pytest

import meridian

#: Surfaces ADR-018 puts on the ERASE side. Mirrors the table in that record — this is a
#: transcription of a decision, not a place to silence a failure. A new entry here means
#: amending ADR-018 first and saying which completeness claim the surface does not make.
#:
#: `meridian.api` is excluded from the walk entirely: routers take a principal and
#: delegate, so the domain function is where the discipline is decided and where a defect
#: would be introduced.
ERASES = frozenset(
    {
        # A browse view over everything filed. Claims to show what you may read, never
        # that it shows everything the board holds.
        "meridian.documents.list_documents",
        # A browse view over refused extractions. Nobody prepares for a meeting from it.
        "meridian.documents.list_quarantine",
    }
)


def _domain_modules():
    for info in pkgutil.iter_modules(meridian.__path__):
        if info.ispkg:  # `meridian.api` — routers delegate, they do not decide
            continue
        yield importlib.import_module(f"meridian.{info.name}")


def _clearance_readers() -> list[tuple[str, typing.Any]]:
    """Every public domain function that filters by clearance, as (qualname, return type)."""
    found: list[tuple[str, typing.Any]] = []
    for mod in _domain_modules():
        for name, fn in inspect.getmembers(mod, inspect.isfunction):
            if name.startswith("_") or fn.__module__ != mod.__name__:
                continue
            try:
                sig = inspect.signature(fn)
            except (ValueError, TypeError):  # pragma: no cover - C-implemented callables
                continue
            if "clearance" not in sig.parameters:
                continue
            hints = typing.get_type_hints(fn)
            found.append((f"{mod.__name__}.{name}", hints.get("return")))
    return sorted(found)


def _dataclasses_in(annotation) -> list[type]:
    """Every dataclass reachable from an annotation, unwrapping list/tuple/optional."""
    if annotation is None:
        return []
    if dataclasses.is_dataclass(annotation):
        return [annotation]
    out: list[type] = []
    for arg in typing.get_args(annotation):
        out.extend(_dataclasses_in(arg))
    return out


def _is_container(cls: type) -> bool:
    """A dataclass holding a `list[...]` field — the only shape a count can live on."""
    return any(
        typing.get_origin(f.type) is list or str(f.type).startswith("list")
        for f in dataclasses.fields(cls)
    )


def _has_count(cls: type) -> bool:
    return any("withheld" in f.name for f in dataclasses.fields(cls))


READERS = _clearance_readers()


def test_the_walk_actually_finds_the_known_surfaces():
    """A sweep that enumerates nothing passes vacuously.

    Pinned against the surfaces that exist today so a refactor which moves the domain out
    from under `meridian/` — or renames the `clearance` parameter — fails loudly here
    instead of turning every assertion below into a no-op.
    """
    names = {name for name, _ in READERS}
    assert "meridian.documents.version_chain" in names
    assert "meridian.documents.list_documents" in names
    assert "meridian.packs.get_pack" in names
    assert len(names) >= 8, f"walk found only {len(names)} clearance readers: {sorted(names)}"


@pytest.mark.parametrize("qualname,annotation", READERS, ids=[n for n, _ in READERS])
def test_every_clearance_filtered_collection_declares_its_discipline(qualname, annotation):
    """Count or erase — never neither (ADR-018).

    A container that filters by clearance and offers no count is the failure this exists
    to catch: material vanishes, the reader is not told, and nothing in the type says
    whether that was decided or overlooked.
    """
    if qualname in ERASES:
        return

    containers = [c for c in _dataclasses_in(annotation) if _is_container(c)]
    if not containers:
        # Returns a single object, or a bare list of non-containers. A bare list cannot
        # carry a count, so anything that filters and returns one must be on ERASES.
        if typing.get_origin(annotation) is list:
            pytest.fail(
                f"{qualname} filters by clearance and returns a bare list, which cannot "
                f"carry a withheld count. Put it on ERASES (and in ADR-018's table), or "
                f"return a container dataclass that has one."
            )
        return

    for cls in containers:
        assert _has_count(cls), (
            f"{qualname} returns {cls.__name__}, which holds a list filtered by clearance "
            f"but has no `withheld` field. Under ADR-018 a reader of this collection would "
            f"mistake a partial view for a complete one. Either add the count, or add "
            f"{qualname} to ERASES and record in ADR-018 which completeness claim it does "
            f"not make."
        )


def test_the_erase_list_has_no_stale_entries():
    """An ERASES entry naming a function that no longer exists silences a real surface.

    A renamed function drops off the walk and its old name sits here excusing nothing —
    the allowlist would keep passing while the surface it described went unchecked.
    """
    names = {name for name, _ in READERS}
    assert ERASES <= names, f"ERASES names functions that do not exist: {sorted(ERASES - names)}"
