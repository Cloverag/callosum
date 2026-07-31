"""Link the demo Keycloak users to the principals `callosum init` created.

Deployment tooling, not a product feature. `callosum init` seeds `principal` and
`membership`; nothing seeds `principal_identity`, which is the table the OIDC callback
looks a subject up in. Without it, login authenticates successfully against Keycloak and
is then refused by Meridian — correctly, per ADR-011, because "the provider
authenticated them; this system has no record of them, and login does not create one."

    .venv/bin/python scripts/seed_demo_identities.py

Idempotent: re-running it is a no-op.

---------------------------------------------------------------------------
WHY THE SUBJECTS ARE HARD-CODED
---------------------------------------------------------------------------
A Keycloak user's `sub` claim is its internal id. `keycloak/realm-dev.json` pins that id
for each demo user, so the value below is not a guess — it is the same string the
provider will assert, and the pairing is reproducible on any machine that imports the
same realm.

`stranger` is deliberately absent. It exists to demonstrate that an authenticated but
unprovisioned identity is refused, and seeding it would delete the demonstration.
"""

from __future__ import annotations

import os
import sys

import psycopg

# (Keycloak user id — the `sub` claim, principal email as seeded by `callosum init`)
DEMO_IDENTITIES = [
    ("00000000-0000-4000-a000-000000000001", "raj@callosum.inc"),
    ("00000000-0000-4000-a000-000000000002", "priya@callosum.inc"),
    ("00000000-0000-4000-a000-000000000003", "marcus@sequoia.com"),
]

ISSUER = os.environ.get(
    "MERIDIAN_OIDC_ISSUER", "http://localhost:8080/realms/meridian"
)


def main() -> int:
    from callosum.config import settings

    # The admin DSN, deliberately. `principal_identity` write grants are revoked from
    # the runtime role — provisioning an identity is an administrative act, not
    # something the application should be able to do to itself.
    dsn = settings().postgres_dsn

    linked, skipped, missing = 0, 0, []

    with psycopg.connect(dsn) as conn:
        for subject, email in DEMO_IDENTITIES:
            row = conn.execute(
                "SELECT id, name FROM principal WHERE email = %s", (email,)
            ).fetchone()

            if row is None:
                missing.append(email)
                continue

            principal_id, name = row[0], row[1]
            existing = conn.execute(
                "SELECT principal_id FROM principal_identity WHERE provider = %s AND subject = %s",
                (ISSUER, subject),
            ).fetchone()

            if existing is not None:
                print(f"  = {name:<14} already linked")
                skipped += 1
                continue

            conn.execute(
                "INSERT INTO principal_identity (principal_id, provider, subject)"
                " VALUES (%s, %s, %s)",
                (principal_id, ISSUER, subject),
            )
            print(f"  + {name:<14} {email}")
            linked += 1
        conn.commit()

    print(f"\nlinked {linked}, already present {skipped}")
    print(f"issuer: {ISSUER}")

    if missing:
        print(
            "\nNo principal found for: "
            + ", ".join(missing)
            + "\nRun `.venv/bin/callosum init` first — it seeds the principals this links to.",
            file=sys.stderr,
        )
        return 1

    print("\n`stranger` is intentionally not linked: it demonstrates that an")
    print("authenticated but unprovisioned identity is refused (ADR-011).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
