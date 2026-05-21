from pathlib import Path
from typing import Any

from packages.agent_runtime import (
    Agent,
    Envelope,
    StatusUpdate,
    TaskAssignment,
)
from packages.ai_providers.anthropic_client import AnthropicClient
from packages.ai_providers.base import LLMClient
from packages.ai_providers.gemini_client import GeminiClient
from packages.ai_providers.openai_client import OpenAIClient
from packages.generator import generate, package_zip
from packages.reconciler import reconcile
from packages.spec_extractor import extract_spec
from packages.validator import validate


def _make_client(provider: str, api_key: str, model: str) -> LLMClient:
    if provider == "anthropic":
        return AnthropicClient(api_key=api_key, model=model)
    if provider == "openai":
        return OpenAIClient(api_key=api_key, model=model)
    if provider == "gemini":
        return GeminiClient(api_key=api_key, model=model)
    raise ValueError(f"Unsupported provider: {provider}")


class EngineerAgent(Agent):
    """Wraps the existing extract_spec -> generate -> validate -> reconcile ->
    package pipeline as a single agent on the runtime.

    Inputs expected on the TaskAssignment payload:
      - markdown: str          (the parsed requirements doc)
      - provider: str          ("anthropic" | "openai" | "gemini")
      - model: str             (provider-specific model id)
      - api_key: str           (BYO key)
      - max_tokens: int | None (optional budget)

    Emits a sequence of StatusUpdate envelopes back to the requester:
      accepted -> in_progress(extract) -> in_progress(generate) ->
      in_progress(validate) -> in_progress(reconcile) ->
      in_progress(package) -> completed (or failed at any stage).

    On completion the workspace contains a `project/` tree plus a
    `<task_id>.zip` artifact, and the workspace audit log carries one
    'engineer' snapshot commit per pipeline run.
    """

    DEFAULT_ROLE = "engineer"

    async def handle(self, envelope: Envelope) -> None:
        payload = envelope.payload
        if payload.kind == "task_assignment":
            await self._run_pipeline(envelope, payload)
        elif payload.kind == "heartbeat":
            return
        else:
            self.memory.add_note(
                f"engineer ignoring unsupported payload kind={payload.kind} "
                f"from {envelope.from_agent}"
            )

    async def _run_pipeline(
        self, envelope: Envelope, payload: TaskAssignment
    ) -> None:
        task_id = payload.task_id
        inputs = payload.inputs
        requester = envelope.from_agent

        async def status(status_value: str, notes: str, **extra: Any) -> None:
            await self.send(
                to=requester,
                payload=StatusUpdate(
                    task_id=task_id,
                    status=status_value,  # type: ignore[arg-type]
                    notes=notes,
                    artifact_uris=extra.get("artifact_uris", []),
                ),
                in_reply_to=envelope.id,
            )

        try:
            self._require(inputs, "markdown", "provider", "model", "api_key")
        except ValueError as exc:
            await status("failed", str(exc))
            self.memory.add_note(f"task {task_id} rejected: {exc}")
            return

        markdown = inputs["markdown"]
        provider = inputs["provider"]
        model = inputs["model"]
        api_key = inputs["api_key"]
        max_tokens = inputs.get("max_tokens")

        await status("accepted", "task received")

        # --- extract_spec ---
        try:
            await status("in_progress", "extracting spec")
            llm = _make_client(provider, api_key, model)
            extraction = extract_spec(markdown, llm, max_tokens_budget=max_tokens)
        except Exception as exc:  # noqa: BLE001
            await status("failed", f"extract_spec failed: {exc}")
            self.memory.add_note(f"task {task_id} extract_spec failed: {exc}")
            return

        spec = extraction.spec
        usage = extraction.usage
        self.memory.record_decision(
            summary=f"extracted spec for '{spec['app']['name']}'",
            rationale=(
                f"{len(spec.get('entities', []))} entities, "
                f"{len(spec.get('endpoints', []))} endpoints, "
                f"{len(spec.get('screens', []))} screens, "
                f"{usage['total']} tokens"
            ),
            related_task=task_id,
        )

        # --- generate ---
        try:
            await status("in_progress", "generating files")
            project_dir = Path(self.workspace.root) / "project"
            project = generate(spec, project_dir)
        except Exception as exc:  # noqa: BLE001
            await status("failed", f"generate failed: {exc}")
            self.memory.add_note(f"task {task_id} generate failed: {exc}")
            return

        # Record the generated tree as a single engineer snapshot
        self.workspace.snapshot(
            agent_name=self.name,
            agent_role=self.role,
            message=f"generated {spec['app']['name']} (task {task_id})",
            glob="project/**/*",
        )

        # --- validate ---
        await status("in_progress", "validating")
        v = validate(project)
        if not v.ok:
            await status(
                "failed",
                f"validation failed: {len(v.errors)} compile error(s)",
            )
            self.memory.add_note(
                f"task {task_id} validation failed: {len(v.errors)} errors"
            )
            return

        # --- reconcile ---
        await status("in_progress", "reconciling")
        r = reconcile(spec, project)
        if r.missing:
            await status(
                "failed",
                f"reconciliation gaps: {len(r.missing)} spec item(s) missing",
            )
            self.memory.add_note(
                f"task {task_id} reconciliation gaps: {len(r.missing)} missing"
            )
            return

        # --- package ---
        await status("in_progress", "packaging")
        zip_path = package_zip(project, Path(self.workspace.root) / f"{task_id}.zip")

        coverage = r.coverage
        covered = sum(b["covered"] for b in coverage.values())
        total = sum(b["total"] for b in coverage.values())
        await self.send(
            to=requester,
            payload=StatusUpdate(
                task_id=task_id,
                status="completed",
                artifact_uris=[str(zip_path)],
                notes=(
                    f"{covered}/{total} spec items covered; "
                    f"{usage['total']} tokens used"
                ),
            ),
            in_reply_to=envelope.id,
        )
        self.memory.complete_task(
            task_id=task_id,
            summary=f"shipped {spec['app']['name']} ({covered}/{total} covered)",
        )

    @staticmethod
    def _require(inputs: dict, *keys: str) -> None:
        missing = [k for k in keys if k not in inputs or inputs[k] is None]
        if missing:
            raise ValueError(f"task missing required inputs: {missing}")


__all__ = ["EngineerAgent"]
