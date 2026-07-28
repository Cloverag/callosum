#!/usr/bin/env python
"""Deterministic schema fingerprint, read from the Postgres catalogue.

Written for the P2 exit gate (CP10) to answer a question a migration run cannot:
a downgrade/upgrade cycle can *succeed* and still leave drift — an index not
recreated, a constraint quietly dropped, a grant lost. "It ran" is not the bar.

Usage:

    # 1. round trip on the current volume
    alembic downgrade base && alembic upgrade head
    PYTHONPATH=. .venv/bin/python scripts/schema_fingerprint.py /tmp/roundtrip.txt

    # 2. rebuild from empty
    docker compose down -v && docker compose up -d && sleep 15
    alembic upgrade head
    PYTHONPATH=. .venv/bin/python scripts/schema_fingerprint.py /tmp/fresh.txt

    # 3. the actual test
    diff /tmp/roundtrip.txt /tmp/fresh.txt && echo "recovery path is lossless"

Anything the catalogue does not expose is not compared, so this proves structural
equivalence, not behavioural equivalence — the gated suite and the mechanism gate
cover that. `alembic_version` is excluded because it records where the chain stopped,
which legitimately differs between the two runs.
"""

import sys

import psycopg

from callosum.config import settings

QUERIES: list[tuple[str, str]] = [
    (
        "COLUMN",
        """
        SELECT table_name || '.' || column_name || ' ' || data_type
               || ' null=' || is_nullable
               || ' default=' || coalesce(column_default, '-')
          FROM information_schema.columns
         WHERE table_schema = 'public' AND table_name <> 'alembic_version'
         ORDER BY 1
        """,
    ),
    (
        "CONSTRAINT",
        """
        SELECT rel.relname || ' :: ' || con.conname || ' :: ' || pg_get_constraintdef(con.oid)
          FROM pg_constraint con
          JOIN pg_class rel ON rel.oid = con.conrelid
         WHERE rel.relnamespace = 'public'::regnamespace
         ORDER BY 1
        """,
    ),
    (
        "INDEX",
        """
        SELECT tablename || ' :: ' || indexname || ' :: ' || indexdef
          FROM pg_indexes
         WHERE schemaname = 'public' AND tablename <> 'alembic_version'
         ORDER BY 1
        """,
    ),
    (
        "RLS",
        """
        SELECT relname
               || ' rowsecurity=' || relrowsecurity::text
               || ' forced=' || relforcerowsecurity::text
          FROM pg_class
         WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'
         ORDER BY 1
        """,
    ),
    (
        # Policies are the load-bearing half of tenancy. A downgrade that drops a
        # policy and an upgrade that forgets to recreate it would leave a table with
        # RLS enabled and nothing to enforce — which reads as secure and is not.
        "POLICY",
        """
        SELECT tablename || ' :: ' || policyname || ' :: '
               || coalesce(qual, '-') || ' :: ' || coalesce(with_check, '-')
          FROM pg_policies
         WHERE schemaname = 'public'
         ORDER BY 1
        """,
    ),
    (
        # `0016_audit_event` relies on a REVOKE to make the trail append-only, and
        # `0004_app_role` grants writes on every new table by default. A lost revoke
        # is invisible in the table definition and fatal to the guarantee.
        "GRANT",
        """
        SELECT table_name || ' :: ' || grantee || ' :: ' || privilege_type
          FROM information_schema.role_table_grants
         WHERE table_schema = 'public' AND grantee = 'callosum_app'
         ORDER BY 1
        """,
    ),
]


def fingerprint() -> list[str]:
    facts: list[str] = []
    with psycopg.connect(settings().postgres_dsn) as conn:
        for label, sql in QUERIES:
            for (row,) in conn.execute(sql).fetchall():
                facts.append(f"{label}\t{row}")
    return facts


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    facts = fingerprint()
    with open(sys.argv[1], "w", encoding="utf-8") as fh:
        fh.write("\n".join(facts) + "\n")
    print(f"{len(facts)} schema facts -> {sys.argv[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
