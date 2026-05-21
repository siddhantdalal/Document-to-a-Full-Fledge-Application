from collections import defaultdict
from pathlib import Path
from typing import Any

from packages.generator.naming import pascal, plural, snake

_PY_TYPE = {
    "string": "str",
    "integer": "int",
    "float": "float",
    "boolean": "bool",
    "datetime": "datetime",
    "json": "dict[str, Any]",
}

_AUTH_PATHS = {"/signup", "/login"}


def render_model(entity: dict[str, Any]) -> str:
    cls = pascal(entity["name"])
    fields = entity["fields"]

    extras: list[str] = []
    if any(f["type"] == "datetime" for f in fields):
        extras.append("from datetime import datetime")
    if any(f["type"] == "json" for f in fields):
        extras.append("from typing import Any")

    out: list[str] = []
    out.extend(extras)
    out.append("from sqlmodel import Field, SQLModel")
    out.append("")
    out.append("")
    out.append(f"class {cls}(SQLModel, table=True):")
    out.append("    id: int | None = Field(default=None, primary_key=True)")

    for f in fields:
        py = _PY_TYPE.get(f["type"], "str")
        required = f.get("required", True)
        unique = f.get("unique", False)
        name = snake(f["name"])
        ann = py if required else f"{py} | None"
        if unique and required:
            out.append(f"    {name}: {ann} = Field(unique=True)")
        elif unique and not required:
            out.append(f"    {name}: {ann} = Field(default=None, unique=True)")
        elif not required:
            out.append(f"    {name}: {ann} = None")
        else:
            out.append(f"    {name}: {ann}")

    return "\n".join(out) + "\n"


def write_models(spec: dict[str, Any], backend_dir: Path) -> list[Path]:
    models_dir = backend_dir / "app" / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for entity in spec["entities"]:
        path = models_dir / f"{snake(entity['name'])}.py"
        path.write_text(render_model(entity))
        written.append(path)

    init_lines = [
        f"from app.models.{snake(e['name'])} import {pascal(e['name'])}"
        for e in spec["entities"]
    ]
    init_lines.append("")
    init_lines.append(
        "__all__ = ["
        + ", ".join(repr(pascal(e["name"])) for e in spec["entities"])
        + "]"
    )
    (models_dir / "__init__.py").write_text("\n".join(init_lines) + "\n")
    return written


