"""The frozen core's ON CONFLICT targets match the indexes that actually exist (#193).

`store.upsert_document` conflicted on `(content_hash)`. `schema/postgres.sql:57` once
declared exactly that constraint, but migration `0022_doc_content_hash_uq` replaced it
with a workspace-scoped composite — correctly, because the same bytes may legitimately
exist once per tenant. The call site was never updated, so **every** `callosum
ingest-doc` failed against a migrated database:

    InvalidColumnReference: there is no unique or exclusion constraint matching
    the ON CONFLICT specification

Nothing in the suite exercised that path, so 906 gated tests passed while the primary
ingest entry point could not insert a row. It survived nine migrations because a
long-lived development volume still held documents ingested before 0022 — the failure
only appears on a fresh volume, which is what every new deployment is.

Run deliberately: ``CALLOSUM_RUN_INTEGRATION=1 pytest -m integration``.
"""

import os
import re
import uuid
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
import pytest

if os.environ.get("CALLOSUM_RUN_INTEGRATION") != "1":
    pytest.skip(
        "set CALLOSUM_RUN_INTEGRATION=1 to run live-store integration tests",
        allow_module_level=True,
    )

from callosum import store  # noqa: E402
from callosum.config import settings  # noqa: E402

pytestmark = pytest.mark.integration

CORE = Path(__file__).resolve().parent.parent / "src" / "callosum"


def _hash(marker: str) -> str:
    return f"sha256-193-{marker}-{uuid.uuid4().hex}"


# ---------------------------------------------------------------------------
# The reported defect: ingest works at all, and still deduplicates.
# ---------------------------------------------------------------------------

def test_upsert_document_succeeds_and_stays_idempotent_within_a_workspace():
    """Steps 1 and 2. Not "it no longer throws" — the dedupe contract still holds.

    A fix that made the INSERT succeed by dropping the conflict clause would satisfy
    "does not raise" and silently double every document on re-ingest, which is the
    behaviour `upsert_document`'s docstring exists to promise. So this asserts the
    second call returns the *same id*, reports `is_new=False`, and leaves exactly one
    row.
    """
    content_hash = _hash("idem")

    with store.pg(store.DEFAULT_WORKSPACE_ID) as conn:
        first_id, first_is_new = store.upsert_document(
            conn, title="193 idempotence", doc_type="transcript",
            raw_text="body", content_hash=content_hash, sensitivity=1,
        )
        assert first_is_new is True, "a hash never seen before must insert"

        second_id, second_is_new = store.upsert_document(
            conn, title="193 idempotence (again)", doc_type="transcript",
            raw_text="body", content_hash=content_hash, sensitivity=1,
        )
        assert second_is_new is False, "re-ingesting the same bytes must not insert"
        assert second_id == first_id, "the caller must get the original document back"

        rows = conn.execute(
            "SELECT count(*) AS n FROM document WHERE content_hash = %s", (content_hash,)
        ).fetchone()["n"]
        assert rows == 1, f"expected exactly one row for this hash, found {rows}"


def test_the_same_bytes_may_exist_once_per_workspace():
    """Step 3, and the reason the conflict target had to change rather than be dropped.

    `uq_document_workspace_content_hash` is `(workspace_id, content_hash)`. Two tenants
    ingesting an identical document are two documents. If the old global constraint were
    restored, this would fail — which is precisely what 0022 set out to fix.

    `store.upsert_document` cannot be used for the second workspace: `document.
    workspace_id` carries a hardcoded column default of the Default Workspace and the
    helper never names the column, while the `tenant_isolation` policy is FORCE'd with a
    WITH CHECK on `workspace_id`. The core ingest helper is therefore
    Default-Workspace-only by construction. That limitation is real and is asserted
    below rather than left as folklore; the cross-tenant row is inserted explicitly.
    """
    content_hash = _hash("tenant")
    other_ws = str(uuid.uuid4())

    with psycopg.connect(settings().postgres_dsn, autocommit=True) as admin:
        admin.execute(
            "INSERT INTO workspace (id, external_id, name) VALUES (%s, %s, %s)",
            (other_ws, f"ws-193-{other_ws[:8]}", "193 second tenant"),
        )

    with store.pg(store.DEFAULT_WORKSPACE_ID) as conn:
        default_id, is_new = store.upsert_document(
            conn, title="193 shared bytes", doc_type="transcript",
            raw_text="identical", content_hash=content_hash, sensitivity=1,
        )
        assert is_new is True

    with store.pg(other_ws) as conn:
        conn.execute(
            """
            INSERT INTO document (workspace_id, title, doc_type, raw_text,
                                  content_hash, sensitivity, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, '{}')
            """,
            (other_ws, "193 shared bytes", "transcript", "identical", content_hash, 1),
        )
        other_id = conn.execute(
            "SELECT id FROM document WHERE content_hash = %s", (content_hash,)
        ).fetchone()["id"]

    assert str(other_id) != str(default_id), (
        "the same content_hash in two workspaces must be two distinct documents — "
        "if these are equal the uniqueness is global again and 0022 has been undone"
    )

    with psycopg.connect(settings().postgres_dsn, autocommit=True) as admin:
        n = admin.execute(
            "SELECT count(*) AS n FROM document WHERE content_hash = %s", (content_hash,)
        ).fetchone()[0]
        assert n == 2, f"expected one row per workspace, found {n}"


