from pathlib import Path

import pytest

from packages.agent_runtime import (
    DEFAULT_OWNERSHIP,
    OwnershipPolicy,
    OwnershipViolation,
    Workspace,
)


def test_write_and_read_roundtrip(tmp_path: Path):
    ws = Workspace(project_id="p1", root=tmp_path)
    ws.write(
        agent_name="alice",
        agent_role="backend_developer",
        path="backend/app/models/user.py",
        content="class User: pass\n",
        message="add user model",
    )
    assert ws.read_text("backend/app/models/user.py") == "class User: pass\n"
    assert ws.exists("backend/app/models/user.py")


def test_commits_record_authorship(tmp_path: Path):
    ws = Workspace(project_id="p1", root=tmp_path)
    ws.write(
        agent_name="alice",
        agent_role="backend_developer",
        path="backend/app/main.py",
        content="x = 1",
        message="bootstrap",
    )
    ws.write(
        agent_name="bob",
        agent_role="qa",
        path="tests/test_main.py",
        content="def test(): pass",
        message="seed test",
    )

    commits = ws.commits()
    assert [c.agent_name for c in commits] == ["alice", "bob"]
    assert [c.paths[0] for c in commits] == ["backend/app/main.py", "tests/test_main.py"]
    assert ws.commits_by_agent("alice")[0].message == "bootstrap"
    assert ws.commits_touching("tests/test_main.py")[0].agent_role == "qa"


def test_ownership_blocks_writes_outside_role_scope(tmp_path: Path):
    ws = Workspace(project_id="p1", root=tmp_path, policy=DEFAULT_OWNERSHIP)
    with pytest.raises(OwnershipViolation) as exc:
        ws.write(
            agent_name="alice",
            agent_role="qa",
            path="backend/app/main.py",
            content="",
            message="rogue write",
        )
    assert exc.value.agent_role == "qa"
    assert exc.value.path == "backend/app/main.py"


def test_ownership_allows_writes_within_role_scope(tmp_path: Path):
    ws = Workspace(project_id="p1", root=tmp_path, policy=DEFAULT_OWNERSHIP)
    ws.write(
        agent_name="alice",
        agent_role="qa",
        path="tests/test_user.py",
        content="def test(): pass",
        message="ok",
    )
    assert ws.exists("tests/test_user.py")


def test_empty_policy_allows_everything(tmp_path: Path):
    ws = Workspace(project_id="p1", root=tmp_path, policy=OwnershipPolicy())
    ws.write(
        agent_name="alice",
        agent_role="anything",
        path="random/file.txt",
        content="x",
        message="x",
    )
    assert ws.exists("random/file.txt")


def test_list_files_filters_with_glob(tmp_path: Path):
    ws = Workspace(project_id="p1", root=tmp_path)
    for path in ["a.py", "sub/b.py", "sub/c.md"]:
        ws.write(
            agent_name="x",
            agent_role="anything",
            path=path,
            content="x",
            message="x",
        )
    py_files = ws.list_files("**/*.py")
    assert py_files == ["a.py", "sub/b.py"]
