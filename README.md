# Document to a Full-Fledged Application

Generate a runnable full-stack application from a requirements document.
Bring your own AI provider API key.

The Spec — a structured representation of the doc — is the contract: every
generated file must trace back to a Spec node, and every Spec node must be
implemented. See `PLAN.md` for the original phased plan, `MULTI_AGENT.md`
for the actor-model multi-agent team architecture (Phases 5-9), and this
file for current capabilities + the **scaling roadmap** that closes the
gap toward larger projects.

## Capabilities

| Area | What works today |
|---|---|
| Inputs | `.md`, `.txt`, `.pdf`, `.docx` |
| Providers | Anthropic, OpenAI, Google Gemini (BYO key) |
| Pipeline | extract_spec → generate → validate → reconcile → package (and refine_spec for chat-style edits) |
| Generated backend | FastAPI + SQLModel + JWT auth + working CRUD with user scoping |
| Generated frontend | Vite + React + TypeScript shell, typed API client per endpoint group, placeholder pages per screen |
| Generated tests | pytest smoke suite that exercises every documented endpoint, with in-memory SQLite |
| Generated DB | SQLite default; spec.stack.db = "postgres" rewrites compose + adds psycopg |
| Live preview | `docker compose` sandbox with frontend (:15173) + backend (:18000); polled logs |
| GitHub push | PAT-based; creates the repo, commits, pushes; tokens redacted from any surfaced error |
| Refinement | Chat panel; produces a child job with a spec-level diff + lineage breadcrumb |
| Cost guard | Optional per-job token budget; pipeline aborts cleanly if exceeded |
| Key handling | API key sent per-request via header; optional encrypted at-rest in IndexedDB (AES-GCM-256, master key non-extractable) |
| Tests | 142 pytest tests covering parsing, codegen, validation, reconciliation, refinement, runner, publisher, and end-to-end job lifecycle |

## Layout

| Path | Purpose |
|---|---|
| `apps/api` | FastAPI orchestrator |
| `apps/web` | Vite + React + TS web UI |
| `packages/doc_parser` | File → normalized markdown |
| `packages/spec_extractor` | Markdown → structured Spec; refine_spec for edits |
| `packages/ai_providers` | Provider-agnostic `LLMClient` + adapters for Anthropic / OpenAI / Gemini |
| `packages/generator` | Spec → code (models, routers, pages, API client, tests) |
| `packages/refiner` | Computes the diff between two Specs |
| `packages/reconciler` | Cross-checks every Spec node against generated artifacts |
| `packages/validator` | py_compile sweep on generated backend |
| `packages/runner` | `docker compose` wrapper for live previews |
| `packages/publisher` | GitHub API + git CLI for PAT-based push |
| `templates/react-fastapi` | Default generated-app template |
| `tests/` | pytest suite for the orchestrator |

## Run

```
docker compose up
```

Web UI: http://localhost:5173 · API: http://localhost:8000

The orchestrator only needs Docker + your AI provider key. The generated
project lives in `/tmp/doc-to-app-artifacts/<job_id>/project/` and ships as a
downloadable ZIP plus an optional live preview.

---

# Scaling roadmap

This section is the plan for taking the orchestrator from "hackathon-grade
MVP" to something usable for genuinely large projects. Each item lists the
current ceiling, the proposed approach, the implementation outline, and the
risks/tradeoffs.

Effort estimates: **S** ≈ a few days · **M** ≈ a week or two · **L** ≈ a
month-plus of focused work.

## Capacity, today vs after roadmap

| Dimension | Today | After roadmap |
|---|---|---|
| Doc size | ~150 pages (single LLM context) | unbounded (chunked extraction) |
| Entities per spec | ~50 (single-response output ceiling) | hundreds (chunked + merge pass) |
| Endpoints | ~200 | thousands |
| Screens with real UI | ~10 (placeholders today) | hundreds (AI frontend codegen) |
| Refinement cost | O(full spec) every edit | O(diff) via JSON Patch |
| Concurrent previews | 1 (fixed host ports) | many (per-job reverse proxy) |
| Server-side state | in-memory dict (lost on restart) | Postgres + blob store |
| Generated DB migrations | none (auto-create only) | Alembic, generated alongside code |
| Long-term codebase shape | flat `models/`, `routers/` | domain-bounded subdirs |

