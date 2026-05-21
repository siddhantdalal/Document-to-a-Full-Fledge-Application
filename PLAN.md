# Document → Full-Fledged Application: Build Plan

## 1. Product Statement

A tool that ingests a requirements document and produces a runnable, end-to-end
application (frontend + backend + data layer + run/deploy scripts) that
implements **exactly** the requirements stated in the document — no extra
features, no missing ones.

Users bring their own API key for the AI model they want the generator to use
(Anthropic Claude, OpenAI, Google Gemini, …). Our service never charges for
model usage — the user's key is used directly.

---

## 2. End-to-End User Flow

```
┌────────┐   ┌──────────┐   ┌──────────────┐   ┌──────────────┐   ┌─────────────┐
│ Upload │ → │ Choose   │ → │ Spec preview │ → │ Generation & │ → │ Preview /   │
│ doc    │   │ provider │   │ + confirm    │   │ self-repair  │   │ download /  │
│ + key  │   │ + model  │   │ scope        │   │ loop         │   │ push to Git │
└────────┘   └──────────┘   └──────────────┘   └──────────────┘   └─────────────┘
```

1. User uploads `.md` / `.pdf` / `.docx` / `.txt`.
2. User selects AI provider, model, and pastes their API key (validated by a
   tiny test call; stored only in-session, never logged, never persisted unless
   the user explicitly opts in to encrypted storage).
3. Doc parser extracts text; a **Spec Extractor** agent converts it to a
   structured JSON spec (entities, screens, endpoints, auth, integrations).
4. User reviews the spec and confirms / edits. **This is the contract** for
   "nothing more, nothing less."
5. Generation pipeline runs (planner → scaffolder → backend → frontend →
   integration → validator). Failures feed back into a self-repair loop with a
   bounded retry budget.
6. Output: a downloadable ZIP, a running preview in a sandboxed container, and
   optional push to a GitHub repo the user owns.

---

## 3. System Architecture

```
apps/
  web/                Next.js UI (upload, key entry, spec editor, live logs, preview)
  api/                Orchestrator service (FastAPI). Owns the job lifecycle.
  worker/             Long-running job runner (queue consumer). Calls into packages/*.

packages/
  doc-parser/         PDF/DOCX/MD/TXT → normalized markdown
  spec-extractor/     markdown → structured Spec JSON (validated against schema)
  ai-providers/       Provider-agnostic LLM client (Anthropic / OpenAI / Gemini)
  generator/          Spec → code, per stack template
  validator/          Typecheck + lint + build + smoke tests on generated code
  runner/             Docker exec of generated app, returns preview URL + logs

templates/
  react-fastapi/      Default stack: React+Vite+TS+Tailwind / FastAPI+SQLModel
  next-node/          Optional: Next.js full-stack
  (others added later)

infra/
  docker/             Sandbox images for generation and preview
  scripts/            CI, formatters, release
```

---

## 4. The Spec — Our Single Source of Truth

The **Spec** is the bridge between the doc and the code. Without it, "nothing
more, nothing less" is unenforceable.

Schema (draft):

```jsonc
{
  "app": { "name": "...", "summary": "...", "version": "0.1.0" },
  "stack": { "frontend": "react-vite-ts", "backend": "fastapi", "db": "sqlite" },
  "entities": [
    { "name": "User", "fields": [{ "name": "email", "type": "string", "unique": true }] }
  ],
  "auth": { "type": "jwt", "roles": ["admin", "user"] },
  "endpoints": [
    { "method": "POST", "path": "/login", "auth": false, "request": {...}, "response": {...} }
  ],
  "screens": [
    { "name": "Login", "route": "/login", "components": [...], "actions": [...] }
  ],
  "integrations": [],  // explicit list — empty means none
  "non_functional": { "i18n": false, "analytics": false, "tests": "smoke" }
}
```

Two rules give us the "exactly what the doc says" guarantee:

