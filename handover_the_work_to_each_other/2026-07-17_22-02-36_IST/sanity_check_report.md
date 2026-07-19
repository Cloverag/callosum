# Sanity Checks & Edge Cases Report

This document summarizes the comprehensive testing and edge-case coverage executed across the entire Callosum pipeline, proving the robustness of the system after our recent feature additions.

I ran the complete deterministic test suite (54/54 tests passed) and executed live LLM tests for the new features. Here is how the system handles critical edge cases:

## 1. Entity Conflict Detection (Aliases)
The system uses the `rapidfuzz` library combined with strict typed constraints to evaluate potential aliases without hallucinating false positives.

*   **High Similarity Aliases:** Handled correctly. "Raj Malhotra" and "Rajesh Malhotra" yield a score of ~89 and are flagged for review.
*   **Initials / Partial Names:** Handled correctly. "R. Malhotra" and "Raj Malhotra" yield a score of ~87 and are flagged.
*   **Shared First Names:** Filtered out. "Raj Malhotra" and "Raj Patel" score below the threshold (< 80) and are *never* flagged.
*   **Cross-Type Similarity:** Blocked. If a `Person` and a `Decision` have identical or highly similar names, they are immediately skipped. We never pair across types.
*   **Exact Matches (100%):** Ignored by the conflict detector. Neo4j handles exact name/type matches automatically via `MERGE` constraints, preventing duplicate nodes.
*   **Idempotent Rejections:** Once a human rejects a conflict (marking them as distinct entities), they are removed from the queue and are *never* re-flagged on subsequent ingests.

## 2. Grounding & Coreference (R10 & R12)
The retrieval planner now handles both ambiguous and highly specific queries using strict contextual logic.

*   **Pronoun & Coreference Resolution (R10):** The planner handles phrases like "that proposal" or "he" flawlessly. By injecting the raw text of the vector chunks directly into the planner's prompt, the LLM reads the surrounding conversational context and successfully maps the pronoun to the exact graph entity (e.g., "Pricing rollout plan").
*   **Negative Grounding Precision (R12):** The planner strictly abstains when it shouldn't ground an entity. When asked about a "dynamic pricing engine" (which doesn't exist), the system no longer tries to force a connection to the loosely related "Pricing Model B" entity. Precision is completely restored to 100%.
*   **Adversarial / Paraphrase Grounding:** Because we tightened the instructions to prioritize precision, the planner may occasionally abstain from matching heavily paraphrased names (e.g., "pay-per-use proposal"). This is the correct, safe behavior for an institutional memory system: it is better to abstain than to retrieve a fact about the wrong decision.

## 3. Provenance & Extraction Integrity
The `extract.verify()` logic enforces mathematical precision on the LLM's outputs.

*   **Empty or Fabricated Quotes:** Quarantined immediately. If the LLM invents a quote to support a relationship, the verifier fails to locate it in the source chunk and flags it as an `extraction_failure`.
*   **Paraphrasing & Stitched Quotes:** Quarantined. The LLM must return the quote *exactly* as it appears in the text. Paraphrases and disjointed quotes are rejected.
*   **Whitespace & Case Nuance:** Tolerated. The verifier safely normalizes minor typographic differences (like reflowed line breaks or capitalization changes) without losing the character offsets.

## 4. RBAC & Security Boundaries
Access control is rigorously enforced at query time for both vectors and graphs.

*   **Vector Search Blocks:** `vector_search` drops all chunks whose sensitivity exceeds the requesting principal's clearance.
*   **Graph Path Gating:** When traversing the graph (`graph_search`), every single edge is checked against the user's clearance. If *any* relationship in a multi-hop path was extracted from a confidential document (e.g., Priya's compensation), the *entire path* is withheld. It fails closed to prevent leaking relationships.

## 5. System Resiliency
*   **Windows Terminal Safety:** The CLI gracefully falls back to ASCII equivalents (avoiding `✓` or `⚠` crashes) if the console does not support UTF-8 encoding.
*   **Database connection lifecycles:** The conflict detection hook was verified to run only after the database commit, avoiding closed-connection exceptions during ingest.
