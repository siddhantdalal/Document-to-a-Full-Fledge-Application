import fnmatch
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from packages.agent_runtime.exceptions import OwnershipViolation
from packages.agent_runtime.messages import now_iso


@dataclass(frozen=True)
class WorkspaceCommit:
    id: str
    agent_name: str
    agent_role: str
    paths: tuple[str, ...]
    message: str
    created_at: str


class OwnershipPolicy:
    """Maps agent roles to globs of paths they may write."""

    def __init__(self, rules: dict[str, list[str]] | None = None) -> None:
        self.rules = rules or {}

    def can_write(self, agent_role: str, path: str) -> bool:
        if not self.rules:
            return True
        patterns = self.rules.get(agent_role, [])
        return any(fnmatch.fnmatch(path, pat) for pat in patterns)


DEFAULT_OWNERSHIP = OwnershipPolicy(
    {
        "product_owner": ["brief.md", "audit/**"],
        "project_manager": ["plan/**", "audit/**"],
        "business_analyst": ["spec.json", "audit/**"],
        "solution_architect": ["adr/**", "audit/**"],
        "designer": ["designs/**", "audit/**"],
        "backend_developer": ["backend/**", "audit/**"],
        "frontend_developer": ["frontend/**", "audit/**"],
        "qa": ["tests/**", "qa/**", "audit/**"],
        "devops": ["infra/**", "Dockerfile", "docker-compose.yml", "audit/**"],
        "cybersecurity": ["security/**", "audit/**"],
        "performance_engineer": ["perf/**", "audit/**"],
        "technical_writer": ["docs/**", "audit/**"],
        "compliance_officer": ["compliance/**", "audit/**"],
        "data_scientist": ["data/**", "ml/**", "audit/**"],
        "junior_developer": ["backend/**", "frontend/**", "audit/**"],
    }
)


class Workspace:
    def __init__(
        self,
        project_id: str,
        root: Path,
        policy: OwnershipPolicy | None = None,
    ) -> None:
        self.project_id = project_id
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.policy = policy or OwnershipPolicy()
        self._commits: list[WorkspaceCommit] = []

    def write(
        self,
        *,
        agent_name: str,
        agent_role: str,
        path: str,
        content: str | bytes,
        message: str,
    ) -> WorkspaceCommit:
        if not self.policy.can_write(agent_role, path):
            raise OwnershipViolation(agent_role=agent_role, path=path)

        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")

        commit = WorkspaceCommit(
            id=uuid.uuid4().hex,
            agent_name=agent_name,
            agent_role=agent_role,
            paths=(path,),
            message=message,
            created_at=now_iso(),
        )
        self._commits.append(commit)
        return commit

    def read_text(self, path: str) -> str:
        return (self.root / path).read_text(encoding="utf-8")

    def read_bytes(self, path: str) -> bytes:
        return (self.root / path).read_bytes()

    def exists(self, path: str) -> bool:
        return (self.root / path).exists()

    def list_files(self, glob: str = "**/*") -> list[str]:
        return sorted(
            str(p.relative_to(self.root))
            for p in self.root.glob(glob)
            if p.is_file()
        )

    def commits(self) -> list[WorkspaceCommit]:
        return list(self._commits)

    def commits_by_agent(self, agent_name: str) -> list[WorkspaceCommit]:
        return [c for c in self._commits if c.agent_name == agent_name]

    def commits_touching(self, path: str) -> list[WorkspaceCommit]:
        return [c for c in self._commits if path in c.paths]

    def snapshot(
        self,
        *,
        agent_name: str,
        agent_role: str,
        message: str,
        glob: str = "**/*",
    ) -> WorkspaceCommit:
        """Record a single commit listing every existing file matching glob.
        Useful when files were created outside Workspace.write (e.g. by a
        subprocess or a code generator that writes the filesystem directly)."""
        paths = tuple(self.list_files(glob))
        commit = WorkspaceCommit(
            id=uuid.uuid4().hex,
            agent_name=agent_name,
            agent_role=agent_role,
            paths=paths,
            message=message,
            created_at=now_iso(),
        )
        self._commits.append(commit)
        return commit


__all__ = ["DEFAULT_OWNERSHIP", "OwnershipPolicy", "Workspace", "WorkspaceCommit"]