1. **Spec extraction is reviewable.** The UI diffs the spec against the doc
   line-by-line so the user catches over-/under-reach before generation.
2. **Generator is spec-bound.** Every file emitted must trace to a spec node.
   A reconciliation step lists `spec features → code artifacts` and fails the
   job if there is unbacked code or unimplemented spec entries.

---

## 5. Generation Pipeline

Each stage is a tool call with a structured input/output contract, so failures
are localized and retriable.

| # | Stage             | Input              | Output                          | Failure mode                   |
|---|-------------------|--------------------|---------------------------------|--------------------------------|
| 1 | Doc parse         | uploaded file      | normalized markdown             | unsupported format → reject    |
| 2 | Spec extract      | markdown           | Spec JSON (schema-validated)    | retry with stricter prompt     |
| 3 | Spec confirm      | Spec JSON          | user-approved Spec              | user edit loop                 |
| 4 | Plan              | Spec               | file tree + dependency list     | retry                          |
| 5 | Scaffold          | plan + template    | empty project on disk           | template error → abort         |
| 6 | Backend codegen   | Spec + scaffold    | models, routers, services       | per-file retry                 |
| 7 | Frontend codegen  | Spec + scaffold    | pages, components, API client   | per-file retry                 |
| 8 | Integrate         | both sides         | env, configs, README, scripts   | retry                          |
| 9 | Validate          | full project       | typecheck + build + lint result | feed errors back to step 6/7   |
| 10| Reconcile         | Spec + project     | coverage report                 | fail job if gaps remain        |
| 11| Package           | project            | ZIP / Docker image / Git push   | —                              |

Self-repair loop: stage 9 failures route back to 6 or 7 with the error log,
capped at N retries (default 3) per file and a total token budget per job.

---

## 6. AI Provider & BYOK

`packages/ai-providers/` exposes one interface:

```ts
interface LLMClient {
  complete(opts: { system, messages, tools?, schema?, temperature }): Promise<Response>;
  // streaming variant, structured-output variant
}
```

Adapters: `AnthropicClient`, `OpenAIClient`, `GeminiClient`. Each maps the
unified options to the provider's native API.

**Key handling rules:**

- Entered in the UI; kept in the browser, sent to the API only as a
  `X-Provider-Key` header on the generation request.
- Server holds the key in worker memory for the duration of the job. Never
  written to disk, never logged, redacted in any error trace.
- Validated on entry with a `models.list`-style call (or smallest possible
  completion) so we fail fast on bad keys.
- Optional "save key" toggle stores the key encrypted at rest (envelope
  encryption with a KMS-held data key); off by default.
- Per-job token budget set in the UI; worker aborts cleanly if exceeded.

---

## 7. Defaults for Generated Apps

Picked to minimize generation surface area and maximize the chance the code
runs first time:

- **Frontend:** React + Vite + TypeScript + Tailwind + React Router + TanStack
  Query.
- **Backend:** FastAPI + SQLModel + Pydantic + uvicorn (alt: Node + Express +
  Prisma).
- **DB:** SQLite for dev, swappable to Postgres via env.
- **Auth:** JWT with a refresh-token endpoint when the spec asks for auth.
- **Tests:** smoke tests only by default; expanded if the spec requests it.
- **Run:** `docker compose up` brings up the whole thing.

Stack is part of the Spec, so users can override.

---

## 8. Sandboxing & Safety

- Doc parsing runs in a restricted worker (no network, read-only fs except
  scratch).
- Generated code is built and run only inside a Docker sandbox with no host
  mounts and no outbound network beyond an allowlist (the app's own service
  URLs, npm/pypi registries during install).
- Static analysis pass on generated code: dependency audit (`npm audit`,
  `pip-audit`), secret scan, simple SAST (semgrep ruleset) — surfaced to the
  user, not silently fixed.

---

## 9. Build Phases