def test_core_ingest_helper_cannot_write_outside_the_default_workspace():
    """Pins the limitation the test above relies on, so it cannot rot silently.

    If `upsert_document` ever learns to name `workspace_id`, this test fails and the
    test above should be rewritten to use it. Until then, "the core ingest path is
    single-tenant" is a checked property rather than a comment.
    """
    other_ws = str(uuid.uuid4())
    with psycopg.connect(settings().postgres_dsn, autocommit=True) as admin:
        admin.execute(
            "INSERT INTO workspace (id, external_id, name) VALUES (%s, %s, %s)",
            (other_ws, f"ws-193b-{other_ws[:8]}", "193 third tenant"),
        )

    with pytest.raises(psycopg.Error) as exc:
        with store.pg(other_ws) as conn:
            store.upsert_document(
                conn, title="193 wrong tenant", doc_type="transcript",
                raw_text="body", content_hash=_hash("wrongws"), sensitivity=1,
            )

    # The REASON matters, not merely that something raised. Asserting bare
    # `psycopg.Error` made this test pass under the #193 mutant, where the call died
    # of InvalidColumnReference long before RLS ever looked at the row — a green test
    # for a broken reason. It must fail for the tenancy policy or not at all.
    assert "row-level security" in str(exc.value).lower(), (
        f"expected the tenant_isolation WITH CHECK to reject the default "
        f"workspace_id, got: {exc.value}"
    )


# ---------------------------------------------------------------------------
# The mechanical guard. This is the test that would have caught #193, and the
# one that catches the next instance of it.
# ---------------------------------------------------------------------------

_ON_CONFLICT = re.compile(
    r"INSERT\s+INTO\s+(?P<table>\w+)(?P<between>.*?)ON\s+CONFLICT\s*\((?P<cols>[^)]*)\)",
    re.IGNORECASE | re.DOTALL,
)


def _core_conflict_targets() -> list[tuple[str, str, frozenset[str]]]:
    found = []
    for path in sorted(CORE.glob("*.py")):
        text = path.read_text()
        for m in _ON_CONFLICT.finditer(text):
            if "INSERT INTO" in m.group("between").upper():
                continue  # a later INSERT matched an earlier ON CONFLICT
            cols = frozenset(
                c.strip().strip('"').lower()
                for c in m.group("cols").split(",")
                if c.strip() and not c.strip().startswith("--")
            )
            found.append((path.name, m.group("table").lower(), cols))
    return found


def test_every_core_on_conflict_target_matches_a_real_unique_index():
    """Mechanical, not a hand-picked list of the two sites known to be broken.

    #193 was two defects, not one: `store.upsert_document` and
    `conflicts.queue_pairs` had both been orphaned by tenancy migrations that
    prepended `workspace_id` to an index. A test naming those two would pass while a
    third drifted. This one enumerates every `ON CONFLICT` in the frozen core and
    checks each against the indexes the migrated database actually has.

    `ON CONFLICT (a, b)` is satisfied by a unique index on exactly `{a, b}`; Postgres
    matches on the column set, so order does not matter here.
    """
    targets = _core_conflict_targets()
    assert targets, "parsed no ON CONFLICT clauses — the regex has stopped matching"

    with psycopg.connect(settings().postgres_dsn, row_factory=dict_row) as conn:
        rows = conn.execute(
            """
            SELECT c.relname AS table_name, i.relname AS index_name,
                   array_agg(a.attname::text) AS cols
              FROM pg_index x
              JOIN pg_class c ON c.oid = x.indrelid
              JOIN pg_class i ON i.oid = x.indexrelid
              JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(x.indkey)
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE x.indisunique AND n.nspname = 'public'
             GROUP BY c.relname, i.relname
            """
        ).fetchall()

    by_table: dict[str, list[frozenset[str]]] = {}
    for r in rows:
        by_table.setdefault(r["table_name"], []).append(
            frozenset(c.lower() for c in r["cols"])
        )

    failures = []
    for filename, table, cols in targets:
        available = by_table.get(table, [])
        if cols not in available:
            failures.append(
                f"{filename}: INSERT INTO {table} ... ON CONFLICT {sorted(cols)} "
                f"matches no unique index; {table} has {[sorted(a) for a in available]}"
            )

    assert not failures, (
        "ON CONFLICT target(s) name no existing unique index. Postgres raises "
        "InvalidColumnReference at runtime, so these INSERTs cannot execute at all:\n  "
        + "\n  ".join(failures)
    )
