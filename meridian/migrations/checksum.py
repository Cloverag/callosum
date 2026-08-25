"""Per-segment checksums for migration files.

A migration is hashed in **three** parts rather than one, because exactly one of
those parts may ever legitimately change:

    header      everything outside the two functions — the docstring, `revision`,
                `down_revision`, imports. Immutable. `down_revision` in particular
                is the chain itself; an edit there rewires history.
    upgrade     the `upgrade()` body. **Immutable, and this is the one that matters.**
    downgrade   the `downgrade()` body. Correctable, under the boundary in
                CONTRIBUTING.md — it may be fixed when it acts on objects the
                migration did not create.

The asymmetry is not a convenience. The harm a whole-file checksum exists to
prevent is *two populations that never converge*: a database migrated before an
edit never receives it, one built fresh afterwards has it from the start, and both
report the same `alembic_version`. That harm lives entirely on the **upgrade** path.
Alembic stores version numbers and never stores downgrade SQL, so no applied
database carries a copy of `downgrade()` to diverge from. A downgrade that is wrong
is wrong in the file, for everyone, at once — and can therefore be corrected for
everyone, at once.

A single whole-file hash cannot express that, which is why re-recording one silently
re-blesses the upgrade path too. Splitting is what lets the recorder refuse.

The split is **lossless**: every byte of the file lands in exactly one segment, and
`verify_covers_whole_file` proves it per file rather than asserting it.
"""

import ast
import hashlib
import pathlib

SEGMENTS = ("header", "upgrade", "downgrade")

#: Only this one may be re-recorded once set. See `scripts/record_migration_checksums.py`.
CORRECTABLE = frozenset({"downgrade"})


def _normalise(text: str) -> bytes:
    return text.replace("\r\n", "\n").encode()


def _spans(source: str) -> dict[str, tuple[int, int]]:
    """Character spans of `upgrade()` and `downgrade()` in the file text.

    Offsets are computed from line starts rather than taken from a byte position,
    because `ast` reports `col_offset` in bytes of the UTF-8 encoding of the line
    while we slice a `str`. Every migration in this repository is ASCII, so the two
    agree today; doing it by line start keeps that from being a latent trap.
    """
    starts = [0]
    for line in source.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))

    found: dict[str, tuple[int, int]] = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name in ("upgrade", "downgrade"):
            begin = starts[node.lineno - 1] + node.col_offset
            end = starts[node.end_lineno - 1] + node.end_col_offset
            found[node.name] = (begin, end)
    return found


def segments(path: pathlib.Path) -> dict[str, str]:
    """The three source segments of one migration file, keyed by name.

    A migration missing `upgrade()` or `downgrade()` yields an empty string for it,
    which still hashes to a stable value — absence is a fact worth pinning too.
    """
    source = path.read_text()
    spans = _spans(source)

    out = {name: source[a:b] for name, (a, b) in spans.items()}
    for name in ("upgrade", "downgrade"):
        out.setdefault(name, "")

    cut = sorted(spans.values())
    header, cursor = [], 0
    for a, b in cut:
        header.append(source[cursor:a])
        cursor = b
    header.append(source[cursor:])
    out["header"] = "".join(header)
    return out


def digests(path: pathlib.Path) -> dict[str, str]:
    return {name: hashlib.sha256(_normalise(text)).hexdigest() for name, text in segments(path).items()}


def verify_covers_whole_file(path: pathlib.Path) -> bool:
    """Every byte of the file is in exactly one segment.

    Proved rather than assumed: if a future `ast` change or an unusual layout made
    the spans overlap or leave a gap, the segments would still hash to *something*
    and the guard would silently stop covering part of the file.
    """
    parts = segments(path)
    return sum(len(parts[name]) for name in SEGMENTS) == len(path.read_text())


def whole_file_digest(path: pathlib.Path) -> str:
    """The pre-split hash. Kept so the format migration can be proved, not asserted."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