## Item 1 — AI-driven frontend codegen

**Why first.** The biggest honest gap. The backend generator emits real
working CRUD with auth scoping. The frontend generator emits page components
that are *placeholders* — a heading and a "customize this screen" note. For
a 3-screen todo app the user customizes 3 files; for a 30-screen app, 30.
The "nothing more, nothing less" promise is honest at the spec level but the
frontend is a scaffold, not a finished app.

**Approach.** Per-screen LLM codegen, gated by the same spec contract.

1. Add an `ai_frontend` codegen stage that runs *per screen* after the
   mechanical scaffold step. Inputs:
   - The screen entry from spec.screens (name, route, components, actions)
   - The entities the screen references (inferred from spec.endpoints used
     in `actions` + heuristic name matching)
   - The signatures from the already-generated `src/lib/<group>.ts` API
     client (Pascal-cased type names, function names, parameter shapes)
   - A small design-system primer (Tailwind utility classes, base
     button/input/card patterns from the template)
2. Output: a single `src/routes/<Pascal>.tsx` file containing the page
   component, possibly with a sibling `src/components/<group>/*.tsx` file
   for shared bits.
3. Add a frontend validator stage that runs `npx tsc -b` (no emit) on the
   generated project; on failure, feed errors back to the same LLM with a
   "your previous output failed: …" message — same retry pattern as
   `extract_spec`. Bounded to 2 retries per screen.
4. Extend the reconciler to verify each generated page imports from the
   correct API client modules and uses entities declared in the spec.
   Pages that reference symbols not in the spec are flagged as "extras"
   the same way extra entity files are today.

**Implementation outline.**
- New module: `packages/ai_frontend/__init__.py` with
  `generate_page(spec, screen, llm)` and a small system prompt that
  explicitly forbids inventing fields, endpoints, or screens.
- `packages/generator/frontend.py.write_frontend` already lays down the
  placeholder; replace the body of `render_page` with a hook that produces
  *the placeholder when AI is disabled* and the AI-generated component when
  enabled, controlled by `spec.non_functional.ui = "scaffold" | "ai"`.
- New schema enum value for `non_functional.ui`. Default `scaffold` to
  preserve current behaviour.
- New pipeline stage in `apps/api/routers/jobs.py` between `generate` and
  `validate`: `generate_ui` (skipped if ui=scaffold).
- New tsc validator: subprocess wrapping `npx tsc -b` in
  `<project>/frontend`, parsing diagnostics.
- New tests: fake LLM returns canned components, assert tsc passes; assert
  forbidden-symbol detection works.

**Tradeoffs.**
- LLM hallucination risk is highest here. A model might add a button that
  calls an undeclared endpoint. The reconciler check is the main guard.
- Cost: roughly one LLM call per screen. For a 20-screen app at ~3K tokens
  per call, ~60K tokens — comparable to today's refinement cost. The token
  budget already enforces a ceiling.
- Determinism: AI output varies between runs. Mitigation: temperature=0 and
  a fixed seed when the provider supports it.

**Depends on.** Nothing — independent.
**Effort.** L.

## Item 2 — Large-document spec chunking

**Why.** Today `extract_spec` sends the whole document + the whole schema
in a single LLM call. Hard ceilings: ~150 pages of doc (provider context
limit) and ~50 entities of output (`max_tokens` truncation when the spec
JSON gets big).

**Approach.** Map-reduce extraction.

1. **Segment**: split the normalized markdown by section. Prefer doc
   structure (H1/H2 boundaries) with a fallback to fixed-size windows
   (e.g., 4K tokens with 200-token overlap to avoid losing context across
   boundaries).