**Phase 1 — MVP (smallest thing that proves the loop works)**
- One provider (Anthropic), one model.
- Markdown input only.
- Single template (`react-fastapi`).
- No sandbox, no live preview — just ZIP download.
- Spec extraction + confirm UI + generation + validate + reconcile.

**Phase 2 — BYOK + format coverage**
- Add OpenAI and Gemini adapters; provider dropdown in UI.
- PDF and DOCX parsing.
- Encrypted optional key storage.
- Token budgeter + cost preview.

**Phase 3 — Live preview**
- Docker sandbox runner, streamed logs, preview URL.
- GitHub push integration (OAuth, user-owned repo).

**Phase 4 — Iteration**
- "Chat with the generated app" to add/modify features (still spec-bound — a
  chat message becomes a spec diff first, then a regen).
- Additional stack templates.
- Expanded test generation.

---

## 10. Locked Decisions (Phase 1)

| # | Decision                  | Choice                                              |
|---|---------------------------|-----------------------------------------------------|
| 1 | Orchestrator backend      | **Python + FastAPI**                                |
| 2 | Default generated stack   | **React + Vite + TS** (FE) / **FastAPI + SQLModel** (BE) / **SQLite** |
| 3 | Deployment model          | **Self-hosted Docker image**, user-run, BYOK        |
| 4 | Job runner (MVP)          | **In-process background task** in FastAPI; queue deferred to Phase 3 |
| 5 | Our-app auth (MVP)        | **Anonymous**; API key kept in the browser, sent per-request |

These collapse the architecture nicely: one Python codebase end-to-end
(orchestrator + generated backend share libraries), one Docker image to ship,
no auth/DB on our side for MVP, no queue infra.

---

## 11. Phase 1 — Concrete Scope

**In scope**
- Next.js (or simple React) UI: upload `.md`, paste Anthropic API key, pick
  model, view extracted spec, edit/confirm, watch logs, download ZIP.
- FastAPI orchestrator with `POST /jobs` (multipart: doc + key + model),
  `GET /jobs/{id}` (status + log stream via SSE), `GET /jobs/{id}/artifact`
  (ZIP).
- `packages/doc-parser`: markdown only.
- `packages/spec-extractor`: prompt + JSON-schema-validated output.
- `packages/ai-providers`: Anthropic adapter only; interface in place for
  others.
- `packages/generator` + `templates/react-fastapi`: scaffold + per-file codegen
  with retries.
- `packages/validator`: `tsc --noEmit`, `vite build`, `python -m compileall`,
  `ruff check`. Errors feed back into the generator.
- Reconciliation report (spec ↔ files); job fails if gaps remain after retry
  budget.
- Single `docker compose up` runs the whole tool locally.

**Out of scope for Phase 1** (tracked for later phases)
- PDF/DOCX parsing.
- OpenAI/Gemini adapters.
- Live preview of the generated app (sandbox runner).
- GitHub push, saved projects, sign-in.
- Iterative refinement / "chat with the app".
- Token budget UI (hard cap server-side only).

**Phase 1 acceptance test**

A markdown doc describing a simple todo app (CRUD + auth) goes in; a ZIP
comes out that runs cleanly with `docker compose up`, exposes the documented
endpoints, renders the documented screens, and contains no extra
routes/screens/entities beyond the spec.

---

## 12. Immediate Next Steps

1. Scaffold the monorepo: `apps/web`, `apps/api`, `packages/*`, `templates/react-fastapi`, `infra/docker`, root `docker-compose.yml`, `pyproject.toml` / `package.json` workspaces.
2. Draft and freeze the Spec JSON schema in `packages/spec-extractor/schema.json`.
3. Build the spec-extractor prompt + a fixtures-based test (markdown in → expected spec out) before wiring it to a live model.
4. Build the `react-fastapi` template by hand first — generate the *empty* shell of a working app — so codegen only fills in spec-derived pieces.
5. Wire `POST /jobs` end-to-end with a stub generator (returns a fixed ZIP) so the UI ↔ API contract is locked before AI is involved.
