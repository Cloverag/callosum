# Handover notes

This folder is the shared continuity record for work that one collaborator may need to
resume, review, or challenge later. It is deliberately separate from product and research
documentation: `ROADMAP.md` states the authoritative gate status, while a timestamped
handover captures the practical state of an in-progress session.

Use this folder when work is paused, handed to another person, blocked by a local service,
or completed but awaiting review. The goal is to eliminate rediscovery: the next person
should be able to understand what happened, what evidence exists, and what action is safe
without relying on chat history.

## Naming and structure

Create one directory per handover, using local India time:

```text
handover_the_work_to_each_other/
  YYYY-MM-DD_HH-mm-ss_IST/
    <scope>_handover.md
```

Keep the note focused on a bounded checkpoint, bug, review, or implementation slice. Link
to authoritative files instead of copying long material into the handover.

## Information every handover must include

1. **Identity and scope**
   - Timestamp, repository, branch, author/owner if known, and the handover topic.
   - Last relevant commit SHA and whether it was pushed.

2. **Status stated precisely**
   - Separate *implemented*, *deterministically tested*, *live evaluated*, *reviewed*, and
     *formally accepted*. Do not use ?done? when only implementation is complete.
   - Mention any active roadmap checkpoint and its gate state.

3. **What changed**
   - Files or components changed, the intent, and important design/security decisions.
   - Links to related roadmap, findings, PRD, issue, or experiment records.

4. **Verification evidence**
   - Exact commands run and concise outcomes.
   - Environment/provider/model details where results depend on them.
   - State clearly what was not run and why.

5. **Outstanding work and blockers**
   - Specific remaining tasks, their owner if known, and why they remain.
   - Distinguish a technical blocker from a missing product/review decision.

6. **Recommended next action**
   - The smallest safe next step, with commands and warnings for destructive operations.
   - Include expected evidence or decision needed to close the handover.

7. **Guardrails**
   - Invariants that must not be weakened and files that should not be changed without
     evidence/review.
   - Note uncommitted changes and whether they belong to someone else.

## Questions to answer before closing a handover

- Is the work committed and pushed? If not, who is expected to do that?
- What proves the claimed status, and where is that proof recorded?
- Which required tests or live checks have not run, and why?
- Is there any destructive command, secret, external access, approval, or product decision
  the next collaborator must obtain before proceeding?
- Does the authoritative roadmap need an update, or is the work intentionally only local?
- What would make the next person accidentally overstate progress or violate a security
  invariant?

## Current handover

- [Devguru grounding salvage — gated approach confirmed](2026-07-18_03-02-19_IST/devguru-grounding-salvage_handover.md)
- [R8-R13 handover](2026-07-16_08-24-44_IST/R8-R13_handover.md)

Keep this README short and stable. Put session-specific facts in the timestamped note.
