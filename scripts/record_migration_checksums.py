#!/usr/bin/env python3
"""Record the checksum of every migration, freezing it as history.

Run this in the same commit that adds a migration:

    python scripts/record_migration_checksums.py

After that, `tests/test_migration_immutability.py` fails if the file changes. See
that module's docstring for why an applied migration cannot be edited.

Deliberately additive-only. It refuses to overwrite a checksum that is already
recorded, because the failure this whole mechanism exists to catch is exactly
"someone edited a migration and then regenerated the manifest to match".
"""

import hashlib
import json
import pathlib
import re
import sys

VERSIONS = pathlib.Path(__file__).resolve().parents[1] / "meridian" / "migrations" / "versions"
MANIFEST = VERSIONS.parent / "CHECKSUMS.json"

_REVISION = re.compile(r'^revision\s*=\s*"([^"]+)"', re.M)


def main() -> int:
    recorded: dict[str, str] = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}

    added, conflicts = [], []
    for path in sorted(VERSIONS.glob("*.py")):
        if path.name == "__init__.py":
            continue
        match = _REVISION.search(path.read_text())
        if not match:
            print(f"skipped (no revision declared): {path.name}", file=sys.stderr)
            continue

        revision = match.group(1)
        digest = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()

        if revision not in recorded:
            recorded[revision] = digest
            added.append(revision)
        elif recorded[revision] != digest:
            conflicts.append((revision, path.name))

    if conflicts:
        print("REFUSING TO OVERWRITE. These migrations differ from their recorded checksum:\n")
        for revision, name in conflicts:
            print(f"  {revision}  ({name})")
        print(
            "\nA recorded migration has already been applied somewhere, and Alembic will\n"
            "not re-run it — so an edit reaches new databases only. Revert the file and\n"
            "add a new migration instead. If a recorded migration was genuinely never\n"
            "released, remove its line from CHECKSUMS.json by hand and say why in the\n"
            "commit message."
        )
        return 1

    MANIFEST.write_text(json.dumps(recorded, indent=2, sort_keys=True) + "\n")
    if added:
        print(f"recorded {len(added)} new migration(s):")
        for revision in added:
            print(f"  {revision}")
    else:
        print("nothing new to record")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
