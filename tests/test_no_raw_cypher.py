"""D-001 ban-test — no Neo4j session may be opened outside the gateway.

**The invariant:** opening a Neo4j session outside the gateway or the explicit frozen allowlist
is a D-001 violation.

Per **P2-RFC-001**, all Neo4j access must flow through the single gateway module. Opening a
driver session (``driver.session()``) anywhere else is a Defect Class **D-001** violation —
the class of bug that caused F2 (``conflicts.py`` ran raw, workspace-blind Cypher). Opening the
session is the chokepoint: no session outside the gateway ⇒ no raw Cypher can be authored.

This is a **security invariant**, not a style check (AGENTS.md: "treat permission tests as
security tests"). It is deterministic and needs no database — it parses source with ``ast``.

The frozen, already-verified query sites are grandfathered on a **TEMPORARY** allowlist: they
are allowed not because they are special, but because they already satisfy the invariant and
are covered by the frozen evaluation baseline. The allowlist is retired at the next planned
retrieval change (P2-RFC-001 §Technical debt).

Expected state:
  * RED now — ``conflicts.py`` opens sessions outside the gateway/allowlist.
  * GREEN once ``conflicts.py`` is migrated through the gateway (which does not exist yet).
"""

import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parent.parent / "src" / "callosum"

# The one module allowed to open Neo4j sessions once it exists.
GATEWAY_MODULE = "graph.py"

# (module, enclosing function) sites grandfathered per P2-RFC-001. TEMPORARY — each entry is
# removed when its query is migrated into the gateway at the next retrieval change.
FROZEN_ALLOWLIST = {
    ("store.py", "ensure_constraints"),
    ("store.py", "entity_names_for_chunks"),
    ("store.py", "upsert_chunk_node"),
    ("store.py", "apply_entity"),
    ("store.py", "apply_relationship"),
    ("retrieve.py", "graph_search"),
}


class _SessionFinder(ast.NodeVisitor):
    """Records every ``<x>.session()`` call with its innermost enclosing function name."""

    def __init__(self, module: str) -> None:
        self.module = module
        self._stack: list[str] = []
        self.sites: list[tuple[str, str, int]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "session":
            enclosing = self._stack[-1] if self._stack else "<module>"
            self.sites.append((self.module, enclosing, node.lineno))
        self.generic_visit(node)


def _session_sites() -> list[tuple[str, str, int]]:
    sites: list[tuple[str, str, int]] = []
    for path in sorted(SRC.glob("*.py")):
        finder = _SessionFinder(path.name)
        finder.visit(ast.parse(path.read_text(), filename=str(path)))
        sites.extend(finder.sites)
    return sites


def test_no_raw_cypher_outside_gateway() -> None:
    violations = [
        (module, func, line)
        for module, func, line in _session_sites()
        if module != GATEWAY_MODULE and (module, func) not in FROZEN_ALLOWLIST
    ]
    assert not violations, (
        "D-001 violation — Neo4j session opened outside the gateway/allowlist; "
        "route it through callosum.graph. Offending sites: "
        + ", ".join(f"{m}:{fn}():L{ln}" for m, fn, ln in violations)
    )
