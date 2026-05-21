import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Union


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(kw_only=True, frozen=True)
class TaskAssignment:
    kind: Literal["task_assignment"] = "task_assignment"
    task_id: str
    description: str
    inputs: dict[str, Any] = field(default_factory=dict)
    retry_budget: int = 3
    deadline_iso: str | None = None


@dataclass(kw_only=True, frozen=True)
class StatusUpdate:
    kind: Literal["status_update"] = "status_update"
    task_id: str
    status: Literal["accepted", "in_progress", "blocked", "completed", "failed"]
    artifact_uris: list[str] = field(default_factory=list)
    notes: str | None = None


@dataclass(kw_only=True, frozen=True)
class Question:
    kind: Literal["question"] = "question"
    topic: str
    context: str = ""


@dataclass(kw_only=True, frozen=True)
class Answer:
    kind: Literal["answer"] = "answer"
    content: str
    confidence: float = 1.0


@dataclass(kw_only=True, frozen=True)
class InfoRequest:
    kind: Literal["info_request"] = "info_request"
    what: str
    purpose: str = ""


@dataclass(kw_only=True, frozen=True)
class InfoResponse:
    kind: Literal["info_response"] = "info_response"
    content: str
    found: bool = True


@dataclass(kw_only=True, frozen=True)
class Blocker:
    kind: Literal["blocker"] = "blocker"
    task_id: str
    blocker: str
    options: list[str] = field(default_factory=list)


@dataclass(kw_only=True, frozen=True)
class DecisionRequest:
    kind: Literal["decision_request"] = "decision_request"
    question: str
    options: list[str] = field(default_factory=list)
    impact: str = ""


@dataclass(kw_only=True, frozen=True)
class UserMessage:
    kind: Literal["user_message"] = "user_message"
    text: str


@dataclass(kw_only=True, frozen=True)
class UserReply:
    kind: Literal["user_reply"] = "user_reply"
    text: str


@dataclass(kw_only=True, frozen=True)
class Heartbeat:
    kind: Literal["heartbeat"] = "heartbeat"
    note: str = ""


Payload = Union[
    TaskAssignment,
    StatusUpdate,
    Question,
    Answer,
    InfoRequest,
    InfoResponse,
    Blocker,
    DecisionRequest,
    UserMessage,
    UserReply,
    Heartbeat,
]


@dataclass(kw_only=True, frozen=True)
class Envelope:
    id: str
    from_agent: str
    to_agent: str
    project_id: str
    created_at: str
    payload: Payload
    in_reply_to: str | None = None


def new_envelope(
    *,
    from_agent: str,
    to_agent: str,
    project_id: str,
    payload: Payload,
    in_reply_to: str | None = None,
) -> Envelope:
    return Envelope(
        id=uuid.uuid4().hex,
        from_agent=from_agent,
        to_agent=to_agent,
        project_id=project_id,
        created_at=now_iso(),
        payload=payload,
        in_reply_to=in_reply_to,
    )


__all__ = [
    "Answer",
    "Blocker",
    "DecisionRequest",
    "Envelope",
    "Heartbeat",
    "InfoRequest",
    "InfoResponse",
    "Payload",
    "Question",
    "StatusUpdate",
    "TaskAssignment",
    "UserMessage",
    "UserReply",
    "new_envelope",
    "now_iso",
]
