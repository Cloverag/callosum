"""Entity + relationship extraction: chunk text in, graph mutations out.

Two paths, one cached prefix:
  - `extract(chunk)`      — synchronous, for a single doc or an interactive demo.
  - `submit_batch(chunks)` — Batch API, 50% cheaper, for bulk corpus ingestion.

Nothing here writes to the graph. Extractions become rows in `proposed_change`,
and a human approves them. That is the answer to PRD Open Question #3
("How much autonomy should AI have before requiring founder approval?").
"""

import json
from typing import Any

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

from meridian.config import EXTRACTION_MODEL, settings
from meridian.ontology import Extraction

# The cached prefix. Everything above the cache_control breakpoint must be
# byte-identical across every request or the cache silently misses — so no
# timestamps, no chunk ids, no per-document context in here. The chunk itself
# goes in the user turn, after the breakpoint.
#
# This prompt is deliberately long. Opus 4.8 will not cache a prefix under 4096
# tokens (it fails silently — `cache_read_input_tokens` just stays 0), and the
# worked examples below are what push it over the line while also being the
# single biggest lever on extraction quality. Run `check_cache_prefix()` after
# editing it.
SYSTEM_PROMPT = """\
You extract structured organizational knowledge from a startup's internal \
documents — board decks, meeting transcripts, minutes, memos, emails, and \
contracts — so that it can be stored in a knowledge graph and queried later by \
the company's founders, executives, board members, and investors.

Your output is not prose. It is a set of entities and the relationships between \
them, drawn strictly from the text you are given.

# Why this matters

The graph you populate is the company's institutional memory. Months from now a \
founder will ask questions like "Why did we reject Pricing Model B?" or "Show me \
every discussion about international expansion." The system answers those \
questions by traversing the edges you write. An edge you miss is an answer the \
company cannot retrieve. An edge you invent is an answer that is wrong — and a \
wrong answer about who approved a decision is worse than no answer at all, \
because the founder will act on it.

Prefer precision over recall. When the text is ambiguous, extract less.

# Entity types

- **Person** — a named human. Founders, executives, employees, board members, \
investors, advisors. Attributes: `role`, `org`.
- **Organization** — a company or fund. Investor firms, customers, competitors, \
partners, vendors.
- **Meeting** — a specific convening. Board meetings, reviews, standups, \
offsites. Attributes: `date` (ISO-8601 if stated), `kind`.
- **Decision** — a choice the company made, considered, or rejected. This is the \
most important entity type in the system. Attributes: `status` (one of \
`proposed`, `approved`, `rejected`, `superseded`, `deferred`) and `rationale` \
(why, in the document's own terms).
- **Document** — a referenced artifact. Decks, memos, contracts, minutes, \
reports, models. Not the document you are currently reading unless it refers to \
itself.
- **Topic** — a subject of ongoing discussion. "Pricing Model B", \
"international expansion", "Series B", "the Nigeria launch". Topics are how a \
founder searches; be generous in creating them, and name them exactly as the \
document names them.
- **ActionItem** — a follow-up task with an implied or stated owner. Attributes: \
`due`, `status`.
- **Metric** — a KPI reported at a point in time. ARR, burn rate, CAC, churn, \
headcount, runway. Attributes: `value` (verbatim, including units), `period`.

# Relationship types

Person-centric:
- `ATTENDED` — Person → Meeting.
- `PROPOSED` — Person → Decision. They put it forward.
- `SUPPORTED` — Person → Decision. They argued for it.
- `OPPOSED` — Person → Decision. They argued against it.
- `APPROVED` — Person → Decision. They had authority and exercised it. This is \
stronger than `SUPPORTED`; use it only when the text indicates formal approval, \
sign-off, or a carried vote.
- `OWNS` — Person → ActionItem, or Person → Topic. Accountability.
- `WORKS_AT` — Person → Organization.

Decision-centric:
- `MADE_IN` — Decision → Meeting. Where it happened.
- `ABOUT` — Decision → Topic, or Document → Topic. What it concerns.
- `SUPERSEDES` — Decision → Decision. The new one replaces the old one. This edge \
is how the company reconstructs history, so write it whenever the text indicates \
a reversal, revision, or replacement of an earlier choice.

Provenance:
- `PRESENTED_AT` — Document → Meeting.
- `EVIDENCE_FOR` — Document → Decision. The deck, model, or memo that backed it.
- `REPORTED_IN` — Metric → Document, or Metric → Meeting.
- `DERIVED_FROM` — ActionItem → Decision. The task exists because of the decision.

# Rules

1. **Every relationship needs verbatim evidence.** The `evidence` field must be a \
direct quote from the chunk you were given — not a paraphrase, not a summary. If \
you cannot quote text that supports the edge, do not write the edge. This is the \
single most important rule.
2. **Name entities exactly as the text names them.** Write "Pricing Model B", not \
"pricing model b" or "the B pricing model". Downstream resolution merges \
duplicates; inconsistent naming defeats it.
3. **Every `source` and `target` in a relationship must exactly match the `name` \
of an entity you also emit.** Do not reference an entity you did not extract.
4. **Distinguish support from approval.** "Sarah liked the idea" is `SUPPORTED`. \
"Sarah signed off" or "the board approved 4-1" is `APPROVED`. Founders ask \
"who approved this?" and expect an authoritative answer.
5. **Do not infer sentiment from silence.** A person attending a meeting where a \
decision was made did not thereby support it.
6. **Set `confidence` honestly.** 0.9+ for an explicit statement, 0.5-0.7 for a \
reasonable reading, below 0.5 for a guess. Low-confidence edges are routed to a \
human for review rather than discarded, so an honest 0.4 is more useful than a \
dishonest 0.9.
7. **Extract nothing rather than something plausible.** An empty extraction from \
a boilerplate page is a correct extraction.

# Worked examples

## Example A — a transcript excerpt

Input:
> RAJ: I want to close out the pricing question. Model B — the usage-based one — \
> Priya, you costed it out.
> PRIYA: I did. At our current volume it takes gross margin from 71% to 58%. I \
> can't recommend it.
> MARCUS (Sequoia): I'll push back. The margin hit is real but Model B is how \
> Stripe grew. Long game.
> RAJ: Noted, but I'm not betting the company on it this quarter. We're not doing \
> Model B. Priya, write it up for the board pack.

Correct extraction:
- Entities: Person "Raj" (role: founder); Person "Priya"; Person "Marcus" \
(role: investor, org: Sequoia); Organization "Sequoia"; Topic "Pricing Model B"; \
Decision "Reject Pricing Model B" (status: rejected, rationale: "Usage-based \
pricing would reduce gross margin from 71% to 58% at current volume"); \
Metric "gross margin" (value: "71% to 58%"); ActionItem "Write up pricing \
decision for the board pack".
- Relationships: Priya —OPPOSED→ "Reject Pricing Model B"? **No.** Priya opposed \
*Model B*, which means she *supported* rejecting it. Be careful about polarity: \
the Decision here is "Reject Pricing Model B", so Priya —SUPPORTED→ it \
(evidence: "I can't recommend it") and Marcus —OPPOSED→ it (evidence: "I'll push \
back... Long game"). Raj —APPROVED→ it (evidence: "We're not doing Model B") — \
he is the founder and this is a final call, not an opinion. The Decision \
—ABOUT→ Topic "Pricing Model B". Marcus —WORKS_AT→ "Sequoia". The ActionItem \
—DERIVED_FROM→ the Decision, and Priya —OWNS→ the ActionItem.

Note the polarity trap. Name the Decision as the action taken, then attribute \
stances relative to *that action*, not to the underlying topic.

## Example B — a superseding decision

Input:
> Following the Q2 board meeting, we are revisiting the hiring freeze announced \
> in March. With the Series B closed, we're resuming engineering hiring \
> immediately. Target: 6 engineers by end of Q3.

Correct extraction: a Decision "Resume engineering hiring" (status: approved, \
rationale: "Series B closed") that —SUPERSEDES→ Decision "Hiring freeze" \
(status: superseded), —MADE_IN→ Meeting "Q2 board meeting", and —ABOUT→ Topic \
"engineering hiring". ActionItem "Hire 6 engineers by end of Q3" \
—DERIVED_FROM→ the new Decision. The `SUPERSEDES` edge is the whole point of \
this chunk — without it, a founder asking "are we still in a hiring freeze?" \
gets a stale answer.

## Example C — boilerplate

Input:
> This document is confidential and proprietary. Distribution outside the board \
> is prohibited. © 2026 Meridian Inc.

Correct extraction: no entities, no relationships. Emit empty lists. Do not \
manufacture an Organization from a copyright line.

# Output

Return entities and relationships as structured output. Emit nothing you cannot \
quote.
"""


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings().anthropic_api_key or None)


