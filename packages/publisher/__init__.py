import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

GITHUB_API = "https://api.github.com"


class PushError(Exception):
    pass


@dataclass
class PushResult:
    repo_url: str
    branch: str
    commit_sha: str


_REPO_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _redact_token(text: str, token: str) -> str:
    if not token:
        return text
    return text.replace(token, "***")


def _gh(method: str, path: str, token: str, json: dict | None = None) -> httpx.Response:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    return httpx.request(method, f"{GITHUB_API}{path}", headers=headers, json=json, timeout=30)


def get_current_user(token: str) -> str:
    r = _gh("GET", "/user", token)
    if r.status_code == 401:
        raise PushError("GitHub token rejected (401).")
    if r.status_code != 200:
        raise PushError(f"GitHub /user failed: {r.status_code}")
    return r.json()["login"]


def repo_exists(owner: str, repo: str, token: str) -> bool:
    r = _gh("GET", f"/repos/{owner}/{repo}", token)
    if r.status_code == 200:
        return True
    if r.status_code == 404:
        return False
    raise PushError(f"GitHub repo check failed: {r.status_code}")


def create_repo(name: str, owner: str, current_user: str, token: str, private: bool) -> str:
    payload = {"name": name, "private": private, "auto_init": False}
    path = "/user/repos" if owner == current_user else f"/orgs/{owner}/repos"
    r = _gh("POST", path, token, json=payload)
    if r.status_code in (201, 200):
        return r.json()["clone_url"]
    if r.status_code == 422:
        raise PushError(f"Repo {owner}/{name} already exists or is invalid.")
    if r.status_code in (401, 403):
        raise PushError(f"GitHub denied repo creation under {owner} ({r.status_code}).")
    raise PushError(f"GitHub repo create failed: {r.status_code}")


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "GIT_TERMINAL_PROMPT": "0",
    }
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )


def _git_or_raise(args: list[str], cwd: Path, error_label: str, token: str | None = None) -> str:
    result = _git(args, cwd)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        if token:
            message = _redact_token(message, token)
        raise PushError(f"{error_label}: {message}")
    return result.stdout


def push_to_github(
    project_dir: Path,
    token: str,
    owner: str,
    repo: str,
    private: bool = True,
    commit_message: str = "Initial commit",
    branch: str = "main",
) -> PushResult:
    project_dir = Path(project_dir)
    if not project_dir.exists():
        raise PushError(f"project_dir {project_dir} does not exist.")
    if not (project_dir / "README.md").exists():
        raise PushError("project_dir does not look like a generated project (no README.md).")
    if not _REPO_RE.match(repo) or not _REPO_RE.match(owner):
        raise PushError("Owner and repo name must contain only letters, digits, '.', '-', or '_'.")

    current_user = get_current_user(token)

    if repo_exists(owner, repo, token):
        raise PushError(f"Repo {owner}/{repo} already exists. Choose a new name.")
    create_repo(repo, owner, current_user, token, private)

    git_dir = project_dir / ".git"
    if git_dir.exists():
        shutil.rmtree(git_dir)

    _git_or_raise(["init", "-q", "-b", branch], project_dir, "git init failed", token=token)
    _git_or_raise(
        ["config", "user.email", f"{current_user}@users.noreply.github.com"],
        project_dir,
        "git config email failed",
        token=token,
    )
    _git_or_raise(
        ["config", "user.name", current_user], project_dir, "git config name failed", token=token
    )
    _git_or_raise(["add", "-A"], project_dir, "git add failed", token=token)
    _git_or_raise(
        ["-c", "commit.gpgsign=false", "commit", "-q", "-m", commit_message],
        project_dir,
        "git commit failed",
        token=token,
    )

    push_url = f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"
    _git_or_raise(
        ["push", "-q", push_url, f"{branch}:{branch}"],
        project_dir,
        "git push failed",
        token=token,
    )

    sha = _git_or_raise(
        ["rev-parse", "HEAD"], project_dir, "git rev-parse failed", token=token
    ).strip()
    return PushResult(
        repo_url=f"https://github.com/{owner}/{repo}",
        branch=branch,
        commit_sha=sha,
    )


__all__ = [
    "PushError",
    "PushResult",
    "create_repo",
    "get_current_user",
    "push_to_github",
    "repo_exists",
]