2. **Map**: each segment is sent to the LLM with a tweaked system prompt:
   "you are extracting the *partial* spec for one section of the document.
   Only include entities/endpoints/screens that this section explicitly
   describes. Mark entities you only *reference* but don't *define* with
   `"_ref_only": true`."
3. **Reduce**: a deterministic merge pass walks every partial spec.
   Entities with the same `name` are unioned (fields merged; conflicting
   types raise a merge conflict). Endpoints are deduplicated by
   `(method, path)`. Screens by `name`.
4. **Reconcile**: a final small LLM call (or schema validation pass) that
   resolves dangling `_ref_only` entities — either by finding a definition
   in another segment or by raising a fail-the-job error.

**Implementation outline.**
- New module `packages/spec_extractor/chunking.py` with `segment_markdown`
  and `merge_partials`.
- `extract_spec` becomes a thin orchestrator that segments, maps in
  parallel via `asyncio.gather`, merges, and validates.
- Schema gets an internal-only `_ref_only` field (stripped before the
  spec is shown to the user).
- Per-segment results recorded in `job.usage` so cost is still tracked
  granularly.

**Tradeoffs.**
- Cost may actually go *down* for large docs (smaller responses per call
  vs. one giant truncated output), but goes up slightly for small docs.
  Heuristic: skip chunking if doc < 8K tokens.
- Merge step is the hard bit. Two segments describing the same entity
  with different fields → merge conflict. Decide policy: union fields
  (lenient) vs. fail-the-job (strict). Strict is safer for "nothing more,
  nothing less".

**Depends on.** Nothing.
**Effort.** M.

## Item 3 — JSON Patch refinements

**Why.** Today `refine_spec` sends the *full* current spec + change
request, gets the *full* updated spec back. For a 50K-token spec, that's
~50K in + ~50K out every refinement.

**Approach.** Ask the LLM to output a JSON Patch (RFC 6902) describing the
change; apply it server-side.

1. New system prompt: "given the current Spec, output a JSON Patch
   operations array that, when applied, produces the user's requested
   change. Do not output the full spec."
2. Server applies the patch with `jsonpatch` (Python package), validates
   the result against the schema.
3. On parse/validation failure: retry with a "your patch was invalid:
   …" message, **bounded to 2 retries**, then **fall back** to full-spec
   refinement so we don't strand the user.
4. The diff stage that already exists is unchanged — we still show
   added/removed/modified to the user.

**Implementation outline.**
- New prompt in `packages/spec_extractor/prompts.py`:
  `patch_refinement_system_prompt()`.
- New function `refine_spec_via_patch(current_spec, change_request, llm)`
  in `packages/spec_extractor/__init__.py`.
- `_run_refinement` in `apps/api/routers/jobs.py` tries the patch path
  first; on persistent failure logs and falls through to `refine_spec`.
- New tests verifying: valid patch is applied; invalid patch triggers
  retry; persistent failure triggers fallback.

**Tradeoffs.**
- LLMs are known to produce malformed JSON Patches. The fallback to
  full-spec refine keeps the feature reliable.
- Cost win is large (5-20× cheaper refinements) when it works.

**Depends on.** Nothing.
**Effort.** S.

## Item 4 — Domain partitioning

**Why.** Today every entity lands in `backend/app/models/<name>.py` and
every URL prefix becomes one router file. For a system with `/admin/users`,
`/admin/posts`, `/admin/settings`, `/admin/audit`, all four end up in
`backend/app/routers/admin.py` — quickly an unmaintainable thousand-line
file. No bounded contexts, no service layer.

**Approach.** Optional spec-driven domain partitioning.

1. New schema field: `spec.domains: { name, entities[], endpoints[],
   screens[] }[]`. Spec authors (or the LLM) group features by domain.
   When absent, behaviour falls back to today's flat layout.
2. Generator emits per-domain subdirs:
   ```
   backend/app/users/        models.py, router.py, services.py (placeholder)
   backend/app/billing/      models.py, router.py
   backend/app/admin/        models.py, router.py
   ```
