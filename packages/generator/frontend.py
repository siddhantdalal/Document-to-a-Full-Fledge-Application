from pathlib import Path
from typing import Any

from packages.generator.backend import (
    _AUTH_PATHS,
    endpoint_kind,
    find_entity_for_group,
    group_endpoints,
)
from packages.generator.naming import pascal, plural, snake

_TS_TYPE = {
    "string": "string",
    "integer": "number",
    "float": "number",
    "boolean": "boolean",
    "datetime": "string",
    "json": "Record<string, unknown>",
}


def render_types(spec: dict[str, Any]) -> str:
    out: list[str] = []
    for entity in spec["entities"]:
        cls = pascal(entity["name"])
        out.append(f"export interface {cls} {{")
        out.append("  id?: number;")
        for f in entity["fields"]:
            ts = _TS_TYPE.get(f["type"], "string")
            sep = "" if f.get("required", True) else "?"
            out.append(f"  {snake(f['name'])}{sep}: {ts};")
        out.append("}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def _path_template(path: str) -> tuple[str, list[str]]:
    params: list[str] = []
    parts: list[str] = []
    for seg in path.split("/"):
        if seg.startswith("{") and seg.endswith("}"):
            name = seg[1:-1]
            params.append(name)
            parts.append(f"${{{name}}}")
        else:
            parts.append(seg)
    return "/".join(parts), params


def _ts_fn_name(ep: dict[str, Any], kind: str, entity: dict[str, Any] | None) -> str:
    if entity:
        sing = snake(entity["name"])
        if kind == "list":
            return "list" + pascal(plural(sing))
        if kind in ("create", "get_one", "update", "delete"):
            prefix = {"create": "create", "get_one": "get", "update": "update", "delete": "delete"}[kind]
            return prefix + pascal(sing)
    method = ep["method"].lower()
    parts = [snake(p.strip("{}")) for p in ep["path"].split("/") if p]
    return method + pascal("_".join(parts)) if parts else method + "Root"


def _render_endpoint(ep: dict[str, Any], kind: str, entity: dict[str, Any] | None) -> str:
    fn = _ts_fn_name(ep, kind, entity)
    method = ep["method"].upper()
    tpl, params = _path_template(ep["path"])
    param_args = ", ".join(f"{p}: string | number" for p in params)

    if entity and kind == "list":
        cls = pascal(entity["name"])
        return (
            f"export const {fn} = (token: string) =>\n"
            f"  api<{cls}[]>(`{tpl}`, {{ token }});"
        )
    if entity and kind == "create":
        cls = pascal(entity["name"])
        return (
            f"export const {fn} = (payload: {cls}, token: string) =>\n"
            f"  api<{cls}>(`{tpl}`, {{\n"
            f'    method: "POST",\n'
            f"    body: JSON.stringify(payload),\n"
            f"    token,\n"
            f"  }});"
        )
    if entity and kind == "get_one":
        cls = pascal(entity["name"])
        return (
            f"export const {fn} = ({param_args}, token: string) =>\n"
            f"  api<{cls}>(`{tpl}`, {{ token }});"
        )
    if entity and kind == "update":
        cls = pascal(entity["name"])
        return (
            f"export const {fn} = ({param_args}, payload: Partial<{cls}>, token: string) =>\n"
            f"  api<{cls}>(`{tpl}`, {{\n"
            f'    method: "{method}",\n'
            f"    body: JSON.stringify(payload),\n"
            f"    token,\n"
            f"  }});"
        )
    if entity and kind == "delete":
        return (
            f"export const {fn} = ({param_args}, token: string) =>\n"
            f'  api<void>(`{tpl}`, {{ method: "DELETE", token }});'
        )

    args = [*([param_args] if param_args else []), "token: string"]
    body_part = ""
    if method in ("POST", "PUT", "PATCH"):
        body_part = ", body: JSON.stringify({})"
    return (
        f"export const {fn} = ({', '.join(args)}) =>\n"
        f'  api<unknown>(`{tpl}`, {{ method: "{method}"{body_part}, token }});'
    )


def render_api_client(group: str, endpoints: list[dict[str, Any]], spec: dict[str, Any]) -> str:
    entity = find_entity_for_group(group, spec)
    out: list[str] = ['import { api } from "./api";']
    if entity:
        out.append(f'import type {{ {pascal(entity["name"])} }} from "./types";')
    out.append("")
    for ep in endpoints:
        kind = endpoint_kind(ep, group)
        out.append("")
        out.append(_render_endpoint(ep, kind, entity))
    return "\n".join(out) + "\n"


def render_auth_client() -> str:
    return '''const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

async function _form(path: string, email: string, password: string): Promise<AuthResponse> {
  const body = new URLSearchParams({ username: email, password });
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!res.ok) {
    throw new Error(`${path} failed: ${res.status}`);
  }
  return res.json() as Promise<AuthResponse>;
}

export const login = (email: string, password: string) => _form("/login", email, password);
export const signup = (email: string, password: string) => _form("/signup", email, password);
'''


def render_page(screen: dict[str, Any]) -> str:
    cls = pascal(screen["name"])
    actions = screen.get("actions") or []
    actions_block = ""
    if actions:
        items = "\n".join(f'              <li>{a}</li>' for a in actions)
        actions_block = (
            '\n          <div className="text-sm text-slate-500">\n'
            "            Actions described in the spec:\n"
            '            <ul className="list-disc pl-5 mt-1">\n'
            f"{items}\n"
            "            </ul>\n"
            "          </div>"
        )
    return f'''export function {cls}() {{
  return (
    <section className="mx-auto max-w-3xl space-y-4 p-6">
      <h1 className="text-2xl font-semibold text-slate-900">{screen["name"]}</h1>
      <p className="text-slate-600">
        Generated from the requirements document. Customize this screen.
      </p>{actions_block}
    </section>
  );
}}
'''


def write_frontend(spec: dict[str, Any], project_dir: Path) -> dict[str, list[str]]:
    fe_src = project_dir / "frontend" / "src"
    (fe_src / "lib").mkdir(parents=True, exist_ok=True)
    (fe_src / "lib" / "types.ts").write_text(render_types(spec))

    auth_present = bool(spec.get("auth") and spec["auth"].get("type") == "jwt")
    endpoints = list(spec["endpoints"])
    if auth_present:
        endpoints = [ep for ep in endpoints if ep["path"] not in _AUTH_PATHS]

    api_groups: list[str] = []
    if auth_present:
        (fe_src / "lib" / "auth.ts").write_text(render_auth_client())
        api_groups.append("auth")
    for group, eps in group_endpoints(endpoints).items():
        (fe_src / "lib" / f"{group}.ts").write_text(render_api_client(group, eps, spec))
        api_groups.append(group)

    routes_dir = fe_src / "routes"
    routes_dir.mkdir(parents=True, exist_ok=True)
    pages: list[str] = []
    for screen in spec["screens"]:
        cls = pascal(screen["name"])
        (routes_dir / f"{cls}.tsx").write_text(render_page(screen))
        pages.append(cls)

    _patch_app(fe_src / "App.tsx", spec["screens"])
    return {"api_groups": api_groups, "pages": pages}


def _patch_app(app_tsx: Path, screens: list[dict[str, Any]]) -> None:
    if not screens:
        return
    text = app_tsx.read_text()
    text = text.replace(
        'import { Routes } from "react-router-dom";',
        'import { Route, Routes } from "react-router-dom";',
        1,
    )
    imports = "\n".join(
        f'import {{ {pascal(s["name"])} }} from "./routes/{pascal(s["name"])}";'
        for s in screens
    )
    text = text.replace("// GENERATED:IMPORTS", imports, 1)
    routes = "\n      ".join(
        f'<Route path="{s["route"]}" element={{<{pascal(s["name"])} />}} />'
        for s in screens
    )
    text = text.replace("{/* GENERATED:ROUTES */}", routes, 1)
    app_tsx.write_text(text)
