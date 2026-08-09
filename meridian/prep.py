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
        overdue = conn.execute(
            """
            SELECT id, title, owner_name, due_date
              FROM commitment
             WHERE workspace_id = %s AND status = 'open' AND due_date < NOW()
             ORDER BY due_date ASC
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
        decisions = conn.execute(
            """
            SELECT id, title, category
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
                    "reason": f"Unresolved {d['category']} decision requiring board alignment",
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