3. Cross-domain references go through explicit imports
   (`from app.users.models import User`). Pydantic forward-ref handling
   is needed for circular references.
4. Frontend mirrors the structure: `src/users/`, `src/billing/`, with the
   App.tsx router registering routes namespaced under the domain.
5. Reconciler updated to walk the per-domain layout.

**Implementation outline.**
- Schema update in `packages/spec_extractor/schema.json`.
- Codegen refactor in `packages/generator/backend.py` (and
  `frontend.py`): split `write_models` and `write_routers` to take a
  domain parameter.
- New AI prompt hint: encourage the model to propose domain partitions
  when the spec exceeds a size threshold.

**Tradeoffs.**
- Some apps don't partition naturally — small projects shouldn't be
  forced into a domain split. The fallback to flat layout is essential.
- Cross-domain entity references add real complexity to SQLModel
  metadata.

**Depends on.** Nothing strictly, but most useful after Item 2 unblocks
larger specs.
**Effort.** M.

## Item 5 — Alembic migrations in the generated app

**Why.** Today the generated app's `init_db()` calls
`SQLModel.metadata.create_all(engine)` on startup. That creates *new*
tables; it doesn't add columns to existing ones or rename anything. If a
user refines and adds a `priority` field, their local SQLite from the
previous run has the old schema. They have to delete the DB and start
over.

**Approach.** Bake Alembic into the template and run autogenerate on
every codegen pass.

1. Template gains:
   ```
   backend/alembic.ini
   backend/alembic/env.py
   backend/alembic/versions/
   ```
   `env.py` reads `app.models.*` via `SQLModel.metadata` so autogenerate
   knows the target schema.
2. After `write_backend`, the generator runs (synchronously, in the
   orchestrator process):
   ```
   alembic revision --autogenerate -m "spec snapshot <job_id>"
   ```
   The resulting migration is bundled in the ZIP under
   `backend/alembic/versions/`.
3. The generated app's startup runs `alembic upgrade head` instead of
   `create_all`. Existing data survives a refinement that adds columns.
4. Migration files from refinements are *additive* (new file per child
   job), not destructive — the user can roll back to an earlier spec by
   downgrading.

**Implementation outline.**
- `templates/react-fastapi/backend/alembic*` added to the template.
- `packages/generator/migrations.py` shells out to alembic in the
  generated project's venv (need to install alembic into the project
  during generation? Or use the orchestrator's alembic with a path
  override).
- Template's `app/main.py` lifespan switches to alembic upgrade.

**Tradeoffs.**
- Alembic autogenerate has known false-positives — column reordering,
  default expression equivalence. Pin SQLAlchemy to a known-good version.
- For *destructive* changes (rename column, drop table) the user must
  edit the migration by hand. We can warn in the diff card when an
  operation looks destructive.

**Depends on.** Nothing.
**Effort.** M.

## Item 6 — Job + artifact persistence

**Why.** `_jobs: dict[str, dict[str, Any]]` lives in the FastAPI worker
process. Restart the orchestrator → all job state is gone, generated
artifacts on disk become orphans. Fine for single-user self-hosted, broken
for any deployment that survives a redeploy.

**Approach.** A `JobStore` abstraction with a SQLite default and a
Postgres-backed implementation for SaaS.

1. New `packages/job_store/__init__.py` with:
   ```python
   class JobStore(Protocol):
       def create(self, job: dict) -> None: ...
       def get(self, job_id: str) -> dict | None: ...
       def update(self, job_id: str, mutator: Callable[[dict], None]) -> dict: ...
       def list(self, limit: int = 50) -> list[dict]: ...
   ```
   `update` uses row-level locking (`SELECT ... FOR UPDATE` on Postgres,
   `IMMEDIATE` transaction on SQLite) so concurrent pipeline stages can't
   stomp each other.
2. Artifact ZIPs and project dirs move from `/tmp/...` to a configurable
   blob store: filesystem path for self-host, S3/MinIO bucket for SaaS.
3. `apps/api/routers/jobs.py` and `preview.py` swap their dict access for
   `JobStore` calls.