def group_endpoints(endpoints: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ep in endpoints:
        parts = [p for p in ep["path"].split("/") if p and not p.startswith("{")]
        group = parts[0] if parts else "root"
        groups[group].append(ep)
    return dict(groups)


def find_entity_for_group(group: str, spec: dict[str, Any]) -> dict[str, Any] | None:
    for entity in spec["entities"]:
        ent_snake = snake(entity["name"])
        if plural(ent_snake) == group or ent_snake == group:
            return entity
    return None


def endpoint_kind(ep: dict[str, Any], group: str) -> str:
    method = ep["method"].upper()
    path = ep["path"].rstrip("/")
    base = f"/{group}"
    if path == base:
        if method == "GET":
            return "list"
        if method == "POST":
            return "create"
    if path.startswith(f"{base}/") and path.count("/") == 2 and path.endswith("}"):
        if method == "GET":
            return "get_one"
        if method in ("PATCH", "PUT"):
            return "update"
        if method == "DELETE":
            return "delete"
    return "stub"


def _entity_has_user_field(entity: dict[str, Any]) -> bool:
    return any(f["name"] in ("user_id", "owner_id") for f in entity["fields"])


def _path_param_name(path: str) -> str:
    for part in path.split("/"):
        if part.startswith("{") and part.endswith("}"):
            return part[1:-1]
    return "item_id"


def _render_crud(
    ep: dict[str, Any],
    kind: str,
    entity: dict[str, Any],
    has_auth: bool,
) -> str:
    cls = pascal(entity["name"])
    sing = snake(entity["name"])
    user_scoped = has_auth and _entity_has_user_field(entity)
    user_dep = (
        "    user_id: Annotated[str, Depends(current_user_id)],\n"
        if has_auth
        else ""
    )
    user_filter = f".where({cls}.user_id == int(user_id))" if user_scoped else ""

    if kind == "list":
        return (
            f'@router.get("", response_model=list[{cls}])\n'
            f"def list_{plural(sing)}(\n"
            f"{user_dep}"
            f"    session: Annotated[Session, Depends(get_session)],\n"
            f") -> list[{cls}]:\n"
            f"    return list(session.exec(select({cls}){user_filter}).all())\n"
        )
    if kind == "create":
        set_user = f"    payload.user_id = int(user_id)\n" if user_scoped else ""
        return (
            f'@router.post("", response_model={cls})\n'
            f"def create_{sing}(\n"
            f"    payload: {cls},\n"
            f"{user_dep}"
            f"    session: Annotated[Session, Depends(get_session)],\n"
            f") -> {cls}:\n"
            f"    payload.id = None\n"
            f"{set_user}"
            f"    session.add(payload)\n"
            f"    session.commit()\n"
            f"    session.refresh(payload)\n"
            f"    return payload\n"
        )
    if kind == "get_one":
        pp = _path_param_name(ep["path"])
        scope_check = (
            f"    if not item or item.user_id != int(user_id):\n"
            if user_scoped
            else "    if not item:\n"
        )
        return (
            f'@router.get("/{{{pp}}}", response_model={cls})\n'
            f"def get_{sing}(\n"
            f"    {pp}: int,\n"
            f"{user_dep}"
            f"    session: Annotated[Session, Depends(get_session)],\n"
            f") -> {cls}:\n"
            f"    item = session.get({cls}, {pp})\n"
            f"{scope_check}"
            f'        raise HTTPException(status_code=404, detail="Not found.")\n'
            f"    return item\n"
        )
    if kind == "update":
        pp = _path_param_name(ep["path"])
        scope_check = (
            f"    if not item or item.user_id != int(user_id):\n"
            if user_scoped
            else "    if not item:\n"
        )
        return (
            f'@router.{ep["method"].lower()}("/{{{pp}}}", response_model={cls})\n'
            f"def update_{sing}(\n"
            f"    {pp}: int,\n"
            f"    payload: {cls},\n"
            f"{user_dep}"
            f"    session: Annotated[Session, Depends(get_session)],\n"
            f") -> {cls}:\n"
            f"    item = session.get({cls}, {pp})\n"
            f"{scope_check}"
            f'        raise HTTPException(status_code=404, detail="Not found.")\n'
            f"    for key, val in payload.model_dump(exclude_unset=True).items():\n"
            f'        if key != "id":\n'
            f"            setattr(item, key, val)\n"
            f"    session.add(item)\n"
            f"    session.commit()\n"
            f"    session.refresh(item)\n"
            f"    return item\n"
        )
    if kind == "delete":
        pp = _path_param_name(ep["path"])
        scope_check = (
            f"    if not item or item.user_id != int(user_id):\n"
            if user_scoped
            else "    if not item:\n"
        )
        return (
            f'@router.delete("/{{{pp}}}", status_code=204)\n'
            f"def delete_{sing}(\n"
            f"    {pp}: int,\n"
            f"{user_dep}"
            f"    session: Annotated[Session, Depends(get_session)],\n"
            f") -> None:\n"
            f"    item = session.get({cls}, {pp})\n"
            f"{scope_check}"
            f'        raise HTTPException(status_code=404, detail="Not found.")\n'
            f"    session.delete(item)\n"
            f"    session.commit()\n"
        )
    raise ValueError(f"unknown crud kind: {kind}")


def _render_stub(ep: dict[str, Any], group: str) -> str:
    method = ep["method"].lower()
    path = ep["path"]
    relative = path
    if path == f"/{group}":
        relative = ""
    elif path.startswith(f"/{group}/"):
        relative = path[len(group) + 1 :]
    fn_path_parts = [
        snake(p.strip("{}")) for p in path.split("/") if p
    ]
    fn = "_".join([method] + fn_path_parts) or method
    summary = ep.get("summary", "")
    summary_arg = f', summary="{summary}"' if summary else ""
    return (
        f'@router.{method}("{relative}"{summary_arg})\n'
        f"def {fn}() -> dict[str, str]:\n"
        f'    raise HTTPException(status_code=501, detail="Not implemented.")\n'
    )


def render_router(group: str, endpoints: list[dict[str, Any]], spec: dict[str, Any]) -> str:
    entity = find_entity_for_group(group, spec)
    has_auth_anywhere = any(ep.get("auth", False) for ep in endpoints)

    imports = [
        "from typing import Annotated",
        "",
        "from fastapi import APIRouter, Depends, HTTPException",
        "from sqlmodel import Session, select",
        "",
        "from app.db import get_session",
    ]
    if has_auth_anywhere:
        imports.append("from app.auth import current_user_id")
    if entity:
        imports.append(
            f"from app.models.{snake(entity['name'])} import {pascal(entity['name'])}"
        )

    out: list[str] = []
    out.extend(imports)
    out.append("")
    out.append("")
    out.append(f'router = APIRouter(prefix="/{group}", tags=["{group}"])')
    out.append("")

    for ep in endpoints:
        kind = endpoint_kind(ep, group)
        if kind in ("list", "create", "get_one", "update", "delete") and entity:
            body = _render_crud(ep, kind, entity, ep.get("auth", False))
        else:
            body = _render_stub(ep, group)
        out.append("")
        out.append(body.rstrip())

    return "\n".join(out) + "\n"


def render_auth_router(spec: dict[str, Any]) -> str | None:
    auth = spec.get("auth")
    if not auth or auth.get("type") != "jwt":
        return None
    user_entity = next((e for e in spec["entities"] if snake(e["name"]) == "user"), None)
    if not user_entity:
        return None
    field_names = {f["name"] for f in user_entity["fields"]}
    if "email" not in field_names or "password" not in field_names:
        return None

    return '''from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from app.auth import create_token, hash_password, verify_password
from app.db import get_session
from app.models.user import User

router = APIRouter(tags=["auth"])


@router.post("/signup")
def signup(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    existing = session.exec(select(User).where(User.email == form.username)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered.")
    user = User(email=form.username, password=hash_password(form.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    return {"access_token": create_token(str(user.id)), "token_type": "bearer"}


@router.post("/login")
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    user = session.exec(select(User).where(User.email == form.username)).first()
    if not user or not verify_password(form.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    return {"access_token": create_token(str(user.id)), "token_type": "bearer"}
'''


def write_routers(spec: dict[str, Any], backend_dir: Path) -> list[str]:
    routers_dir = backend_dir / "app" / "routers"
    routers_dir.mkdir(parents=True, exist_ok=True)

    auth_router = render_auth_router(spec)
    written_groups: list[str] = []
    if auth_router:
        (routers_dir / "auth.py").write_text(auth_router)
        written_groups.append("auth")

    endpoints = list(spec["endpoints"])
    if auth_router:
        endpoints = [ep for ep in endpoints if ep["path"] not in _AUTH_PATHS]

    for group, eps in group_endpoints(endpoints).items():
        (routers_dir / f"{group}.py").write_text(render_router(group, eps, spec))
        written_groups.append(group)

    init_lines = [f"from app.routers import {g}" for g in written_groups]
    init_lines.append("")
    init_lines.append("__all__ = [" + ", ".join(repr(g) for g in written_groups) + "]")
    (routers_dir / "__init__.py").write_text("\n".join(init_lines) + "\n")
    return written_groups


def patch_main(backend_dir: Path, router_groups: list[str]) -> None:
    main_py = backend_dir / "app" / "main.py"
    text = main_py.read_text()
    imports_line = (
        f"from app.routers import {', '.join(router_groups)}" if router_groups else ""
    )
    register_lines = "\n".join(
        f"app.include_router({g}.router)" for g in router_groups
    )
    text = text.replace("# GENERATED:IMPORTS", imports_line, 1)
    text = text.replace("# GENERATED:ROUTERS", register_lines, 1)
    text = text.replace("from app.db import init_db\n\n\n\n", "from app.db import init_db\n\n\n", 1)
    main_py.write_text(text)


def write_backend(spec: dict[str, Any], project_dir: Path) -> list[str]:
    backend_dir = project_dir / "backend"
    write_models(spec, backend_dir)
    groups = write_routers(spec, backend_dir)
    patch_main(backend_dir, groups)
    return groups
