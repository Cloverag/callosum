# DRAFT for review — Board Meeting 14 (identity grounding / entity disambiguation)

**Status: transcript draft only. NOT wired.** This file lives under `docs/proposals/`, not
`data/demo/`, so nothing here is ingested or evaluated until a reviewer approves it. No gold
questions, no eval changes, no ontology changes are proposed here — per the freeze, those
come only after this transcript is accepted.

## What this stresses

**Identity grounding and entity disambiguation**, harder than the current fixture. Two
people whose surface forms deliberately collide:

| Entity | Surface forms that appear in the text | Role |
|---|---|---|
| **Raj Malhotra** | "Raj Malhotra", "Raj", "R. Malhotra", "the CEO" | CEO (existing cast) |
| **Rajesh Kumar** | "Rajesh Kumar", "Rajesh", "R. Kumar" | Staff Engineer, Platform (new) |

The traps, all present naturally in dialogue:
- **"Raj" vs "Rajesh"** — one is short for Raj Malhotra, the other is a *different* person's
  first name. A linker that treats "Rajesh" as the long form of "Raj" collapses two people.
- **"R. Malhotra" vs "R. Kumar"** — same initial, different surnames. An initial-only match
  ("R.") is ambiguous and must not resolve without the surname.
- **One deliberately ambiguous line** ("R. signed off on the deploy") that the transcript
  *itself later disambiguates* — so the evidence a reviewer needs to grade it is in the text,
  never a guess.

Topic is a **production incident / rollout decision**, deliberately not pricing, to keep this
capability isolated from the pricing-polarity ambiguity documented in the 2026-07-17 findings.

## Relationship to the existing fixture — reviewer decision needed

`data/demo/board_meeting_14_transcript.txt` already exists (Rajesh Malhotra, CEO, vs a
distinct guest **Raj Patel**; "Raj" = short for Rajesh Malhotra). **This draft is a different
design and would conflict if dropped in under the same name.** Note two clashes for the
reviewer to resolve before any wiring:
1. The existing fixture makes the CEO's full name *Rajesh* Malhotra and uses "Rajesh" for the
   CEO. This draft assigns "Rajesh" to a *different* person (Kumar) and names the CEO *Raj*
   Malhotra. Both cannot be true in one corpus.
2. Slot: this could **replace** the existing M14, **supplement** it as a new meeting (e.g.
   M17), or be held. That is a corpus-design call, not mine to make under the freeze.

Recommended if accepted: take the CEO's canonical name as **Raj Malhotra** consistently and
introduce **Rajesh Kumar** as a genuinely separate engineer, retiring the older M14's
Rajesh-Malhotra spelling to avoid a corpus-internal contradiction.

---

## Transcript (draft)

```
Meridian Inc — Board Meeting 14
Date: 2026-11-18
Attendees: Raj Malhotra (CEO, co-founder), Priya Nair (CFO), Marcus Webb (Sequoia, board),
           Rajesh Kumar (Staff Engineer, Platform — attending for the incident review)

---

RAJ: Before the standing agenda, we're opening with the November 9th outage. Rajesh is here
to walk the board through it. Rajesh, you led the response — take us through what happened.

RAJESH: Thanks. On the 9th we shipped the new billing-events pipeline to production. The
rollout was staged, but the migration step held a lock on the events table longer than
staging predicted, and checkout backed up behind it. Customer-facing impact was forty-one
minutes of failed charges before we rolled back.

MARCUS: Forty-one minutes. Who made the call to ship on a Friday?

RAJESH: I did. I owned the rollout and I approved the deploy window. That one's on me.

PRIYA: The written incident summary says "R. signed off on the deploy." I want that pinned
down for the record, because we have two R's in this room. Was that R. Kumar or R. Malhotra?

RAJESH: R. Kumar. Me. Raj wasn't in the approval path for the deploy — engineering owns
deploy windows, not the CEO.

RAJ: Correct. I didn't sign the deploy off and I don't want the minutes reading as if I did.
I approved the *rollback* once we were in the incident, because that needed an exec on the
call to authorize the customer credits. Two different decisions, two different people.

MARCUS: Understood. So to be precise: Rajesh Kumar approved the deploy, and Raj Malhotra
approved the rollback and the credits. The CEO's name shouldn't be anywhere near the deploy
approval.

RAJ: Right.

PRIYA: Good. Because the last board packet had "R. Malhotra approved the pipeline change,"
and that's wrong — that was Rajesh's approval, not mine. The initials got merged by whoever
wrote the summary. I don't want that error carried forward.

RAJESH: For what it's worth, the postmortem doc has it correct: deploy approver Rajesh Kumar,
rollback approver Raj Malhotra. It's only the one-page summary that collapsed the two.

RAJ: Then the action items. Rajesh, you own the remediation — the lock needs to move off the
hot path before we re-attempt the rollout.

RAJESH: I own it. I'll bring the revised rollout plan to the next review before anything ships
again.

RAJ: And Priya, you own the customer-credit reconciliation from the failed charges.

PRIYA: Owned. One correction for the record, though — going forward, please don't let anyone
minute me as "R." in an engineering context. In this company "R." next to a deploy is Kumar,
and "R." next to a board decision is Malhotra, and the summaries keep guessing wrong.

MARCUS: Agreed. Full surnames on approvals from now on.

RAJ: Settled. Rajesh owns the remediation and the new rollout plan; I approved the rollback
and the credits; Priya owns the reconciliation. Let's move to the standing agenda.
```

---

## Disambiguation key (for the reviewer building gold later — not gold itself)

Everything a grader needs is supported by a verbatim sentence in the transcript, so no
judgement call is required:

- **Rajesh Kumar** (= "Rajesh", "R. Kumar") **approved the deploy** — "R. Kumar. Me… I owned
  the rollout and I approved the deploy window."
- **Raj Malhotra** (= "Raj", "R. Malhotra", "the CEO") **approved the rollback and the credits**
  — "I approved the *rollback*… that needed an exec on the call to authorize the customer
  credits."
- **The CEO did NOT approve the deploy** — "I didn't sign the deploy off." (A grounding
  *negative*: a question implying the CEO approved the deploy should not resolve to that.)
- **"R. Malhotra approved the pipeline change" is a stated error in a source document** — the
  summary merged the initials; the postmortem has it right. This is a built-in provenance /
  conflict case: two source documents disagree, and the transcript names which is correct.
- **Remediation / new rollout plan owner:** Rajesh Kumar. **Reconciliation owner:** Priya Nair.

## Why these are hard beyond the current benchmark

- The current M14 tests one alias cluster against one clearly-labelled outsider. This tests
  **two clusters that share tokens** ("Raj"/"Rajesh", "R. Malhotra"/"R. Kumar"), which is the
  realistic failure mode: not "is this an alias?" but "*whose* alias is this?"
- It embeds a **document-vs-document conflict on identity** (summary says R. Malhotra, post-
  mortem says R. Kumar), exercising provenance without any ontology change — reusing the same
  conflicting-source pattern as the FY27 forecast case, but on *who did what* rather than *how
  much*.
- It contains a **grounding negative** ("the CEO approved the deploy") whose correct answer is
  abstention, backed by an explicit denial in the text — a cleaner negative than "dynamic
  pricing engine," because the near-miss entity (Raj Malhotra) is present and plausible.
