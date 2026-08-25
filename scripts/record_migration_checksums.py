#!/usr/bin/env python3
"""Record the checksum of every migration, freezing it as history.

Run this in the same commit that adds a migration:

    python scripts/record_migration_checksums.py

After that, `tests/test_migration_immutability.py` fails if the file changes. See
that module's docstring for why an applied migration cannot be edited.

Each migration is recorded as **three** hashes, not one:

    {"header": ..., "upgrade": ..., "downgrade": ...}

`header` and `upgrade` are **permanently unoverwritable** — this script exits
non-zero rather than replace either, and there is no flag to make it. `downgrade`
may be re-recorded, because a downgrade correction is the one edit that cannot split
the estate: Alembic stores version numbers and never stores downgrade SQL, so no
applied database carries a copy of it to diverge from.

That asymmetry is the whole point of splitting. A single whole-file hash could only
be re-recorded wholesale, which silently re-blessed the upgrade path along with the
downgrade — a boundary that lived in prose and that the tool could not enforce. The
refusal below is what makes the boundary in CONTRIBUTING.md a mechanism instead of a
sentence a future reader has to have read.
"""

import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from meridian.migrations import checksum  # noqa: E402

VERSIONS = pathlib.Path(__file__).resolve().parents[1] / "meridian" / "migrations" / "versions"
MANIFEST = VERSIONS.parent / "CHECKSUMS.json"

_REVISION = re.compile(r'^revision\s*=\s*"([^"]+)"', re.M)


def main() -> int:
    recorded: dict[str, dict[str, str]] = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}

    added, corrected, converted, conflicts, uncovered = [], [], [], [], []
    for path in sorted(VERSIONS.glob("*.py")):
        if path.name == "__init__.py":
            continue
        match = _REVISION.search(path.read_text())
        if not match:
            print(f"skipped (no revision declared): {path.name}", file=sys.stderr)
            continue
        revision = match.group(1)

        # Refuse to record anything the split does not fully account for. A gap here
        # would leave part of the file unhashed while every assertion still passed.
        if not checksum.verify_covers_whole_file(path):
            uncovered.append((revision, path.name))
            continue

        fresh = checksum.digests(path)
        previous = recorded.get(revision)

        if previous is None:
            recorded[revision] = fresh
            added.append(revision)
            continue

        # One-time upgrade from the pre-split format, `{revision: "<whole-file sha>"}`.
        # Converted only if the whole-file hash still matches what was recorded — so
        # the split provably records the same file, unmodified, rather than blessing
        # whatever happens to be on disk at the moment of the format change.
        if isinstance(previous, str):
            if checksum.whole_file_digest(path) != previous:
                conflicts.append((revision, "whole-file (pre-split)", path.name))
                continue
            recorded[revision] = fresh
            converted.append(revision)
            continue

        for segment in checksum.SEGMENTS:
            if previous.get(segment) == fresh[segment]:
                continue
            if segment in checksum.CORRECTABLE:
                previous[segment] = fresh[segment]
                corrected.append((revision, segment))
            else:
                conflicts.append((revision, segment, path.name))

    if uncovered:
        print("REFUSING TO RECORD. The checksum split does not cover these whole files:\n")
        for revision, name in uncovered:
            print(f"  {revision}  ({name})")
        print("\nEvery byte must land in exactly one of header/upgrade/downgrade.")
        return 1

    if conflicts:
        print("REFUSING TO OVERWRITE. These migrations changed outside `downgrade()`:\n")
        for revision, segment, name in conflicts:
            print(f"  {revision}  [{segment}]  ({name})")
        print(
            "\nAlembic will not re-run a recorded revision, so an edit to `upgrade()` or\n"
            "to the header reaches new databases only — the estate splits in two and\n"
            "both halves report the same `alembic_version`. Revert the file and add a\n"
            "new migration instead.\n\n"
            "`downgrade()` is the sole exception and is re-recorded automatically, under\n"
            "the boundary in CONTRIBUTING.md: it may be corrected when it acts on objects\n"
            "the migration did not create. There is deliberately no flag to widen that.\n\n"
            "If a recorded migration was genuinely never released — it exists only on an\n"
            "unmerged branch and no surviving database has run it — remove its entry from\n"
            "CHECKSUMS.json by hand and say why in the commit message. Nothing here can\n"
            "check that for you, which is the point: it has to be a decision someone\n"
            "writes down and a reviewer sees in the manifest diff."
        )
        return 1

    MANIFEST.write_text(json.dumps(recorded, indent=2, sort_keys=True) + "\n")
    if added:
        print(f"recorded {len(added)} new migration(s):")
        for revision in added:
            print(f"  {revision}")
    if converted:
        print(f"converted {len(converted)} migration(s) from the pre-split format:")
        for revision in converted:
            print(f"  {revision}")
        print("  (each whole-file hash verified against the old manifest before splitting)")
    if corrected:
        print(f"re-recorded {len(corrected)} downgrade correction(s):")
        for revision, segment in corrected:
            print(f"  {revision}  [{segment}]")
    if not added and not corrected and not converted:
        print("nothing new to record")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
