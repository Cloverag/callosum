"""Pins for the bootstrap-schema and demo-script defects (#183, #184, #195).

Ungated: they read files, they do not need Postgres.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_bootstrap_schema_does_not_declare_a_global_content_hash_unique():
    """#195: uniqueness is (workspace_id, content_hash), owned by 0022."""
    text = (ROOT / "schema" / "postgres.sql").read_text(encoding="utf-8")
    assert "content_hash TEXT UNIQUE" not in text
    assert "0022_doc_content_hash_uq" in text


def test_demo_and_eval_apply_migrations_before_init():
    """#183: schema/postgres.sql has no membership table; init needs Alembic."""
    for name in ("demo.sh", "eval.sh"):
        text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "$ALEMBIC upgrade head" in text, name
        alembic_at = text.index("upgrade head")
        init_at = text.index("$CLI init")
        assert alembic_at < init_at, f"{name}: init runs before alembic"


def test_the_orphan_workspace_sites_tear_down():
    """#184: three files created workspaces and never deleted them."""
    files = (
        "tests/test_resolution_policy_engine.py",
        "tests/test_meeting_importance.py",
        "tests/test_backend_security_hardening.py",
    )
    for rel in files:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "DELETE FROM workspace" in text, rel
