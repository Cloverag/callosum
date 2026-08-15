"""Meeting Preparation & Readiness domain (Meridian P3, CP-B/E).

Owns meeting readiness evaluation, source-backed agenda item suggestions, and
permissioned pre-read publication.
"""

import uuid
from typing import Any

from callosum import store
from callosum.store import DEFAULT_WORKSPACE_ID
from meridian import audit, meetings, packs


class MeetingPrepError(ValueError):
    """Base exception for meeting preparation operations."""


def get_meeting_readiness(
    meeting_id: uuid.UUID | str, *, workspace_id: str = DEFAULT_WORKSPACE_ID
) -> dict[str, Any]:
    """Computes verifiable meeting readiness metrics for a given meeting."""
    m_uuid = uuid.UUID(str(meeting_id))
    meeting = meetings.get_meeting(str(m_uuid), workspace_id=workspace_id)

    with store.pg(workspace_id) as conn:
        # Count agenda items
        agenda_row = conn.execute(
            "SELECT COUNT(*) AS n FROM agenda_item WHERE meeting_id = %s",
            (m_uuid,),
        ).fetchone()
        agenda_count = int(agenda_row["n"]) if agenda_row else 0

        # Check published board pack
        pack_row = conn.execute(
            """
            SELECT id, version_no, status, published_at
              FROM board_pack
             WHERE meeting_id = %s AND status = 'published'
             ORDER BY version_no DESC
             LIMIT 1
            """,
            (m_uuid,),
        ).fetchone()

        # Count open/proposed decisions
        dec_row = conn.execute(
            """
            SELECT COUNT(*) AS n
              FROM decision
             WHERE workspace_id = %s AND status IN ('proposed', 'open')
            """,
            (workspace_id,),
        ).fetchone()
        open_decisions_count = int(dec_row["n"]) if dec_row else 0

        # Count overdue commitments
        com_row = conn.execute(
            """
            SELECT COUNT(*) AS n
              FROM commitment
             WHERE workspace_id = %s AND status = 'open' AND due_date < NOW()
            """,
            (workspace_id,),
        ).fetchone()
        overdue_commitments_count = int(com_row["n"]) if com_row else 0

        # Count active board members (attendees)
        att_row = conn.execute(
            "SELECT COUNT(*) AS n FROM board_member WHERE workspace_id = %s AND active = TRUE",
            (workspace_id,),
        ).fetchone()
        attendee_count = int(att_row["n"]) if att_row else 0

    return {
        "meeting_id": str(meeting.id),
        "meeting_title": meeting.title,
        "status": meeting.status,
        "scheduled_start": meeting.scheduled_start.isoformat() if meeting.scheduled_start else None,
        "agenda_count": agenda_count,
        "has_published_pack": pack_row is not None,
        "pack_version": pack_row["version_no"] if pack_row else None,
        "open_decisions_count": open_decisions_count,
        "overdue_commitments_count": overdue_commitments_count,
        "attendee_count": attendee_count,
    }


def get_agenda_suggestions(
    meeting_id: uuid.UUID | str, *, workspace_id: str = DEFAULT_WORKSPACE_ID
) -> list[dict[str, Any]]:
    """Derives source-backed agenda item suggestions from unresolved state."""
    m_uuid = uuid.UUID(str(meeting_id))
    # Ensure meeting exists in workspace
    _ = meetings.get_meeting(str(m_uuid), workspace_id=workspace_id)

    suggestions: list[dict[str, Any]] = []

    with store.pg(workspace_id) as conn:
        # 1. Overdue Commitments
        # `commitment` has no `owner_name`; it has `owner_board_member_id`, and the name
        # lives on `board_member`. The previous query selected `owner_name` directly and
        # therefore raised `UndefinedColumn` on every call — see the module note in
        # `meridian/api/prep.py` about why that surfaced as a 404.
        #
        # LEFT JOIN because an unowned commitment is a legitimate state, and the caller
        # below already renders `owner_name or 'unassigned'`. The join is on the composite
        # `(id, workspace_id)`, matching the tenant-scoped foreign keys from `0019`, so it
        # cannot resolve a name across a workspace boundary.
        overdue = conn.execute(
            """
            SELECT c.id, c.title, bm.full_name AS owner_name, c.due_date
              FROM commitment c
              LEFT JOIN board_member bm
                     ON bm.id = c.owner_board_member_id
                    AND bm.workspace_id = c.workspace_id
             WHERE c.workspace_id = %s AND c.status = 'open' AND c.due_date < NOW()
             ORDER BY c.due_date ASC
             LIMIT 5
            """,
            (workspace_id,),
        ).fetchall()

        for c in overdue:
            suggestions.append(
                {
                    "title": f"Review Overdue Commitment: {c['title']}",
                    "reason": f"Overdue commitment assigned to {c['owner_name'] or 'unassigned'}",
                    "source": {"kind": "commitment", "id": str(c["id"]), "label": c["title"]},
                    "suggested_duration_minutes": 10,
                }
            )

        # 2. Open/Proposed Decisions
        # `decision` has no `category` column and never has — the table is
        # (id, meeting_id, agenda_item_id, title, rationale, status, superseded_by_id,
        # version, created_at, updated_at, workspace_id). `status` is the real
        # discriminator and is what the reason now names.
        #
        # Substituting a real field rather than inventing a category: §2 forbids
        # rendering a value that has no source, and a category nobody records is
        # exactly that.
        decisions = conn.execute(
            """
            SELECT id, title, status
              FROM decision
             WHERE workspace_id = %s AND status IN ('proposed', 'open')
             ORDER BY created_at ASC
             LIMIT 5
            """,
            (workspace_id,),
        ).fetchall()

        for d in decisions:
            suggestions.append(
                {
                    "title": f"Decision: {d['title']}",
                    "reason": f"Unresolved decision ({d['status']}) requiring board alignment",
                    "source": {"kind": "decision", "id": str(d["id"]), "label": d["title"]},
                    "suggested_duration_minutes": 15,
                }
            )

    return suggestions


def publish_preread(
    meeting_id: uuid.UUID | str,
    *,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    actor_id: str | None = None,
) -> dict[str, Any]:
    """Publishes the latest board pack for pre-read distribution and logs an audit event."""
    m_uuid = uuid.UUID(str(meeting_id))
    meeting = meetings.get_meeting(str(m_uuid), workspace_id=workspace_id)

    with store.pg(workspace_id) as conn:
        pack_row = conn.execute(
            """
            SELECT id, version_no, status
              FROM board_pack
             WHERE meeting_id = %s AND status != 'archived'
             ORDER BY version_no DESC
             LIMIT 1
            """,
            (m_uuid,),
        ).fetchone()

        if not pack_row:
            raise MeetingPrepError(f"No board pack exists for meeting {meeting_id}")

        pack_id = pack_row["id"]
        # Update pack status to published if draft
        if pack_row["status"] == "draft":
            conn.execute(
                """
                UPDATE board_pack
                   SET status = 'published', published_at = NOW()
                 WHERE id = %s
                """,
                (pack_id,),
            )

        # Record audit event
        audit.record_audit_event(
            conn,
            aggregate_type="board_pack",
            aggregate_id=pack_id,
            action="published",
            actor_principal_id=actor_id,
            payload={"meeting_id": str(m_uuid), "version_no": pack_row["version_no"]},
            workspace_id=workspace_id,
        )

    return {
        "meeting_id": str(m_uuid),
        "pack_id": str(pack_id),
        "version_no": pack_row["version_no"],
        "status": "published",
    }
