"""Entity + relationship extraction: chunk text in, proposed graph mutations out.

Provider-agnostic — everything goes through `callosum.llm`. Nothing here writes to
the graph. Extractions become rows in `proposed_change`, and a human approves them.
That is this project's answer to PRD Open Question #3 ("How much autonomy should AI
have before requiring founder approval?"): none, for writes.
"""

import json

from callosum.config import Provider, settings
from callosum.llm import structured
from callosum.ontology import Extraction

# The extraction prompt. On the Anthropic path this is a cached prefix, so it must
# stay byte-identical across chunks — no timestamps, no chunk ids, no per-document
# context in here. The chunk itself goes in the user turn.
#
# It is deliberately long. The worked examples are the single biggest lever on
# extraction quality (Example A teaches the polarity trap, which is the error that
# would most damage the system), and they also push the prefix past the 4096-token
# minimum Opus needs before it caches anything at all. Ollama has no prompt caching,
# so there the length costs context but no money.
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
"international expansion", "Series B", "the hiring freeze". Topics are how a \
founder searches; be generous in creating them, and name them exactly as the \
document names them.
- **ActionItem** — a follow-up task with an implied or stated owner. Attributes: \
`due`, `status`.
- **Metric** — a KPI reported at a point in time. ARR, burn rate, gross margin, \
runway, headcount. Attributes: `value` (verbatim, including units), `period`.

# Relationship types

Person-centric:
- `ATTENDED` — Person → Meeting.
- `PROPOSED` — Person → Decision. They put it forward.
- `SUPPORTED` — Person → Decision. They argued for it.
- `OPPOSED` — Person → Decision. They argued against it.
- `APPROVED` — Person → Decision. They had authority and exercised it. This is \
stronger than `SUPPORTED`; use it only when the text indicates formal approval, \
sign-off, a carried vote, or a founder making a final call.
- `OWNS` — Person → ActionItem, or Person → Topic. Accountability.
- `WORKS_AT` — Person → Organization.

Decision-centric:
- `MADE_IN` — Decision → Meeting. Where it happened.
- `ABOUT` — Decision → Topic, or Document → Topic. What it concerns.
- `SUPERSEDES` — Decision → Decision. The new one replaces the old one. This edge \
is how the company reconstructs its own history, so write it whenever the text \
indicates a reversal, revision, or replacement of an earlier choice.

Provenance:
- `PRESENTED_AT` — Document → Meeting.
- `EVIDENCE_FOR` — Document → Decision. The deck, model, or memo that backed it.
- `REPORTED_IN` — Metric → Document, or Metric → Meeting.
- `DERIVED_FROM` — ActionItem → Decision. The task exists because of the decision.

# Rules

1. **Every relationship needs verbatim evidence.** The `evidence` field must be a \
direct quote from the chunk you were given — not a paraphrase, not a summary. If \
you cannot quote text that supports the edge, do not write the edge. This is the \
single most important rule, and it is enforced downstream: an edge whose quote does \
not appear in the source text is automatically discarded.
2. **Name entities exactly as the text names them.** Write "Pricing Model B", not \
"pricing model b" or "the B pricing model". Downstream resolution merges duplicates \
by exact name; inconsistent naming defeats it.
3. **Every `source` and `target` in a relationship must exactly match the `name` of \
an entity you also emit.** Do not reference an entity you did not extract.
4. **Distinguish support from approval.** "Sarah liked the idea" is `SUPPORTED`. \
"Sarah signed off", "the board approved 4-1", or the CEO saying "we're doing this" \
is `APPROVED`. Founders ask "who approved this?" and expect an authoritative answer.
5. **Do not infer sentiment from silence.** A person attending a meeting where a \
decision was made did not thereby support it.
6. **Set `confidence` honestly.** 0.9+ for an explicit statement, 0.5–0.7 for a \
reasonable reading, below 0.5 for a guess. Low-confidence edges are routed to a \
human for review rather than discarded, so an honest 0.4 is more useful than a \
dishonest 0.9.
7. **Extract nothing rather than something plausible.** An empty extraction from a \
boilerplate page is a correct extraction.

# Worked examples

## Example A — a transcript excerpt, and the polarity trap

Input:
> RAJ: I want to close out the pricing question. Model B — the usage-based one — \
> Priya, you costed it out.
> PRIYA: I did. At our current volume it takes gross margin from 71% to 58%. I \
> can't recommend it.
> MARCUS (Sequoia): I'll push back. The margin hit is real but Model B is how \
> Stripe grew. Long game.
> RAJ: Noted, but I'm not betting the company on it this quarter. We're not doing \
> Model B. Priya, write it up for the board pack.

The decision here is **"Reject Pricing Model B"** — name a Decision by the action \
taken, not by the thing it concerns. Now attribute stances *relative to that \
action*, and watch the polarity:

- Priya argued against Model B, which means she **SUPPORTED** the rejection. \
Evidence: "I can't recommend it."
- Marcus argued *for* Model B, which means he **OPPOSED** the rejection. \
Evidence: "I'll push back."
- Raj **APPROVED** the rejection. Evidence: "We're not doing Model B." He is the \
founder and this is a final call, not an opinion.

Getting this backwards is the most damaging error you can make: it tells the founder \
that the person who fought hardest for a plan was against it. Read the polarity twice.

