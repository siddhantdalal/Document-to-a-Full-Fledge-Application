import json
import re
import uuid
from typing import Any

from packages.agent_runtime import (
    Agent,
    Envelope,
    StatusUpdate,
    TaskAssignment,
    UserMessage,
    UserReply,
)
from packages.ai_providers import CompletionRequest, LLMClient, Message


_SYSTEM_PROMPT = """You are the Product Owner for a small software engineering team consisting of a Project Manager, an Engineer, and a QA agent. Your job is to chat with the user about what they want to build, ask short clarifying questions when needed, and when you have enough information, hand off the requirements to the team.

You MUST respond with a JSON object inside a ```json fenced block:

```json
{
  "reply": "<your message to the user>",
  "handoff": null
}
```

When the user has described their app clearly enough that the team can start (app name + key features + entities + screens), instead emit:

```json
{
  "reply": "<a short message telling the user you're handing off>",
  "handoff": {"brief": "<full requirements brief in markdown>"}
}
```

The Requirements Brief should be a complete markdown document covering:
- # App name and a one-paragraph summary
- ## Features (bulleted list of what users can do)
- ## User roles and auth (if any)
- ## Screens / pages with their routes
- ## Data entities and fields (your best inference from the chat)
- ## API endpoints (your best inference)
- ## Non-functional requirements (tests, performance, etc.)

Until handoff, set "handoff" to null and just chat. Be concise — ask one or two questions per turn at most. Don't ask about implementation details (the Engineer will choose tech stack, libraries, etc.).
"""


class POAgent(Agent):
    """Product Owner. Chats with the user (via UserMessage / UserReply
    envelopes); decides when to hand off the requirements to the PM; forwards
    PM status updates back to the user."""

    DEFAULT_ROLE = "product_owner"

    def __init__(
        self,
        *,
        llm: LLMClient,
        provider: str,
        model: str,
        api_key: str,
        pm_name: str = "pm",
        user_name: str = "user",
        max_tokens_budget: int | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.llm = llm
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.pm_name = pm_name
        self.user_name = user_name
        self.max_tokens_budget = max_tokens_budget
        self.history: list[Message] = []
        self.brief: str | None = None
        self.workflow_id: str | None = None

    async def handle(self, envelope: Envelope) -> None:
        payload = envelope.payload
        if payload.kind == "user_message":
            await self._on_user_message(envelope, payload)
        elif payload.kind == "status_update":
            await self._on_pm_status(envelope, payload)
        elif payload.kind == "heartbeat":
            return
        else:
            self.memory.add_note(
                f"po ignoring unsupported payload kind={payload.kind} "
                f"from {envelope.from_agent}"
            )

    async def _on_user_message(
        self, envelope: Envelope, payload: UserMessage
    ) -> None:
        if self.brief is not None:
            await self.reply(
                envelope,
                UserReply(
                    text=(
                        "The team is already building. Watch the activity "
                        "panel for progress — I'll let you know when there's "
                        "something to review."
                    )
                ),
            )
            return

        self.history.append(Message(role="user", content=payload.text))

        try:
            response = self.llm.complete(
                CompletionRequest(
                    system=_SYSTEM_PROMPT,
                    messages=list(self.history),
                    temperature=0.3,
                    max_tokens=2048,
                )
            )
        except Exception as exc:  # noqa: BLE001
            self.memory.add_note(f"po LLM call failed: {exc}")
            await self.reply(
                envelope,
                UserReply(text=f"I hit an error talking to the model: {exc}"),
            )
            return

        self.history.append(Message(role="assistant", content=response.content))

        data = self._parse_response(response.content)
        if data is None:
            await self.reply(envelope, UserReply(text=response.content.strip()))
            return

        reply_text = (data.get("reply") or "").strip() or "(no reply)"
        await self.reply(envelope, UserReply(text=reply_text))

        handoff = data.get("handoff")
        if handoff and isinstance(handoff, dict):
            brief = (handoff.get("brief") or "").strip()
            if brief:
                await self._handoff(brief, envelope.from_agent)

    async def _handoff(self, brief: str, user_name: str) -> None:
        self.brief = brief
        self.user_name = user_name

        self.workspace.write(
            agent_name=self.name,
            agent_role=self.role,
            path="brief.md",
            content=brief,
            message="initial requirements brief",
        )
        self.memory.record_decision(
            summary="handed off to PM",
            rationale="brief captures app name, features, entities, screens",
        )

        self.workflow_id = f"wf-{uuid.uuid4().hex[:8]}"
        await self.send(
            to=self.pm_name,
            payload=TaskAssignment(
                task_id=self.workflow_id,
                description="ship the user's application",
                inputs={
                    "markdown": brief,
                    "provider": self.provider,
                    "model": self.model,
                    "api_key": self.api_key,
                    "max_tokens": self.max_tokens_budget,
                },
            ),
        )

    async def _on_pm_status(
        self, envelope: Envelope, payload: StatusUpdate
    ) -> None:
        if self.workflow_id is None or payload.task_id != self.workflow_id:
            return

        notes = payload.notes or ""
        if payload.status == "accepted":
            text = f"🛠 Team accepted: {notes}"
        elif payload.status == "in_progress":
            text = f"… {notes}"
        elif payload.status == "completed":
            text = f"✅ Done! {notes}"
            self.memory.complete_task(payload.task_id, "shipped to user")
        elif payload.status == "failed":
            text = f"❌ Failed: {notes}"
            self.memory.add_note(
                f"workflow {payload.task_id} failed at PM: {notes}"
            )
        else:
            text = f"[{payload.status}] {notes}"

        await self.send(to=self.user_name, payload=UserReply(text=text))

    @staticmethod
    def _parse_response(content: str) -> dict | None:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        raw = match.group(1) if match else content.strip()
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(obj, dict):
            return None
        return obj


__all__ = ["POAgent"]