4. New cleanup job (background task on startup) reaps orphan artifacts
   older than a configurable TTL.

**Implementation outline.**
- Job state schema: `id (pk), status, stages_json, spec_json,
  validation_json, reconciliation_json, refinement_json, usage_json,
  max_tokens, artifact_uri, created_at, updated_at`.
- Migration scripts under `apps/api/migrations/`.
- Config: `JOB_STORE=sqlite:///./jobs.db` or `postgres://...`.
- Blob store: `ARTIFACT_DIR=/var/lib/doc-to-app` or `s3://bucket/prefix`.

**Tradeoffs.**
- Adds a real database dependency for the orchestrator itself.
- Concurrency model needs care — pipeline stages mutate job state
  mid-execution. Either keep all stages in one process (current model)
  or move to a job queue (Redis + RQ / Celery).

**Depends on.** Nothing strictly; required for items 7 and any SaaS
deployment.
**Effort.** M.

## Item 7 — Per-preview reverse proxy + idle reaping

**Why.** The current preview compose file pins host ports `18000` and
`15173`. Two users (or two job IDs) cannot have previews running
simultaneously. Preview containers also run forever — a user who closes
their browser leaves a backend + frontend + (postgres) running.

**Approach.** Random container ports + a reverse proxy + an idle reaper.

1. The generated preview compose binds container ports to **random** host
   ports (`"0:8000"`, `"0:5173"`).
2. `start_preview` queries `docker compose port <service> <container_port>`
   to discover the assigned host port and stores it in the Preview
   dataclass (this already exists in the runner; the fixed-port path was
   a simplification).
3. A reverse proxy (Caddy or Traefik) running as part of `docker-compose`
   for the orchestrator routes:
   - `<job_id>-frontend.preview.localhost` → host-assigned frontend port
   - `<job_id>-api.preview.localhost` → host-assigned API port
   Wildcard DNS for `*.preview.localhost` works out of the box on most
   OSes (resolves to 127.0.0.1).
4. Preview state grows `last_accessed_at`, bumped on every `/preview/logs`
   poll and via a heartbeat from the live preview UI.
5. Background reaper (asyncio task on orchestrator startup) finds previews
   with `last_accessed_at` older than `PREVIEW_IDLE_TIMEOUT` (default
   30 min) and runs `stop_preview`. Records a "stopped: idle" note on the
   job.

**Implementation outline.**
- Update `packages/runner/__init__.py` to use `0:8000` / `0:5173` and
  add `_resolve_port` (parses `docker compose port` output).
- New optional service in `docker-compose.yml`: a Caddy container that
  reads job→port mappings from a file the orchestrator writes.
- New endpoint heartbeat from the frontend `PreviewPanel` (already polls
  logs every 2.5s — just register that as activity).

**Tradeoffs.**
- Wildcard DNS doesn't work on every OS without setup. Fallback:
  numbered subdomains via `/etc/hosts` or query-param routing on a
  single host.
- Idle reaping is a behavioural change; defaults must be obvious and
  the UI must surface "preview stopped due to idle".

**Depends on.** Item 6 (so preview tracking survives a restart).
**Effort.** M.

## Suggested execution order

If we're shipping incrementally:

1. **Item 3 (JSON Patch refinements)** — small, immediate cost win, unblocks
   no one downstream.
2. **Item 5 (Alembic)** — small-medium, makes the generated app
   production-real.
3. **Item 1 (AI frontend codegen)** — biggest user-visible value.
4. **Item 2 (Large-document chunking)** — unblocks large docs.
5. **Item 6 (Job persistence)** — required before serving multiple users.
6. **Item 7 (Per-preview proxy)** — depends on Item 6.
7. **Item 4 (Domain partitioning)** — most architectural; most useful once
   1-6 are in.

Total rough effort: ~3 months of focused work for one engineer to get from
today's MVP to the post-roadmap capacity in the table above. The first three
items (about 3-4 weeks combined) cover ~80% of the "feels like a real
product" gap.
