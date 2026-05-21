import json

from packages.agent_runtime import (
    Heartbeat,
    Question,
    StatusUpdate,
    TaskAssignment,
    new_envelope,
)


def test_task_assignment_carries_required_fields():
    task = TaskAssignment(task_id="t-1", description="implement X")
    assert task.kind == "task_assignment"
    assert task.task_id == "t-1"
    assert task.retry_budget == 3
    assert task.inputs == {}


def test_status_update_accepts_terminal_states():
    for status in ["accepted", "in_progress", "blocked", "completed", "failed"]:
        upd = StatusUpdate(task_id="t-1", status=status)
        assert upd.status == status


def test_new_envelope_populates_id_and_timestamp():
    payload = Heartbeat()
    env = new_envelope(
        from_agent="alice",
        to_agent="bob",
        project_id="proj-1",
        payload=payload,
    )
    assert env.id and len(env.id) > 16
    assert env.from_agent == "alice"
    assert env.to_agent == "bob"
    assert env.project_id == "proj-1"
    assert env.payload is payload
    assert env.in_reply_to is None
    assert "T" in env.created_at  # ISO format


def test_envelope_can_be_serialized_for_audit_log():
    env = new_envelope(
        from_agent="pm",
        to_agent="backend_dev",
        project_id="proj-1",
        payload=Question(topic="schema", context="what's the User.email constraint?"),
    )
    blob = {
        "id": env.id,
        "from_agent": env.from_agent,
        "to_agent": env.to_agent,
        "kind": env.payload.kind,
        "topic": env.payload.topic,
    }
    encoded = json.dumps(blob)
    assert "schema" in encoded


def test_in_reply_to_link():
    original = new_envelope(
        from_agent="qa",
        to_agent="backend_dev",
        project_id="proj-1",
        payload=Question(topic="endpoint shape"),
    )
    reply_env = new_envelope(
        from_agent="backend_dev",
        to_agent="qa",
        project_id="proj-1",
        payload=Heartbeat(),
        in_reply_to=original.id,
    )
    assert reply_env.in_reply_to == original.id
