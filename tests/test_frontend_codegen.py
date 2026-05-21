import json
from pathlib import Path

from packages.generator.frontend import (
    render_api_client,
    render_auth_client,
    render_page,
    render_types,
    write_frontend,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_spec() -> dict:
    return json.loads((FIXTURES / "todo_app.spec.json").read_text())


def test_render_types_emits_interfaces_per_entity():
    spec = _load_spec()
    src = render_types(spec)
    assert "export interface User {" in src
    assert "export interface Todo {" in src
    assert "title: string;" in src
    assert "description?: string;" in src
    assert "completed: boolean;" in src


def test_render_api_client_for_todos_uses_entity_type():
    spec = _load_spec()
    todo_endpoints = [ep for ep in spec["endpoints"] if ep["path"].startswith("/todos")]
    src = render_api_client("todos", todo_endpoints, spec)
    assert 'import type { Todo } from "./types";' in src
    assert "listTodos" in src
    assert "createTodo" in src
    assert "updateTodo" in src
    assert "deleteTodo" in src
    assert "api<Todo[]>" in src


def test_render_auth_client_exposes_login_and_signup():
    src = render_auth_client()
    assert "export const login" in src
    assert "export const signup" in src
    assert "OAuth2" not in src


def test_render_page_uses_pascal_class_name():
    src = render_page({"name": "Login", "route": "/login"})
    assert "export function Login()" in src
    assert "<h1" in src


def test_write_frontend_writes_pages_and_api_files(tmp_path: Path):
    spec = _load_spec()
    project_dir = tmp_path / "out"
    fe_src = project_dir / "frontend" / "src"
    fe_src.mkdir(parents=True)
    (fe_src / "App.tsx").write_text(
        'import { Routes } from "react-router-dom";\n'
        "// GENERATED:IMPORTS\n\n"
        "export function App() {\n"
        "  return (\n"
        "    <Routes>\n"
        "      {/* GENERATED:ROUTES */}\n"
        "    </Routes>\n"
        "  );\n"
        "}\n"
    )

    result = write_frontend(spec, project_dir)
    assert "Login" in result["pages"]
    assert "Signup" in result["pages"]
    assert "Todos" in result["pages"]
    assert "auth" in result["api_groups"]
    assert "todos" in result["api_groups"]

    assert (fe_src / "routes" / "Login.tsx").exists()
    assert (fe_src / "routes" / "Todos.tsx").exists()
    assert (fe_src / "lib" / "types.ts").exists()
    assert (fe_src / "lib" / "todos.ts").exists()
    assert (fe_src / "lib" / "auth.ts").exists()

    app_text = (fe_src / "App.tsx").read_text()
    assert 'import { Route, Routes } from "react-router-dom";' in app_text
    assert 'import { Login } from "./routes/Login";' in app_text
    assert '<Route path="/login" element={<Login />} />' in app_text
    assert '<Route path="/" element={<Todos />} />' in app_text
