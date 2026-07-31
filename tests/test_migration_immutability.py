"""An applied migration is history and may not be edited.

Fast suite — reads files, touches no database.

---------------------------------------------------------------------------
WHY THIS IS A TEST AND NOT A CONVENTION
---------------------------------------------------------------------------
Alembic records which revisions a database has run. It never re-runs one. So
editing an applied migration produces two populations that never converge:

  - a database migrated before the edit, which will never see the change;
  - a database built fresh after it, which has the change from the start.

Both report the same `alembic_version`. Nothing in the system notices, and the
divergence surfaces later as a constraint that exists on staging and not in
production, or the reverse.

This is precisely the invariant CP10 was accepted on. The P2 exit gate proved a
full-chain downgrade and return reproduced **628 schema facts identical to a fresh
build** (`scripts/schema_fingerprint.py`, `docs/reviews/2026-07-29-p2-acceptance.md`).
An edit to an applied migration breaks that guarantee silently — the fingerprint
comparison only runs when someone runs it, whereas this runs on every commit.

The rule is therefore mechanical: to change the schema, add a migration.

---------------------------------------------------------------------------
HOW TO ADD A MIGRATION
---------------------------------------------------------------------------
Write the file, then record its checksum:

    python scripts/record_migration_checksums.py

That is the moment the file becomes history. Doing it in the same commit is
deliberate: a manifest updated later is a manifest that can be updated to cover
an edit, which is the thing being prevented.

---------------------------------------------------------------------------
WHAT THIS DOES AND DOES NOT PROVE
---------------------------------------------------------------------------
It proves no *file* changed after being recorded. It cannot prove the migration is
correct, and it says nothing about a migration edited before it was ever recorded —
which is fine, because that one has not been applied anywhere yet.
"""

import hashlib
import json
import pathlib
import re

import pytest

_VERSIONS = pathlib.Path(__file__).resolve().parents[1] / "meridian" / "migrations" / "versions"
_MANIFEST = _VERSIONS.parent / "CHECKSUMS.json"

_REVISION = re.compile(r'^revision\s*=\s*"([^"]+)"', re.M)


def _migration_files() -> list[pathlib.Path]:
    return sorted(p for p in _VERSIONS.glob("*.py") if p.name != "__init__.py")


def _revision_of(path: pathlib.Path) -> str:
    match = _REVISION.search(path.read_text())
    assert match, f"{path.name} declares no `revision = \"...\"`"
    return match.group(1)


def _recorded() -> dict[str, str]:
    return json.loads(_MANIFEST.read_text())


def test_the_manifest_and_the_directory_agree():
    """Guard the guard.

    A manifest that had drifted out of sync with the directory would let the
    checksum test below pass while checking nothing, so the two are pinned to each
    other before any checksum is compared.
    """
    on_disk = {_revision_of(p) for p in _migration_files()}
    recorded = set(_recorded())

    unrecorded = sorted(on_disk - recorded)
    assert not unrecorded, (
        "migrations with no recorded checksum:\n  "
        + "\n  ".join(unrecorded)
        + "\n\nRun `python scripts/record_migration_checksums.py` to record them."
    )

    vanished = sorted(recorded - on_disk)
    assert not vanished, (
        "recorded migrations that are no longer on disk:\n  "
        + "\n  ".join(vanished)
        + "\n\nDeleting an applied migration has the same effect as editing one."
    )


@pytest.mark.parametrize("path", _migration_files(), ids=lambda p: p.stem)
def test_an_applied_migration_is_unchanged(path: pathlib.Path):
    """The rule.

    If this fails, do NOT update the manifest to match. Revert the file and put the
    change in a new migration — the databases that already ran this one will never
    see an edit to it.
    """
    revision = _revision_of(path)
    recorded = _recorded().get(revision)
    if recorded is None:
        pytest.skip("covered by test_the_manifest_and_the_directory_agree")

    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == recorded, (
        f"{path.name} ({revision}) has been edited after being recorded.\n"
        f"  recorded: {recorded}\n"
        f"  actual:   {actual}\n\n"
        "Alembic will not re-run this revision, so databases that already applied it "
        "will never receive this change. Revert the file and add a new migration."
    )


def test_the_checksum_comparison_can_actually_fail():
    """Without this, a broken hash helper would look like a clean tree."""
    first, second = b"CREATE TABLE a ()", b"CREATE TABLE b ()"
    assert hashlib.sha256(first).hexdigest() != hashlib.sha256(second).hexdigest()


def test_there_are_migrations_to_check():
    # A directory glob that silently found nothing would pass every assertion above.
    assert len(_migration_files()) >= 17, f"found only {len(_migration_files())} migrations"
