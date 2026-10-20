"""Meeting Preparation & Readiness domain (Meridian P3, CP-B/E).

Owns meeting readiness evaluation, source-backed agenda item suggestions, and
permissioned pre-read publication.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from callosum import store
from callosum.store import DEFAULT_WORKSPACE_ID
from meridian import audit, commitments, meetings, packs


class MeetingPrepError(ValueError):
    """Base exception for meeting preparation operations."""


def _overdue_commitments(workspace_id: str) -> list[commitments.Commitment]:
    """Overdue by `Commitment.is_overdue`, the domain's one definition (#238).

    `today` is the UTC date, which is what the `due_date < NOW()` this replaced compared
    against on the server. Soonest due first, as `list_commitments` returns them.
    """
    today = datetime.now(timezone.utc).date()
    return [
        c for c in commitments.list_commitments(workspace_id=workspace_id, open_only=True)
        if c.is_overdue(today=today)
    ]


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

        # Count active board members (attendees)
        att_row = conn.execute(
            "SELECT COUNT(*) AS n FROM board_member WHERE workspace_id = %s AND active = TRUE",
            (workspace_id,),
        ).fetchone()
        attendee_count = int(att_row["n"]) if att_row else 0

    overdue_commitments_count = len(_overdue_commitments(workspace_id))

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
        # 1. Overdue Commitments, by the same definition readiness counts (#238). Owner
        # names come from `board_member` on this RLS-scoped connection, so an id cannot
        # resolve across a workspace boundary.
        overdue = _overdue_commitments(workspace_id)[:5]
        owner_names = {
            str(r["id"]): r["full_name"]
            for r in conn.execute(
                "SELECT id, full_name FROM board_member WHERE id = ANY(%s)",
                ([uuid.UUID(c.owner_board_member_id) for c in overdue],),
            ).fetchall()
        }

        for c in overdue:
            suggestions.append(
                {
                    "title": f"Review Overdue Commitment: {c.title}",
                    "reason": f"Overdue commitment assigned to {owner_names.get(c.owner_board_member_id) or 'unassigned'}",
                    "source": {"kind": "commitment", "id": c.id, "label": c.title},
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
    """Publishes the latest board pack for pre-read distribution and logs an audit event.

    Publishing an already-published pack is a no-op that records nothing.
    """
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
             FOR UPDATE
            """,
            (m_uuid,),
        ).fetchone()

        if not pack_row:
            raise MeetingPrepError(f"No board pack exists for meeting {meeting_id}")

        pack_id = pack_row["id"]

        # Already published: nothing happens, so nothing is recorded (`rules.md` §2, the
        # trail records only events that happened). This is a no-op rather than a refusal
        # because the response is true as it stands — the pack IS published at this
        # version — and a client retrying after a dropped response should get that
        # answer, not an error for an operation that had already succeeded. The row lock
        # above makes two concurrent calls serialise, so exactly one sees `draft`.
        if pack_row["status"] != "draft":
            return {
                "meeting_id": str(m_uuid),
                "pack_id": str(pack_id),
                "version_no": pack_row["version_no"],
                "status": pack_row["status"],
            }

        conn.execute(
            """
            UPDATE board_pack
               SET status = 'published', published_at = NOW(),
                   version = version + 1, updated_at = NOW()
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
