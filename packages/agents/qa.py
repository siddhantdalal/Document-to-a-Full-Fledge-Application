import os
import re
import subprocess
from pathlib import Path

from packages.agent_runtime import (
    Agent,
    Envelope,
    StatusUpdate,
    TaskAssignment,
)

_SUMMARY_RE = re.compile(r"=+ (.*?(?:passed|failed|error|warning).*?) =+")
_COUNT_RE = re.compile(
    r"(?:(\d+) passed)?[, ]*(?:(\d+) failed)?[, ]*(?:(\d+) error[s]?)?"
)


class QAAgent(Agent):
    """QA agent. Reads the generated project from the shared workspace and
    runs the generated pytest suite on the backend. Reports the outcome via
    StatusUpdate envelopes.

    TaskAssignment.inputs:
      - project_subpath: str (defaults to "project")
      - backend_subpath: str (defaults to "backend")
      - pytest_target:  str (defaults to "tests")
      - timeout_s:      int (defaults to 180)

    StatusUpdate sequence:
      accepted -> in_progress(running pytest) -> completed | failed
    """

    DEFAULT_ROLE = "qa"

    async def handle(self, envelope: Envelope) -> None:
        payload = envelope.payload
        if payload.kind == "task_assignment":
            await self._validate(envelope, payload)
        elif payload.kind == "heartbeat":
            return
        else:
            self.memory.add_note(
                f"qa ignoring unsupported payload kind={payload.kind} "
                f"from {envelope.from_agent}"
            )

    async def _validate(self, envelope: Envelope, payload: TaskAssignment) -> None:
        task_id = payload.task_id
        inputs = payload.inputs
        requester = envelope.from_agent

        project_subpath = inputs.get("project_subpath", "project")
        backend_subpath = inputs.get("backend_subpath", "backend")
        pytest_target = inputs.get("pytest_target", "tests")
        timeout_s = int(inputs.get("timeout_s", 180))

        async def status(value: str, notes: str) -> None:
            await self.send(
                to=requester,
                payload=StatusUpdate(
                    task_id=task_id,
                    status=value,  # type: ignore[arg-type]
                    notes=notes,
                ),
                in_reply_to=envelope.id,
            )

        backend = Path(self.workspace.root) / project_subpath / backend_subpath
        if not backend.exists():
            await status("failed", f"backend dir not found at {backend}")
            self.memory.add_note(f"task {task_id} aborted: no backend at {backend}")
            return

        tests = backend / pytest_target
        if not tests.exists():
            await status(
                "completed",
                f"no tests to run ({pytest_target} not present)",
            )
            self.memory.complete_task(task_id, "no tests present; treated as pass")
            return

        await status("accepted", "starting test run")
        await status("in_progress", f"running pytest in {backend}/{pytest_target}")

        try:
            result = self._run_pytest(backend, pytest_target, timeout_s)
        except subprocess.TimeoutExpired:
            await status("failed", f"pytest exceeded {timeout_s}s timeout")
            self.memory.add_note(f"task {task_id} pytest timed out")
            return
        except FileNotFoundError as exc:
            await status("failed", f"could not invoke pytest: {exc}")
            self.memory.add_note(f"task {task_id} pytest tool missing: {exc}")
            return

        summary = self._summary(result.stdout)
        counts = self._counts(result.stdout)
        details = self._failure_excerpt(result.stdout)

        if result.returncode == 0:
            await status(
                "completed",
                f"pytest passed: {summary} ({counts})",
            )
            self.memory.complete_task(
                task_id, f"all tests passed: {counts}"
            )
        else:
            tail = f" — {details}" if details else ""
            await status(
                "failed",
                f"pytest failed: {summary} ({counts}){tail}",
            )
            self.memory.add_note(
                f"task {task_id} pytest failed: {counts}; {details[:160]}"
            )

    def _run_pytest(
        self, backend: Path, target: str, timeout_s: int
    ) -> subprocess.CompletedProcess:
        env = {**os.environ, "PYTHONPATH": "."}
        return subprocess.run(
            ["python", "-m", "pytest", target, "-q", "--tb=short", "--no-header"],
            cwd=str(backend),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
        )

    @staticmethod
    def _summary(stdout: str) -> str:
        match = None
        for m in _SUMMARY_RE.finditer(stdout):
            match = m
        if match:
            return match.group(1).strip()
        # Fall back to last non-empty line
        for line in reversed(stdout.splitlines()):
            if line.strip():
                return line.strip()
        return "no summary"

    @staticmethod
    def _counts(stdout: str) -> str:
        passed = failed = errored = 0
        for line in stdout.splitlines():
            if "passed" in line or "failed" in line or "error" in line:
                m = _COUNT_RE.search(line)
                if m:
                    passed = max(passed, int(m.group(1) or 0))
                    failed = max(failed, int(m.group(2) or 0))
                    errored = max(errored, int(m.group(3) or 0))
        return f"{passed} passed, {failed} failed, {errored} errored"

    @staticmethod
    def _failure_excerpt(stdout: str, lines: int = 20) -> str:
        out: list[str] = []
        in_failures = False
        for line in stdout.splitlines():
            if line.startswith("FAILED ") or line.startswith("ERROR ") or "Error" in line:
                in_failures = True
            if in_failures:
                out.append(line)
                if len(out) >= lines:
                    break
        return "\n".join(out).strip()


__all__ = ["QAAgent"]
