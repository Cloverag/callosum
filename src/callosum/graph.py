"""Neo4j query gateway — the single place that opens Neo4j sessions (P2-RFC-001).

Neo4j has no Row-Level Security, so tenant isolation in the graph lives entirely in the query
text. This module is a **bounded repository**: one method per query shape, no raw-Cypher entry
point. Every method takes a context that carries ``workspace_id`` and injects it as
``$workspace_id``, so tenant scoping cannot be omitted — closing Defect Class **D-001**, the
class of bug that caused F2.

**Scope discipline (P2-RFC-001):** build only what the current migration requires. Today that is
the two operations ``conflicts.py`` needs. The frozen, eval-verified query sites in ``store.py``
and ``retrieve.py`` still open their own (correctly scoped) sessions and are *temporarily*
allowlisted by the D-001 ban-test; they migrate here at the next planned retrieval change. Do
not add methods for them — or any speculative helpers — ahead of that.
"""

from __future__ import annotations

from dataclasses import dataclass

from neo4j import Driver

from callosum.store import DEFAULT_WORKSPACE_ID


@dataclass(frozen=True)
class GraphContext:
    """Minimal tenant context for graph access that has no ``Principal`` (e.g. the conflict scan).

    Read paths that already carry a ``Principal`` can pass it directly once those sites migrate;
    for now only the non-frozen conflict scan uses the gateway, and it has no user principal.
    """

    workspace_id: str = DEFAULT_WORKSPACE_ID


class GraphGateway:
    """The one object allowed to open Neo4j sessions. Bounded repository; no raw Cypher."""

    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def entity_mentions(self, ctx: GraphContext) -> list[dict]:
        """Every entity in the workspace with its earliest source chunk.

        Returns one dict per entity — ``{name, type, chunk_id, ordinal, sensitivity}`` — choosing
        the lowest-ordinal (earliest) mention as the introductory-quote anchor. Scoped to
        ``ctx.workspace_id`` on both the chunk and the entity, so the scan never crosses tenants.
        """
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (c:Chunk)-[:MENTIONS]->(e:Entity)
                WHERE c.workspace_id = $workspace_id AND e.workspace_id = $workspace_id
                RETURN e.name AS name, e.type AS type,
                       c.id AS chunk_id, c.ordinal AS ordinal, c.sensitivity AS sensitivity
                ORDER BY e.name, c.ordinal ASC
                """,
                workspace_id=ctx.workspace_id,
            )
            seen: dict[tuple, dict] = {}
            for r in result:
                key = (r["name"], r["type"])
                if key not in seen:
                    seen[key] = {
                        "name": r["name"],
                        "type": r["type"],
                        "chunk_id": r["chunk_id"],
                        "ordinal": r["ordinal"],
                        "sensitivity": r["sensitivity"] or 1,
                    }
            return list(seen.values())

    def alias_edge_exists(
        self, ctx: GraphContext, name_a: str, type_a: str, name_b: str, type_b: str
    ) -> bool:
        """True if an ``ALIAS_OF`` edge already exists from a→b within this workspace.

        Entity identity is ``(name, type, workspace_id)``, so the match is tenant-scoped and a
        colliding name in another workspace can never satisfy it.
        """
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (a:Entity {name: $na, type: $ta, workspace_id: $ws})
                      -[:ALIAS_OF]-
                      (b:Entity {name: $nb, type: $tb, workspace_id: $ws})
                RETURN count(*) AS n
                """,
                na=name_a, ta=type_a, nb=name_b, tb=type_b, ws=ctx.workspace_id,
            )
            rec = result.single()
            return bool(rec and rec["n"] > 0)
