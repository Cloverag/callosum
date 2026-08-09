"""Seeds the unfinished business that `/prepare` is built to surface.

`seed_demo_board.py` produces a board whose work is *done*: every decision approved,
its one commitment on track and not yet due. That is the right shape for demonstrating
decisions, resolutions and withholding, and the wrong shape for demonstrating meeting
preparation — which reads exactly the things a settled board does not have. On the
seeded corpus `/prepare` renders one open commitment, no overdue work and no undecided
proposal, so the surface is correct and nearly empty.

This adds three rows, chosen to exercise the three states the flow distinguishes:

  * a commitment **overdue** — renders critical, and dates the statement
  * a second commitment overdue by longer — proves the ordering is by due date, not
    by insertion, which a single overdue row cannot show
  * a decision left at **proposed** — the only genuinely open decision state, and the
    one that produces an agenda suggestion from the decision side rather than the
    commitment side

Written through the domain modules like `seed_demo_board.py`, and for the same reason:
status machines, version counters and audit events all hold. Seeding by raw SQL would
produce a state the application itself cannot reach, and a demo resting on an
unreachable state is worth nothing.

**These are seeded facts, not measured ones.** They are fictional board business for a
fictional company, exactly as the rest of `data/demo/` is. What must stay true is that
every figure the product *derives* from them is derived and not invented — the counts,
the overdue flags and the agenda suggestions are all computed from these rows at read
time, never written alongside them.

Idempotent: re-running finds its own marker and does nothing.

    .venv/bin/python scripts/seed_demo_prep.py
"""

from __future__ import annotations

import datetime as dt
import pathlib
import sys

# `meridian` is a local package, not an installed one, and Python puts the *script's*
# directory on sys.path rather than the working directory.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from callosum import store
from meridian import board_members, commitments, decisions, meetings

WS = store.DEFAULT_WORKSPACE_ID

# The marker. Re-running is a no-op once this exists.
MARKER_TITLE = "Confirm the Series B data room index"


def _find_meeting(title: str) -> object | None:
    return next((m for m in meetings.list_meetings(workspace_id=WS) if m.title == title), None)


def _find_member(name: str) -> object | None:
    return next(
        (m for m in board_members.list_members(workspace_id=WS, active=None) if m.full_name == name),
        None,
    )


def main() -> int:
    # A commitment hangs off a decision, so the approved decisions from
    # seed_demo_board.py have to exist before this can add anything to them.
    m13 = _find_meeting("Board Meeting 13")
    q3 = _find_meeting("Q3 Board Meeting")
    if m13 is None or q3 is None:
        print(
            "Board demo data missing. Run scripts/seed_demo_board.py first.",
            file=sys.stderr,
        )
        return 1

    existing = commitments.list_commitments(workspace_id=WS)
    if any(c.title == MARKER_TITLE for c in existing):
        print("Preparation demo data already present — nothing to do.")
        return 0

    priya = _find_member("Priya Nair")
    raj = _find_member("Raj Malhotra")
    if priya is None or raj is None:
        print("Board directory missing. Run scripts/seed_demo_board.py first.", file=sys.stderr)
        return 1

    d_adopt = next(
        (d for d in decisions.list_decisions(m13.id, workspace_id=WS) if d.status == "approved"),
        None,
    )
    if d_adopt is None:
        print("No approved decision on Board Meeting 13 to hang a commitment on.", file=sys.stderr)
        return 1

    # --- two overdue commitments -------------------------------------------
    # Fixed dates, not offsets from today. An offset would make the seeded state drift
    # with the clock and the screenshots disagree with the database a week later.
    c1 = commitments.create_commitment(
        d_adopt.id,
        MARKER_TITLE,
        priya.id,
        workspace_id=WS,
        detail="Investor diligence index, ahead of the Series B kickoff.",
        due_date=dt.date(2026, 7, 15),
        accountable_team="Finance",
    )
    commitments.record_update(
        c1.id,
        "Index drafted; three sections still awaiting sign-off.",
        expected_version=c1.version,
        new_status="in_progress",
        workspace_id=WS,
        author_board_member_id=priya.id,
    )

    c2 = commitments.create_commitment(
        d_adopt.id,
        "Publish the usage-based pricing migration plan",
        raj.id,
        workspace_id=WS,
        detail="Customer-facing timeline for existing contracts.",
        due_date=dt.date(2026, 6, 30),
        accountable_team="Product",
    )
    commitments.record_update(
        c2.id,
        "Blocked pending the revised FY27 forecast.",
        expected_version=c2.version,
        new_status="blocked",
        workspace_id=WS,
        author_board_member_id=raj.id,
    )

    # --- one decision left proposed ----------------------------------------
    # On the Q3 meeting, which is the one `/prepare` selects: an undecided proposal on
    # the meeting being prepared is the realistic case, and it exercises the decision
    # side of the agenda suggestion.
    d_open = decisions.create_decision(
        q3.id,
        "Increase the engineering hiring plan for FY27",
        workspace_id=WS,
        rationale="Two of the three roles agreed in June remain unfilled.",
    )
    decisions.record_stance(
        d_open.id, "Priya Nair", "SUPPORTED", workspace_id=WS,
        comment="Supportable if the forecast holds.",
    )

    print("Seeded preparation demo data:")
    print(f"  commitment  overdue 2026-07-15  in_progress  {c1.title}")
    print(f"  commitment  overdue 2026-06-30  blocked      {c2.title}")
    print(f"  decision    proposed                          {d_open.title}")
    print("\n/prepare should now show 3 signals, 2 of them critical, and 3 suggestions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
