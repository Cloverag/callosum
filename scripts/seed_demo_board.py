"""Seed the board-domain demo data that the web demo renders.

Deployment tooling. `callosum init` seeds principals and memberships; the ingest
commands load documents. Nothing creates the *product* domain — meetings, agendas,
decisions, packs, minutes, resolutions, commitments — so a freshly set-up instance
authenticates correctly and then shows nine empty pages.

    .venv/bin/python scripts/seed_demo_board.py

Idempotent: it looks for its own meetings by title and does nothing if they exist.

---------------------------------------------------------------------------
THE DATA IS THE CORPUS, NOT AN INVENTION
---------------------------------------------------------------------------
Every meeting, decision and quote below corresponds to a document in `data/demo/`.
Board Meeting 12 rejected Pricing Model B; Board Meeting 13 reversed that decision;
Board Meeting 14 covered the billing outage and the two directors whose initials were
merged. Writing board data that contradicted the transcripts would put the product and
the knowledge graph in disagreement on the same screen.

**Everything is written through the domain modules, never raw SQL.** The status machines,
version counters, clearance filters and audit events are the behaviour being
demonstrated; bypassing them would seed a state the application itself cannot produce.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import sys

# `meridian` is a local package, not an installed one, and Python puts the *script's*
# directory on sys.path rather than the working directory — so running this from the
# repository root still fails without help.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from callosum import store
from meridian import agenda, board_members, commitments, decisions, meetings, minutes, packs

WS = store.DEFAULT_WORKSPACE_ID

# Sensitivity 4 = restricted. Used to prove withholding, so it must be a document a
# founder can see and an investor cannot.
CONFIDENTIAL_TITLE = "compensation_review_CONFIDENTIAL"


def _utc(y: int, m: int, d: int, hh: int, mm: int = 0) -> dt.datetime:
    return dt.datetime(y, m, d, hh, mm, tzinfo=dt.timezone.utc)


def _existing_meeting_titles() -> set[str]:
    return {m.title for m in meetings.list_meetings(workspace_id=WS)}


def _documents() -> dict[str, str]:
    """Title → id, for the documents already ingested into the core schema."""
    with store.pg(WS) as conn:
        rows = conn.execute("SELECT id, title FROM document").fetchall()
    return {r["title"]: str(r["id"]) for r in rows}


def main() -> int:
    if "Board Meeting 12" in _existing_meeting_titles():
        print("Board demo data already present — nothing to do.")
        return 0

    docs = _documents()
    if not docs:
        print(
            "No documents found. Ingest the corpus first:\n"
            "  .venv/bin/callosum ingest-doc data/demo/board_meeting_12_transcript.txt "
            "--type transcript --sensitivity 1",
            file=sys.stderr,
        )
        return 1

    # --- the board ---------------------------------------------------------
    raj = board_members.create_member(
        "Raj Malhotra", "director", workspace_id=WS, organization="Callosum Inc",
        contact_email="raj@callosum.inc",
    )
    priya = board_members.create_member(
        "Priya Nair", "director", workspace_id=WS, organization="Callosum Inc",
        contact_email="priya@callosum.inc",
    )
    marcus = board_members.create_member(
        "Marcus Webb", "observer", workspace_id=WS, organization="Sequoia",
        contact_email="marcus@sequoia.com",
    )
    print(f"  board members  3")

    # --- Board Meeting 12 — the rejection -----------------------------------
    m12 = meetings.create_meeting(
        "Board Meeting 12", workspace_id=WS,
        scheduled_start=_utc(2026, 3, 11, 10), scheduled_end=_utc(2026, 3, 11, 12),
        location="HQ — Room A",
    )
    # Agenda first: `agenda` locks at `in_progress`, which is the domain saying an
    # agenda is settled before a meeting starts rather than edited during it.
    a12 = agenda.create_agenda_item(
        m12.id, "Pricing Model B — margin analysis", workspace_id=WS,
        description="Usage-based tier; gross-margin impact.", duration_minutes=30,
        presenter="Priya Nair",
    )
    agenda.create_agenda_item(
        m12.id, "Runway review", workspace_id=WS, duration_minutes=15, presenter="Priya Nair"
    )
    for s_ in ("scheduled", "in_progress"):
        m12 = meetings.transition_status(m12.id, s_, expected_version=m12.version, workspace_id=WS)

    d_reject = decisions.create_decision(
        m12.id, "Reject Pricing Model B", workspace_id=WS, agenda_item_id=a12.id,
        rationale="Margin impact unacceptable in its current form.",
    )
    decisions.record_stance(d_reject.id, "Raj Malhotra", "APPROVED", workspace_id=WS,
                            comment="We're not doing Model B.")
    decisions.record_stance(d_reject.id, "Priya Nair", "SUPPORTED", workspace_id=WS,
                            comment="I can't recommend it in its current form.")
    decisions.record_stance(d_reject.id, "Marcus Webb", "OPPOSED", workspace_id=WS,
                            comment="I want to push back on that framing.")
    d_reject = decisions.get_decision(d_reject.id, workspace_id=WS)
    d_reject = decisions.transition_decision_status(
        d_reject.id, "approved", expected_version=d_reject.version, workspace_id=WS
    )
    m12 = meetings.transition_status(m12.id, "completed", expected_version=m12.version, workspace_id=WS)
    print("  Board Meeting 12  agenda 2 · 1 decision · 3 stances")

    # --- Board Meeting 13 — the reversal ------------------------------------
    m13 = meetings.create_meeting(
        "Board Meeting 13", workspace_id=WS,
        scheduled_start=_utc(2026, 6, 10, 10), scheduled_end=_utc(2026, 6, 10, 12),
        location="HQ — Room A",
    )
    a13 = agenda.create_agenda_item(
        m13.id, "Usage-based pricing — revisit", workspace_id=WS,
        description="Reversal of the March decision.", duration_minutes=25, presenter="Raj Malhotra",
    )
    for s_ in ("scheduled", "in_progress"):
        m13 = meetings.transition_status(m13.id, s_, expected_version=m13.version, workspace_id=WS)

    d_adopt = decisions.create_decision(
        m13.id, "Adopt Usage-Based Pricing", workspace_id=WS, agenda_item_id=a13.id,
        rationale="Reversing the March decision; usage-based is the forward model.",
    )
    decisions.record_stance(d_adopt.id, "Raj Malhotra", "APPROVED", workspace_id=WS,
                            comment="I'm comfortable reversing our decision from March.")
    decisions.record_stance(d_adopt.id, "Priya Nair", "SUPPORTED", workspace_id=WS)
    d_adopt = decisions.get_decision(d_adopt.id, workspace_id=WS)
    d_adopt = decisions.transition_decision_status(
        d_adopt.id, "approved", expected_version=d_adopt.version, workspace_id=WS
    )

    # The formal instrument, and the commitment it produced.
    from meridian import resolutions as resolutions_mod

    r = resolutions_mod.create_resolution(
        d_adopt.id, "Resolution 2026-06 — Usage-Based Pricing",
        "RESOLVED THAT the Company adopt usage-based pricing with effect from Q3 FY27.",
        workspace_id=WS,
    )
    resolutions_mod.record_vote(r.id, raj.id, "for", workspace_id=WS)
    resolutions_mod.record_vote(r.id, priya.id, "for", workspace_id=WS)
    resolutions_mod.record_vote(r.id, marcus.id, "abstain", workspace_id=WS)
    r = resolutions_mod.get_resolution(r.id, workspace_id=WS)
    resolutions_mod.transition_resolution(r.id, "adopted", expected_version=r.version, workspace_id=WS)

    c = commitments.create_commitment(
        d_adopt.id, "Bring the revised FY27 forecast", priya.id, workspace_id=WS,
        detail="Reflecting usage-based pricing.", due_date=dt.date(2026, 9, 30),
        accountable_team="Finance",
    )
    commitments.record_update(
        c.id, "Draft model circulated to the audit committee.", expected_version=c.version,
        new_status="in_progress", workspace_id=WS, author_board_member_id=priya.id,
    )
    m13 = meetings.transition_status(m13.id, "completed", expected_version=m13.version, workspace_id=WS)
    print("  Board Meeting 13  1 decision · 1 resolution (3 votes) · 1 commitment")

    # --- Board Meeting 14 — the pack that demonstrates withholding ----------
    m14 = meetings.create_meeting(
        "Board Meeting 14", workspace_id=WS,
        scheduled_start=_utc(2026, 11, 18, 10), scheduled_end=_utc(2026, 11, 18, 12),
        location="Zoom",
    )
    agenda.create_agenda_item(
        m14.id, "November billing outage — remediation", workspace_id=WS,
        description="Forty-one minutes of failed charges; deploy-window ownership.",
        duration_minutes=20, presenter="Raj Malhotra",
    )
    agenda.create_agenda_item(
        m14.id, "Executive compensation review", workspace_id=WS,
        duration_minutes=20, presenter="Priya Nair",
    )
    m14 = meetings.transition_status(m14.id, "scheduled", expected_version=m14.version, workspace_id=WS)

    pack = packs.create_pack(m14.id, "Board Meeting 14 — pack", workspace_id=WS)
    # Two public documents and one restricted one. The restricted item is the point:
    # a founder sees three items, an investor sees two, renumbered from 1, with no
    # gap and no count to subtract from.
    ordered = [
        "board_meeting_14_transcript",
        "finance_fy27_forecast",
        CONFIDENTIAL_TITLE,
    ]
    added = 0
    for title in ordered:
        doc_id = docs.get(title)
        if doc_id is None:
            continue
        packs.add_pack_item(pack.id, doc_id, workspace_id=WS)
        added += 1
    fresh = packs.get_pack(pack.id, workspace_id=WS, clearance=4)
    packs.publish_pack(pack.id, expected_version=fresh.version, workspace_id=WS, clearance=4)
    print(f"  Board Meeting 14  agenda 2 · pack published with {added} items")

    # --- Minutes on a meeting that has actually happened --------------------
    mins = minutes.create_minutes(
        m13.id,
        "The board reversed its March decision and adopted usage-based pricing. "
        "Priya Nair owns the revised FY27 forecast.",
        workspace_id=WS,
    )
    minutes.finalise_minutes(mins.id, expected_version=mins.version, workspace_id=WS)
    print("  minutes           1 finalised (Board Meeting 13)")

    print("\nSeeded. Every row was written through the domain modules, so the status")
    print("machines, version counters and audit events all hold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
