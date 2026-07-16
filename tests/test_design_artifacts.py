"""Contract checks for static Meridian UX/design artifacts, not product behavior."""
from pathlib import Path


def test_governed_workflow_prototype_keeps_consequential_actions_local():
    root = Path(__file__).resolve().parent.parent
    html = (root / "design" / "meridian-governed-workflows.html").read_text(encoding="utf-8")
    for required in ("DESIGN PROTOTYPE", "No graph change will occur", "Human review required", "1 source withheld by your permissions", "Verified contiguous quote; approved relationship.", "aria-live", "Approval review", "Citation patterns"):
        assert required in html
    for prohibited in ("fetch(", "XMLHttpRequest", "WebSocket", "/api/"):
        assert prohibited not in html


def test_governed_workflow_design_document_preserves_the_roadmap_boundary():
    root = Path(__file__).resolve().parent.parent
    doc = (root / "docs" / "ux" / "meridian-governed-workflows.md").read_text(encoding="utf-8")
    assert "not P0/P3 implementation" in doc
    assert "R8-R13" in doc
    assert "FR-DEC-04" in doc
