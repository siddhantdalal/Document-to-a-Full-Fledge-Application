from packages.agent_runtime import AgentMemory


def test_record_decision_appends_to_log():
    mem = AgentMemory()
    d = mem.record_decision(
        summary="use Postgres",
        rationale="audit retention requirement",
        related_task="t-arch-1",
    )
    assert d in mem.decisions
    assert d.related_task == "t-arch-1"
    assert d.timestamp


def test_add_and_resolve_question():
    mem = AgentMemory()
    mem.add_question("idempotency key TTL?")
    assert len(mem.open_questions) == 1
    resolved = mem.resolve_question("idempotency key TTL?")
    assert resolved is True
    assert mem.open_questions == []


def test_resolve_question_returns_false_when_not_present():
    mem = AgentMemory()
    assert mem.resolve_question("nope") is False


def test_complete_task_records_history():
    mem = AgentMemory()
    mem.complete_task("t-7", "added Account model")
    assert mem.completed_tasks[0].task_id == "t-7"


def test_to_dict_and_from_dict_roundtrip():
    mem = AgentMemory()
    mem.record_decision("use SQLite", "fits self-host")
    mem.add_question("session timeout?")
    mem.complete_task("t-1", "init")
    mem.add_note("dev started 2026-05-21")

    encoded = mem.to_dict()
    restored = AgentMemory.from_dict(encoded)
    assert restored.decisions[0].summary == "use SQLite"
    assert restored.open_questions[0].text == "session timeout?"
    assert restored.completed_tasks[0].task_id == "t-1"
    assert restored.notes == ["dev started 2026-05-21"]


def test_json_roundtrip():
    mem = AgentMemory()
    mem.add_question("q?")
    restored = AgentMemory.from_json(mem.to_json())
    assert restored.open_questions[0].text == "q?"
