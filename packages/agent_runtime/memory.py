import json
from dataclasses import asdict, dataclass, field

from packages.agent_runtime.messages import now_iso


@dataclass
class Decision:
    summary: str
    rationale: str
    timestamp: str
    related_task: str | None = None


@dataclass
class OpenQuestion:
    text: str
    asked_at: str
    waiting_on: str | None = None


@dataclass
class CompletedTask:
    task_id: str
    summary: str
    completed_at: str


@dataclass
class AgentMemory:
    decisions: list[Decision] = field(default_factory=list)
    open_questions: list[OpenQuestion] = field(default_factory=list)
    completed_tasks: list[CompletedTask] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def record_decision(
        self, summary: str, rationale: str, related_task: str | None = None
    ) -> Decision:
        decision = Decision(
            summary=summary,
            rationale=rationale,
            timestamp=now_iso(),
            related_task=related_task,
        )
        self.decisions.append(decision)
        return decision

    def add_question(self, text: str, waiting_on: str | None = None) -> OpenQuestion:
        question = OpenQuestion(text=text, asked_at=now_iso(), waiting_on=waiting_on)
        self.open_questions.append(question)
        return question

    def resolve_question(self, text: str) -> bool:
        before = len(self.open_questions)
        self.open_questions = [q for q in self.open_questions if q.text != text]
        return len(self.open_questions) != before

    def complete_task(self, task_id: str, summary: str) -> CompletedTask:
        task = CompletedTask(task_id=task_id, summary=summary, completed_at=now_iso())
        self.completed_tasks.append(task)
        return task

    def add_note(self, note: str) -> None:
        self.notes.append(note)

    def to_dict(self) -> dict:
        return {
            "decisions": [asdict(d) for d in self.decisions],
            "open_questions": [asdict(q) for q in self.open_questions],
            "completed_tasks": [asdict(t) for t in self.completed_tasks],
            "notes": list(self.notes),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentMemory":
        return cls(
            decisions=[Decision(**d) for d in data.get("decisions", [])],
            open_questions=[OpenQuestion(**q) for q in data.get("open_questions", [])],
            completed_tasks=[CompletedTask(**t) for t in data.get("completed_tasks", [])],
            notes=list(data.get("notes", [])),
        )

    @classmethod
    def from_json(cls, payload: str) -> "AgentMemory":
        return cls.from_dict(json.loads(payload))


__all__ = ["AgentMemory", "CompletedTask", "Decision", "OpenQuestion"]
