# Demo script — 8 minutes

A walkthrough for recording. Setup is in [demo-setup.md](./demo-setup.md); everything
below assumes it is done and both processes are running.

**The one line to land:** *this system cannot tell you something a document does not
say, and it cannot show you something you are not cleared to see.* Every beat serves
that. If a beat runs long, cut it — except beats 5 and 6, which are the demonstration.

Two browser profiles side by side, or one window and a logout between beats 4 and 5.

---

## 0 · Before recording

- [ ] `curl -s localhost:8000/health/engine` returns ok
- [ ] `curl -s -o /dev/null -w "%{http_code}" localhost:3000/api/meetings` returns **401**
- [ ] Signed out of Keycloak in the recording profile
- [ ] Terminal font large enough to read at 1080p
- [ ] `docs/screenshots/` captures done, if you want stills as well

---

## 1 · The problem (0:00 – 0:45)

Open the repository, not the app.

> "Six months after a board meeting, nobody can answer 'is that still our position?'
> without reading everything again. The obvious fix is to put the documents in a vector
> store and ask a language model — and that fails in a specific way. The model will
> answer confidently whether or not any document supports it. For a search engine that
> is a bad result. For a record of what a board decided, it is a fabricated minute, and
> it looks exactly like a real one."

Show `data/demo/` briefly.

> "Sixteen documents about a fictional company. Board meeting 12 rejects a pricing
> model. Meeting 13 reverses it. That reversal is the question worth asking."

---

## 2 · Sign in (0:45 – 1:45)

Go to `localhost:3000`. It redirects to Keycloak.

> "Authentication is OIDC through Keycloak. The session is an httpOnly signed cookie.
> Identity maps on provider and subject — never on email, because email is mutable and
> reassignable."

Sign in as **raj / raj**.

Then the workspace selection.

> "Authenticating proved who I am. It said nothing about which workspace I may read, so
> that is a separate, explicit step, re-validated on every single request."

**Optional, 20 seconds, and worth it:** sign in as **stranger / stranger** first.

> "This user exists in Keycloak and the password is correct. Meridian has no record of
> them, and logging in does not create one."

→ **403.** No session is created at all.

---

## 3 · The board, and where the data comes from (1:45 – 2:45)

**Dashboard** → **Meetings** → open **Board Meeting 13**.

> "Meetings, agenda items, decisions, resolutions, commitments. Eight aggregates, each
> with its own migration and its own state machine."

Point at the dashboard's unmeasured figures.

> "Those em dashes matter. Those are numbers nothing in this system counts, so the
> dashboard says so instead of showing a plausible zero. Earlier versions of this page
> showed invented figures — and worse, invented quotes. Both were found by checking them
> against the corpus rather than by reading the code."

---

## 4 · Evidence, not summary (2:45 – 4:15)

**Memory** (the `/memory` route). Click the **Adopt Usage-Based Pricing** node.

> "This is the knowledge graph. Every edge here carries a verbatim quote that a machine
> located in a source document, character for character."

Show the evidence panel — the quote and its document.

> "That sentence is not a summary and not a paraphrase. It is text that exists in
> `board_meeting_13_transcript`. If the extraction model had invented it, the edge would
> not exist — it would be quarantined, with a typed reason, because the verifier is a
> string search and not a judgement call."

Follow the `SUPERSEDES` edge back to the March rejection.

> "And this is why the graph earns its place. 'Is Model B still rejected?' needs an edge
> that lives in a different document from the answer. Chunk similarity does not express
> that. Measured: with grounding off, graph-fact recall is 38%. With it on, 100%. Same
> traversal code, same corpus, same questions."

---

## 5 · Authorization — the first half (4:15 – 5:15)

Still as **raj**. Open **Packs** → the Board Meeting 14 pack.

> "Three documents in this pack. One of them is the executive compensation review,
> which is restricted."

Then **Documents**.

> "Sixteen documents visible."

Say the number aloud. It is the control for the next beat.

---

## 6 · Authorization — the second half (5:15 – 6:30)

Switch to the **marcus** profile — investor, clearance 1. Same workspace, same pack.

> "Marcus is an investor observer. Same pack, same URL."

→ **Two items, numbered 1 and 2.**

> "Two items, not three. And look at the numbering — one and two, not one and three.
> The filtering happens in the database before the pack is serialised, and the positions
> are renumbered afterwards, so there is no gap to notice and no total to subtract from.
>
> There is also no notice saying 'one item hidden' — because a notice that appeared only
> when something was hidden would itself be a disclosure. It would tell an investor the
> board discussed something that excludes them."

Then **Documents** → **14**.

> "Fourteen, against Raj's sixteen. Not redacted, not greyed out. Never selected."

**If asked why `/memory` *does* show a withheld count:** because `graph_search` returns
one and `list_packs` cannot. Different contracts, and the UI states exactly what each
can support.

---

## 7 · The engineering (6:30 – 7:45)

Terminal.

```bash
.venv/bin/callosum eval-mechanism
```

> "A deterministic evaluation with no cloud model involved — because security
> verification must never depend on a provider being up. Candidate recall 22 of 22,
> traversal 21 of 21, RBAC fail-closed."

Then the part that matters:

> "It appends to a CSV, and the rows have to come back byte-identical. When I changed
> the definition of 'verified' inside the frozen core, the gate passed *and* the rows
> did not move — which is the evidence the accepted-input set narrowed without changing
> a single retrieval outcome. No amount of code review demonstrates that."

Optionally show `git log --oneline -8`.

> "Six hundred and ten backend tests, a hundred and sixty-eight on the frontend. Every
> mock swap in this phase was supposed to be a change of transport; six of seven found a
> contract defect instead."

---

## 8 · Close (7:45 – 8:00)

> "Two tracks. The research engine is closed and frozen against a measured baseline. The
> product is frozen feature-complete at phase three of thirteen — and it is frozen, not
> accepted, because two of its three exit criteria were deliberately deferred and
> recorded rather than rounded up.
>
> The corpus is synthetic, and that is the biggest limitation. A quote-location bug that
> would have dropped edges from every Windows-sourced document survived 461 tests and a
> green evaluation gate, because no file in the corpus uses CRLF line endings. The
> corpus could not exercise it. That is in the write-up, not hidden in it."

---

## Notes for the recording

**Do not** demonstrate creating or editing a meeting unless you have rehearsed it. The
write path works and has a genuinely good conflict dialog, but it needs two sessions
editing the same meeting to show anything, and that is a five-minute detour.

**Do not** open `/entity-conflicts`. It is still backed by a mock and is not on the
demonstrated path.

**If a page errors mid-recording**, it will now say so explicitly rather than hanging on
a skeleton. Read the message aloud — an honest failure state is on-message for this
project, and pretending it did not happen is not.

**The strongest 90 seconds** are beats 5 and 6 back to back. If you only record one
thing, record two windows side by side showing 16 documents and 14, and three pack items
and two.
