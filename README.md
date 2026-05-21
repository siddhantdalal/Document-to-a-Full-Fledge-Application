# Document to a Full-Fledged Application

Generate a runnable full-stack application from a requirements document.
Bring your own AI provider API key.

The Spec — a structured representation of the doc — is the contract: every
generated file must trace back to a Spec node, and every Spec node must be
implemented. See `PLAN.md` for the full architecture and roadmap.

## Status

Phase 1 scaffolding. Not yet functional.

## Layout

| Path                          | Purpose                                  |
|-------------------------------|------------------------------------------|
| `apps/api`                    | FastAPI orchestrator                     |
| `apps/web`                    | Vite + React + TS web UI                 |
| `packages/doc_parser`         | File → normalized markdown               |
| `packages/spec_extractor`     | Markdown → structured Spec JSON          |
| `packages/ai_providers`       | Provider-agnostic LLM client             |
| `packages/generator`          | Spec → code (against a template)         |
| `packages/validator`          | Typecheck, lint, build of generated code |
| `templates/react-fastapi`     | Default generated-app template           |
| `infra/docker`                | Sandbox images                           |

## Run

```
docker compose up
```

Web UI: http://localhost:5173 · API: http://localhost:8000
