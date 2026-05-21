from typing import Any

from packages.agent_runtime import (
    Agent,
    Envelope,
    StatusUpdate,
    TaskAssignment,
)


class PMAgent(Agent):
    """Project Manager. Phase 5.5 ships a fixed Engineer -> QA workflow.
    The TaskAssignment received from a requester (PO, user, or another PM)
    becomes a "workflow"; PM dispatches sub-tasks to the Engineer and the
    QA agent in turn, and reports aggregated status back to the requester
    threaded against the original envelope.

    Future phases will add AI-driven planning (multiple parallel tasks,
    milestone decomposition, blocker escalation to PO).

    TaskAssignment.inputs is passed through to the Engineer unchanged
    (markdown / provider / model / api_key / max_tokens). QA uses its
    defaults to find the generated project.
    """

    DEFAULT_ROLE = "project_manager"

    def __init__(
        self,
        *,
        engineer_name: str = "engineer",
        qa_name: str = "qa",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.engineer_name = engineer_name
        self.qa_name = qa_name
        self._workflows: dict[str, dict[str, Any]] = {}
        self._reverse: dict[str, str] = {}

    @property
    def active_workflows(self) -> list[str]:
        return list(self._workflows.keys())

    async def handle(self, envelope: Envelope) -> None:
        payload = envelope.payload
        if payload.kind == "task_assignment":
            await self._start_workflow(envelope, payload)
        elif payload.kind == "status_update":
            await self._handle_status(envelope, payload)
        elif payload.kind == "heartbeat":
            return
        else:
            self.memory.add_note(
                f"pm ignoring unsupported payload kind={payload.kind} "
                f"from {envelope.from_agent}"
            )

    async def _start_workflow(
        self, envelope: Envelope, payload: TaskAssignment
    ) -> None:
        task_id = payload.task_id
        requester = envelope.from_agent

        state: dict[str, Any] = {
            "phase": "engineer",
            "requester": requester,
            "original_envelope_id": envelope.id,
            "inputs": dict(payload.inputs),
            "engineer_task_id": None,
            "qa_task_id": None,
            "artifacts": [],
        }
        self._workflows[task_id] = state

        await self._notify_requester(
            state, task_id, "accepted", "planning: engineer -> qa"
        )

        engineer_task_id = f"{task_id}.eng"
        state["engineer_task_id"] = engineer_task_id
        self._reverse[engineer_task_id] = task_id
        await self.send(
            to=self.engineer_name,
            payload=TaskAssignment(
                task_id=engineer_task_id,
                description=f"engineer step for {task_id}",
                inputs=dict(payload.inputs),
            ),
        )

        await self._notify_requester(
            state,
            task_id,
            "in_progress",
            f"dispatched to engineer ({engineer_task_id})",
        )
        self.memory.record_decision(
            summary=f"started workflow {task_id}",
            rationale="fixed engineer -> qa pipeline",
            related_task=task_id,
        )

    async def _handle_status(
        self, envelope: Envelope, payload: StatusUpdate
    ) -> None:
        sub_task_id = payload.task_id
        parent_task_id = self._reverse.get(sub_task_id)
        if not parent_task_id:
            return
        state = self._workflows.get(parent_task_id)
        if not state:
            return

        if payload.status == "failed":
            await self._notify_requester(
                state,
                parent_task_id,
                "failed",
                f"{state['phase']} failed: {payload.notes or 'no detail'}",
            )
            self.memory.add_note(
                f"workflow {parent_task_id} failed at phase={state['phase']}: "
                f"{payload.notes}"
            )
            self._cleanup(parent_task_id)
            return

        if payload.status != "completed":
            return  # accepted / in_progress are noise for the requester

        if state["phase"] == "engineer":
            state["artifacts"].extend(payload.artifact_uris)
            state["phase"] = "qa"
            qa_task_id = f"{parent_task_id}.qa"
            state["qa_task_id"] = qa_task_id
            self._reverse[qa_task_id] = parent_task_id
            await self.send(
                to=self.qa_name,
                payload=TaskAssignment(
                    task_id=qa_task_id,
                    description=f"qa step for {parent_task_id}",
                ),
            )
            await self._notify_requester(
                state,
                parent_task_id,
                "in_progress",
                f"engineer done ({payload.notes}); dispatched to qa",
            )
            return

        if state["phase"] == "qa":
            state["phase"] = "done"
            await self._notify_requester(
                state,
                parent_task_id,
                "completed",
                f"engineer + qa both passed ({payload.notes})",
                artifacts=state["artifacts"],
            )
            self.memory.complete_task(
                task_id=parent_task_id,
                summary="engineer and qa both passed",
            )
            self._cleanup(parent_task_id)

    async def _notify_requester(
        self,
        state: dict[str, Any],
        task_id: str,
        status_value: str,
        notes: str,
        artifacts: list[str] | None = None,
    ) -> None:
        await self.send(
            to=state["requester"],
            payload=StatusUpdate(
                task_id=task_id,
                status=status_value,  # type: ignore[arg-type]
                notes=notes,
                artifact_uris=artifacts or [],
            ),
            in_reply_to=state["original_envelope_id"],
        )

    def _cleanup(self, parent_task_id: str) -> None:
        state = self._workflows.pop(parent_task_id, None)
        if not state:
            return
        for sub_key in ("engineer_task_id", "qa_task_id"):
            sub_id = state.get(sub_key)
            if sub_id is not None:
                self._reverse.pop(sub_id, None)


__all__ = ["PMAgent"]
