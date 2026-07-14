# Meridian — Architecture

## System overview

```mermaid
flowchart LR
    subgraph SRC["Sources"]
        direction TB
        S1["Board decks"]
        S2["Meeting transcripts"]
        S3["Emails and memos"]
        S4["Contracts"]
    end

    ING["<b>1. Ingestion</b><br/>parse → dedupe by hash → chunk"]

    EXT["<b>2. Extraction — Claude Opus</b><br/>entities: Person, Decision, Meeting,<br/>Topic, ActionItem, Metric<br/>edges: APPROVED, OPPOSED, SUPERSEDES<br/><i>every edge carries a verbatim quote</i>"]

    subgraph STORE["3. Storage"]
        direction TB
        GRAPH[("<b>Neo4j</b><br/>knowledge graph<br/><i>how are these related?</i>")]
        PG[("<b>Postgres + pgvector</b><br/>raw docs · embeddings<br/>RBAC · version history<br/><i>what is similar?</i>")]
    end

    subgraph RET["4. Retrieval"]
        direction TB
        PLAN["Planner<br/><i>graph? vector? both?</i>"]
        SEARCH["Graph traversal ‖ Vector search"]
        PERM["<b>PERMISSION FILTER</b><br/>runs BEFORE merge"]
        MERGE["Merge context"]
        PLAN --> SEARCH
        SEARCH --> PERM
        PERM --> MERGE
    end

    LLM["<b>5. Claude</b><br/>grounded answer + citations"]
    USER(["Founder<br/><i>Why did we reject Pricing Model B?</i>"])
    APPROVE["<b>Human Approval Queue</b><br/>the LLM proposes, a human approves<br/><i>the AI never writes to memory directly</i>"]

    SRC --> ING
    ING --> EXT
    EXT -.-> APPROVE
    APPROVE == "approved writes only" ==> GRAPH
    APPROVE ==> PG
    GRAPH <-. "<b>shared chunk UUID</b><br/>the bridge" .-> PG
    GRAPH --> PLAN
    PG --> PLAN
    MERGE --> LLM
    LLM --> USER
    USER -.-> PLAN

    classDef store fill:#e8f0f7,stroke:#4a6fa5,stroke-width:2px
    classDef danger fill:#fdeaea,stroke:#c0392b,stroke-width:3px
    classDef human fill:#fdf3e0,stroke:#d68910,stroke-width:2px
    classDef ai fill:#eaf4f0,stroke:#2e8b7a,stroke-width:2px

    class GRAPH,PG store
    class PERM danger
    class APPROVE,USER human
    class EXT,LLM ai
```

**The bridge is the thesis.** A chunk row in Postgres and its `(:Chunk)` node in Neo4j share one UUID. So a semantic hit can traverse into the graph, and a graph traversal can pull back the exact paragraph that proves it. Neither store alone can do this:

| Store | Answers | Cannot answer |
|---|---|---|
| Postgres + pgvector | "What text is semantically similar?" | "Who approved this, and in which meeting?" |
| Neo4j | "How are these entities related?" | "What does this 20-page PDF actually say?" |

---

## Retrieval: "Why did we reject Pricing Model B?"

```mermaid
sequenceDiagram
    autonumber
    actor F as Founder
    participant P as Planner
    participant G as Neo4j
    participant V as pgvector
    participant A as Permission filter
    participant L as Claude

    F->>P: Why did we reject Pricing Model B?
    Note over P: Intent: a decision and its rationale.<br/>Needs BOTH stores.

    par Graph traversal
        P->>G: Topic "Pricing Model B" → its Decision →<br/>everyone who PROPOSED / SUPPORTED /<br/>OPPOSED / APPROVED it
        G-->>P: Decision "Reject Pricing Model B" (rejected)<br/>Priya SUPPORTED, Marcus OPPOSED, Raj APPROVED<br/>made in Meeting 12, one open ActionItem
    and Vector search
        P->>V: embed(question) → top-k chunks by cosine
        V-->>P: transcript excerpt, board deck p.7,<br/>investor email, minutes
    end

    Note over P,V: Both result sets carry chunk UUIDs, so graph hits<br/>resolve to text and text hits resolve to entities.

    P->>A: candidate context + caller (role, clearance)
    A->>A: drop every chunk above the caller's clearance
    A-->>P: filtered context (2 chunks withheld)

    Note over A: An investor asking this never loads the salary<br/>discussion. Enforced here, not by asking the LLM nicely.

    P->>L: filtered context only
    L-->>F: Rejected in Meeting 12 (Mar 4). Rationale: gross margin<br/>would fall 71% → 58% at current volume. Priya supported<br/>the rejection, Marcus (Sequoia) opposed it, Raj made the call.<br/>Sources: [transcript §4] [board deck p.7]
```

**Why the permission filter sits where it does.** Filtering *after* retrieval means the forbidden text was already loaded, ranked, and sitting in memory next to the prompt — one bug away from the context window. Filtering *before* means it was never read. The PRD asks for role-based access control over confidential board material; this is the only placement that actually delivers it.

---

## Memory update — the AI proposes, a human disposes

```mermaid
stateDiagram-v2
    direction LR

    [*] --> Ingested
    Ingested --> Extracted
    Extracted --> Pending
    Pending --> Approved
    Pending --> Rejected
    Approved --> Committed
    Rejected --> [*]
    Committed --> Superseded
    Superseded --> Committed
    Committed --> [*]

    note right of Ingested
        Meeting ends, transcript uploaded
    end note

    note right of Pending
        Founder reviews the evidence quote
        that Claude was forced to attach
    end note

    note right of Committed
        Graph mutated, embedding written,
        version row appended
    end note

    note right of Superseded
        Still queryable. Nothing is ever deleted —
        "we reversed the hiring freeze in June" is
        only answerable if the freeze is still there.
    end note
```

Nothing here is destructively updated. A superseded decision stays in the graph with a `SUPERSEDES` edge pointing at it.

This is also the project's answer to **PRD Open Question #3** — *"How much autonomy should AI have before requiring founder approval?"* Our answer: **none for writes.** Read freely, propose freely, mutate never.