def _system_blocks() -> list[dict[str, Any]]:
    return [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }
    ]


def extract(chunk_text: str) -> Extraction:
    """Extract from one chunk. Uses messages.parse for schema-validated output."""
    response = _client().messages.parse(
        model=EXTRACTION_MODEL,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=_system_blocks(),
        messages=[{"role": "user", "content": chunk_text}],
        output_format=Extraction,
    )
    return response.parsed_output


def _batch_schema() -> dict[str, Any]:
    """Extraction's JSON schema, minus the constraints structured outputs rejects.

    messages.parse() strips these for us and validates client-side; the Batch API
    takes a raw schema, so we do it by hand. `ge`/`le` on Relationship.confidence
    are the only offenders today — Pydantic renders them as minimum/maximum.
    """
    schema = Extraction.model_json_schema()

    def strip(node: Any) -> None:
        if isinstance(node, dict):
            for k in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"):
                node.pop(k, None)
            if node.get("type") == "object":
                node.setdefault("additionalProperties", False)
            for v in node.values():
                strip(v)
        elif isinstance(node, list):
            for v in node:
                strip(v)

    strip(schema)
    return schema


def submit_batch(chunks: dict[str, str]) -> str:
    """Queue many chunks for extraction at half price. `chunks` maps chunk_id -> text.

    Returns the batch id. Results arrive in arbitrary order — key them by
    custom_id (the chunk_id), never by position.
    """
    schema = _batch_schema()
    batch = _client().messages.batches.create(
        requests=[
            Request(
                custom_id=chunk_id,
                params=MessageCreateParamsNonStreaming(
                    model=EXTRACTION_MODEL,
                    max_tokens=8000,
                    thinking={"type": "adaptive"},
                    output_config={
                        "effort": "high",
                        "format": {"type": "json_schema", "schema": schema},
                    },
                    system=_system_blocks(),
                    messages=[{"role": "user", "content": text}],
                ),
            )
            for chunk_id, text in chunks.items()
        ]
    )
    return batch.id


def collect_batch(batch_id: str) -> dict[str, Extraction]:
    """Read a finished batch. Call only once processing_status == 'ended'."""
    out: dict[str, Extraction] = {}
    for result in _client().messages.batches.results(batch_id):
        if result.result.type != "succeeded":
            continue
        message = result.result.message
        text = next((b.text for b in message.content if b.type == "text"), None)
        if text:
            out[result.custom_id] = Extraction.model_validate(json.loads(text))
    return out


def check_cache_prefix() -> int:
    """Assert the system prompt is long enough for Opus 4.8 to actually cache it.

    Opus 4.8's minimum cacheable prefix is 4096 tokens. Below that the API accepts
    cache_control and silently caches nothing — cache_read_input_tokens just stays
    at 0 forever. Run this after any edit to SYSTEM_PROMPT.
    """
    n = _client().messages.count_tokens(
        model=EXTRACTION_MODEL,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": "x"}],
    ).input_tokens
    if n < 4096:
        raise AssertionError(
            f"System prompt is {n} tokens; Opus 4.8 needs >=4096 to cache. "
            "Caching is silently disabled — lengthen the prompt (more worked "
            "examples) or accept full price on every chunk."
        )
    return n
