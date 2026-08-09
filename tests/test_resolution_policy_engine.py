import uuid
import pytest
import psycopg
from callosum import store
from meridian import resolutions, commitments
from meridian.api import main
from fastapi.testclient import TestClient

client = TestClient(main.app)


def test_evaluate_resolution_policy_simple_majority():
    """Verify simple majority and supermajority policy evaluation."""
    res_id = str(uuid.uuid4())
    vote1 = resolutions.ResolutionVote(id=str(uuid.uuid4()), resolution_id=res_id, board_member_id=str(uuid.uuid4()), vote="for", created_at=None, updated_at=None, workspace_id="ws")
    vote2 = resolutions.ResolutionVote(id=str(uuid.uuid4()), resolution_id=res_id, board_member_id=str(uuid.uuid4()), vote="for", created_at=None, updated_at=None, workspace_id="ws")
    vote3 = resolutions.ResolutionVote(id=str(uuid.uuid4()), resolution_id=res_id, board_member_id=str(uuid.uuid4()), vote="against", created_at=None, updated_at=None, workspace_id="ws")

    res = resolutions.Resolution(
        id=res_id,
        decision_id=str(uuid.uuid4()),
        title="Test Motion",
        body="Body",
        status="draft",
        signing_state="not_applicable",
        version_no=1,
        superseded_by_id=None,
        adopted_at=None,
        version=1,
        created_at=None,
        updated_at=None,
        workspace_id="ws",
        votes=[vote1, vote2, vote3],
    )

    # 3 participants out of 5 total = 60% quorum (met)
    # 2 for vs 1 against = 66.67% > 50% (simple majority passed, 2/3 supermajority passed)
    simple_eval = resolutions.evaluate_resolution_policy(res, total_voting_members=5, policy_type=resolutions.POLICY_SIMPLE_MAJORITY, quorum_percent=50.0)
    assert simple_eval["quorum_met"] is True
    assert simple_eval["threshold_passed"] is True
    assert simple_eval["passed"] is True

    super_eval = resolutions.evaluate_resolution_policy(res, total_voting_members=5, policy_type=resolutions.POLICY_SUPERMAJORITY_TWOTHIRDS, quorum_percent=50.0)
    assert super_eval["passed"] is True

    unanimous_eval = resolutions.evaluate_resolution_policy(res, total_voting_members=5, policy_type=resolutions.POLICY_UNANIMOUS, quorum_percent=50.0)
    assert unanimous_eval["passed"] is False


def test_bridge_adopted_resolution_to_commitment():
    """Verify adopted resolution converts to an owned commitment."""
    w_id = str(uuid.uuid4())
    m_id = str(uuid.uuid4())
    d_id = str(uuid.uuid4())
    member_id = str(uuid.uuid4())

    with psycopg.connect(store.settings().postgres_dsn, row_factory=store.dict_row) as conn:
        conn.execute("INSERT INTO workspace (id, name) VALUES (%s, 'W')", (w_id,))
        conn.execute("INSERT INTO board_member (id, workspace_id, role) VALUES (%s, %s, 'director')", (member_id, w_id))
        conn.execute("INSERT INTO meeting (id, workspace_id, title, scheduled_start) VALUES (%s, %s, 'M', now())", (m_id, w_id))
        conn.execute("INSERT INTO decision (id, workspace_id, meeting_id, title) VALUES (%s, %s, %s, 'D')", (d_id, w_id, m_id))

    res = resolutions.create_resolution(d_id, "Adopted Resolution", "Body text", workspace_id=w_id)
    adopted_res = resolutions.transition_resolution(res.id, resolutions.ADOPTED, expected_version=res.version, workspace_id=w_id)

    # Convert to commitment
    comm = resolutions.bridge_resolution_to_commitment(adopted_res.id, owner_board_member_id=member_id, workspace_id=w_id)
    assert comm.title == "Adopted Resolution"
    assert comm.decision_id == d_id
    assert comm.owner_board_member_id == member_id
