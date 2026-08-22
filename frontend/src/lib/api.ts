/**
 * Entity conflicts — the review queue for two names the extractor thinks are one.
 *
 * ---------------------------------------------------------------------------
 * WHY THIS FILE WAS REWRITTEN (2026-08-14)
 * ---------------------------------------------------------------------------
 * It was the last module in `lib/` still holding its own `fetch`, its own
 * `API_BASE`, and a fallback that answered with invented data when the API said
 * no. Every method had the same shape:
 *
 *     if (res.ok) return await res.json();
 *     ...
 *     return mockConflicts.filter(c => c.status === 'pending');
 *
 * `GET /api/conflicts` had in fact been returning **500 since 2026-08-10** — the
 * handler called `deps.resolve_principal`, which has never existed. Nothing on
 * screen said so. The dashboard read the fallback and told the operator
 * "2 name conflicts awaiting your review", naming Raj Patel and Sequoia Capital,
 * on the primary screen, as measured fact. rules.md §2 forbids exactly that: a
 * surface may not present as evidence something the record does not contain.
 *
 * The write paths were worse than the read. `approveConflict` and
 * `rejectConflict` caught the failure, mutated a module-level array, and
 * returned `{ status: 'approved' }`. The card animated away and the operator was
 * told a merge had been recorded into an append-only graph that had not been
 * touched.
 *
 * Three further methods — `getMeetingReadiness`, `getAgendaSuggestions` and
 * `publishPreread` — are deleted rather than ported. No surface called any of
 * them: `/prepare` computes readiness through `lib/prep.ts`, which counts real
 * rows. `publishPreread` returned `{ status: "published" }` unconditionally on
 * failure, so the one thing it was reachable for was reporting that a pre-read
 * had gone to the board when it had not. The backend endpoints from #114 stay;
 * they have no frontend consumer yet, and a wrong one is worse than none.
 *
 * What replaces all of it is `lib/http.ts`, which every other module already
 * uses: same-origin `/api`, the session cookie, and the server's error envelope
 * raised as an `ApiError` for the surface to render. A failed load now looks
 * like a failed load.
 */

import { apiGet, apiPost } from "@/lib/http";

/** Mirrors `ConflictResponse` in `meridian/api/conflicts.py`. */
export type EntityConflict = {
  id: string;
  name_a: string;
  type_a: string;
  name_b: string;
  type_b: string;
  similarity: number;
  quote_a: string;
  quote_b: string;
  sensitivity: number;
  status: "pending" | "approved" | "rejected";
  /**
   * Rendered as "Detected {date}" on the conflict card. It was declared here and
   * absent from the server's response model, so the card formatted
   * `new Date(undefined)` — added to `ConflictResponse` in the same pass, and
   * asserted by `tests/test_conflicts_api.py::test_wire_shape_matches_the_frontend_contract`.
   */
  created_at: string;
};

export const apiClient = {
  /**
   * The pending review queue.
   *
   * Throws on failure. The caller decides what a failure looks like — there is no
   * answer this function could return that would be both non-empty and true.
   */
  getPendingConflicts(): Promise<EntityConflict[]> {
    return apiGet<EntityConflict[]>("/conflicts", { status: "pending" });
  },

  /**
   * Approve the merge, writing an `ALIAS_OF` edge and an audit event.
   *
   * No `reviewerId` parameter. The old signature took one, defaulted it to a
   * hardcoded UUID, and never sent it: the server takes the reviewer from the
   * session, which is the only version of that fact a client cannot forge.
   */
  approveConflict(id: string): Promise<{ id: string; status: string; change_id: string }> {
    return apiPost(`/conflicts/${id}/approve`);
  },

  /** Reject the merge, recording that the two entities are distinct. */
  rejectConflict(id: string): Promise<{ id: string; status: string }> {
    return apiPost(`/conflicts/${id}/reject`);
  },
};