Also extract: Person "Marcus" (role: investor, org: Sequoia) —WORKS_AT→ Organization \
"Sequoia"; the Decision —ABOUT→ Topic "Pricing Model B"; Metric "gross margin" \
(value: "71% to 58%"); ActionItem "Write up the pricing decision for the board pack" \
—DERIVED_FROM→ the Decision, with Priya —OWNS→ it.

## Example B — a superseding decision

Input:
> Following the Q2 board meeting, we are revisiting the hiring freeze announced in \
> March. With the Series B closed, we're resuming engineering hiring immediately. \
> Target: 6 engineers by end of Q3.

Extract a Decision "Resume engineering hiring" (status: approved, rationale: "Series \
B closed") that —SUPERSEDES→ Decision "Hiring freeze" (status: superseded), \
—MADE_IN→ Meeting "Q2 board meeting", and —ABOUT→ Topic "engineering hiring". \
ActionItem "Hire 6 engineers by end of Q3" —DERIVED_FROM→ the new Decision.

The `SUPERSEDES` edge is the entire point of this chunk. Without it, a founder asking \
"are we still in a hiring freeze?" gets a stale and confidently wrong answer.

## Example C — boilerplate

Input:
> This document is confidential and proprietary. Distribution outside the board is \
> prohibited. © 2026 Meridian Inc.

Extract nothing. Emit empty lists. Do not manufacture an Organization from a \
copyright line, and do not invent a Decision from the word "prohibited".

# Output

Return entities and relationships as structured output. Emit nothing you cannot quote.
"""


def extract(chunk_text: str) -> Extraction:
    """Extract entities and relationships from one chunk, then verify the quotes."""
    result = structured(SYSTEM_PROMPT, chunk_text, Extraction)
    return verify_evidence(result, chunk_text)


def verify_evidence(extraction: Extraction, chunk_text: str) -> Extraction:
    """Drop any relationship whose evidence quote is not actually in the source.

    The prompt *asks* for verbatim quotes. This *enforces* it, and the distinction
    matters more on a smaller model than on a frontier one. A model that paraphrases
    under pressure — or fabricates a quote outright — produces an edge that looks
    well-sourced and is not. That is the worst failure this system can have: a
    confident, cited, wrong answer about who approved something.

    Matching is whitespace-normalised and case-insensitive, because models reflow
    quotes across line breaks. It is not fuzzy beyond that. A paraphrase is a
    fabrication, and it gets cut.
    """
    haystack = " ".join(chunk_text.split()).lower()

    kept = [
        rel
        for rel in extraction.relationships
        if (needle := " ".join(rel.evidence.split()).lower()) and needle in haystack
    ]

    return Extraction(entities=extraction.entities, relationships=kept)


# ---------------------------------------------------------------------------
# Batch API — Anthropic only (50% cheaper, async). Ollama has no batch endpoint;
# there, extraction is a sequential loop and costs nothing anyway.
# ---------------------------------------------------------------------------


def _require_anthropic(feature: str) -> None:
    if settings().provider != Provider.ANTHROPIC:
        raise RuntimeError(
            f"{feature} is Anthropic-only, but PROVIDER={settings().provider}. "
            "On Ollama just run the normal ingest — extraction is sequential and free."
        )


def submit_batch(chunks: dict[str, str]) -> str:
    """Queue many chunks for extraction at half price. Maps chunk_id -> text."""
    _require_anthropic("The Batch API")

    import anthropic
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    from callosum.llm import _inline_refs

    cfg = settings()
    schema = _strip_constraints(_inline_refs(Extraction.model_json_schema()))

    batch = anthropic.Anthropic(api_key=cfg.anthropic_api_key or None).messages.batches.create(
        requests=[
            Request(
                custom_id=chunk_id,
                params=MessageCreateParamsNonStreaming(
                    model=cfg.anthropic_extraction_model,
                    max_tokens=8000,
                    thinking={"type": "adaptive"},
                    output_config={
                        "effort": "high",
                        "format": {"type": "json_schema", "schema": schema},
                    },
                    system=[{
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }],
                    messages=[{"role": "user", "content": text}],
                ),
            )
            for chunk_id, text in chunks.items()
        ]
    )
    return batch.id


def collect_batch(batch_id: str) -> dict[str, Extraction]:
    """Read a finished batch. Results arrive in arbitrary order — key by custom_id."""
    _require_anthropic("The Batch API")

    import anthropic

    client = anthropic.Anthropic(api_key=settings().anthropic_api_key or None)
    out: dict[str, Extraction] = {}

    for result in client.messages.batches.results(batch_id):
        if result.result.type != "succeeded":
            continue
        content = next(
            (b.text for b in result.result.message.content if b.type == "text"), None
        )
        if content:
            out[result.custom_id] = Extraction.model_validate(json.loads(content))

    return out


def _strip_constraints(schema):
    """Remove the JSON-Schema keywords Anthropic's structured outputs rejects.

    `messages.parse()` strips these for us and validates client-side, but the Batch
    API takes a raw schema. `ge`/`le` on Relationship.confidence are the only
    offenders today — Pydantic renders them as minimum/maximum.
    """
    if isinstance(schema, dict):
        for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"):
            schema.pop(key, None)
        if schema.get("type") == "object":
            schema.setdefault("additionalProperties", False)
        for value in schema.values():
            _strip_constraints(value)
    elif isinstance(schema, list):
        for value in schema:
            _strip_constraints(value)
    return schema
