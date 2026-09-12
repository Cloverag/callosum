"""Authenticated Q&A over the frozen retrieval engine.

The UI assistant rail still uses a local gold-graph snapshot (issue #100 / P6).
This route is the HTTP surface for `callosum.retrieve.ask`: identity from the
session, clearance from membership, never from the request. Graph writes are
unchanged — extraction still cannot reach Neo4j from here.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from callosum import retrieve, store
from meridian.api.deps import CurrentPrincipal

router = APIRouter(prefix="/api", tags=["ask"])


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(..., min_length=1, max_length=4000)


class AskEvidence(BaseModel):
    document_title: str
    source: str
    score: float


class AskResponse(BaseModel):
    text: str
    withheld: int
    graph_facts: list[str]
    evidence: list[AskEvidence]
    latency_ms: int


@router.post("/ask", response_model=AskResponse)
def ask_question(req: AskRequest, principal: CurrentPrincipal) -> AskResponse:
    """Answer a question for the session principal.

    Evidence *text* is omitted on purpose: titles and the synthesised answer are
    enough for a client, and the leak-sweep must not have to special-case chunk
    bodies that the caller already could not have retrieved as a document.
    """
    driver = store.neo()
    try:
        with store.pg(principal.workspace_id) as conn:
            answer = retrieve.ask(conn, driver, req.question, principal)
    finally:
        driver.close()
    return AskResponse(
        text=answer.text,
        withheld=answer.withheld,
        graph_facts=list(answer.graph_facts),
        evidence=[
            AskEvidence(
                document_title=item.document_title,
                source=item.source,
                score=item.score,
            )
            for item in answer.evidence
        ],
        latency_ms=answer.latency_ms,
    )
