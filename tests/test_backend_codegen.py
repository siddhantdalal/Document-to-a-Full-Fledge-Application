import json
import py_compile
from pathlib import Path

from packages.generator.backend import (
    endpoint_kind,
    group_endpoints,
    render_auth_router,
    render_model,
    render_router,
    write_backend,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_spec() -> dict:
    return json.loads((FIXTURES / "todo_app.spec.json").read_text())


def test_render_model_emits_class_and_fields(tmp_path: Path):
    entity = {
        "name": "Todo",
        "fields": [
            {"name": "title", "type": "string", "required": True},
            {"name": "description", "type": "string", "required": False},
            {"name": "completed", "type": "boolean", "required": True},
        ],
    }
    src = render_model(entity)
    assert "class Todo(SQLModel, table=True):" in src
    assert "title: str" in src
    assert "description: str | None = None" in src
    assert "completed: bool" in src
    assert "id: int | None = Field(default=None, primary_key=True)" in src

    out = tmp_path / "todo.py"
    out.write_text(src)
    py_compile.compile(str(out), doraise=True)


def test_render_model_unique_field():
    src = render_model(
        {
            "name": "User",
            "fields": [
                {"name": "email", "type": "string", "required": True, "unique": True},
            ],
        }
    )
    assert "email: str = Field(unique=True)" in src


def test_render_model_datetime_import():
    src = render_model(
        {
            "name": "Event",
            "fields": [{"name": "occurred_at", "type": "datetime", "required": True}],
        }
    )
    assert "from datetime import datetime" in src
    assert "occurred_at: datetime" in src


def test_group_endpoints_by_first_segment():
    spec = _load_spec()
    groups = group_endpoints(spec["endpoints"])
    assert set(groups.keys()) == {"signup", "login", "todos"}
    assert len(groups["todos"]) == 4


def test_endpoint_kind_detects_crud_patterns():
    assert endpoint_kind({"method": "GET", "path": "/todos"}, "todos") == "list"
    assert endpoint_kind({"method": "POST", "path": "/todos"}, "todos") == "create"
    assert endpoint_kind({"method": "GET", "path": "/todos/{id}"}, "todos") == "get_one"
    assert endpoint_kind({"method": "PATCH", "path": "/todos/{id}"}, "todos") == "update"
    assert endpoint_kind({"method": "DELETE", "path": "/todos/{id}"}, "todos") == "delete"
    assert endpoint_kind({"method": "DELETE", "path": "/todos"}, "todos") == "stub"
    assert endpoint_kind({"method": "GET", "path": "/users/{id}/promote"}, "users") == "stub"


def test_render_router_for_todos_compiles(tmp_path: Path):
    spec = _load_spec()
    todo_endpoints = [ep for ep in spec["endpoints"] if ep["path"].startswith("/todos")]
    src = render_router("todos", todo_endpoints, spec)
    assert "from app.models.todo import Todo" in src
    assert "from app.auth import current_user_id" in src
    assert 'router = APIRouter(prefix="/todos", tags=["todos"])' in src
    assert "def list_todos(" in src
    assert "def create_todo(" in src
    assert "def update_todo(" in src
    assert "def delete_todo(" in src

    out = tmp_path / "todos.py"
    out.write_text(src)
    py_compile.compile(str(out), doraise=True)


def test_render_auth_router_compiles_when_jwt_and_user_present(tmp_path: Path):
    spec = _load_spec()
    src = render_auth_router(spec)
    assert src is not None
    assert "def signup(" in src
    assert "def login(" in src
    assert "OAuth2PasswordRequestForm" in src
    out = tmp_path / "auth.py"
    out.write_text(src)
    py_compile.compile(str(out), doraise=True)


def test_render_auth_router_returns_none_without_jwt():
    spec = _load_spec()
    spec["auth"] = {"type": "none"}
    assert render_auth_router(spec) is None


def test_write_backend_produces_compilable_files(tmp_path: Path):
    spec = _load_spec()
    project_dir = tmp_path / "out"
    (project_dir / "backend" / "app").mkdir(parents=True)
    (project_dir / "backend" / "app" / "main.py").write_text(
        "from app.db import init_db\n# GENERATED:IMPORTS\n# GENERATED:ROUTERS\n"
    )

    groups = write_backend(spec, project_dir)
    assert "auth" in groups
    assert "todos" in groups

    assert (project_dir / "backend" / "app" / "models" / "user.py").exists()
    assert (project_dir / "backend" / "app" / "models" / "todo.py").exists()
    assert (project_dir / "backend" / "app" / "routers" / "auth.py").exists()
    assert (project_dir / "backend" / "app" / "routers" / "todos.py").exists()

    for py_file in (project_dir / "backend").rglob("*.py"):
        py_compile.compile(str(py_file), doraise=True)

    main_text = (project_dir / "backend" / "app" / "main.py").read_text()
    assert "from app.routers import" in main_text
    assert "app.include_router(todos.router)" in main_text
    assert "app.include_router(auth.router)" in main_text
