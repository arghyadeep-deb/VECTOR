import sys
import uuid
import asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase
from core.loop.permission_gateway import PermissionGateway, Action


class GitBot(AgentBase):
    """Automates git operations: commit, push, branch, PR creation."""

    def __init__(self, ghost: dict = None):
        super().__init__(str(uuid.uuid4()), "GitBot", "coding")
        if ghost:
            self.inherit_ghost(ghost)
        self._gateway = PermissionGateway()
        logger.info("[VECTOR][git_bot] GitBot initialized")

    def _get_repo(self, repo_path: str):
        """Lazy-import gitpython and return Repo object or None."""
        try:
            from git import Repo, InvalidGitRepositoryError
            return Repo(repo_path)
        except Exception as e:
            logger.error(f"[VECTOR][git_bot] Repo open failed for '{repo_path}': {e}")
            return None

    def get_status(self, repo_path: str = ".") -> dict:
        """
        Return current git status for a repo.
        Returns {branch, modified, staged, untracked, ahead, behind} or {} on error.
        """
        try:
            repo = self._get_repo(repo_path)
            if repo is None:
                return {}

            branch = repo.active_branch.name if not repo.head.is_detached else "DETACHED"

            modified = [item.a_path for item in repo.index.diff(None)]
            staged = [item.a_path for item in repo.index.diff("HEAD")]
            untracked = repo.untracked_files

            ahead = 0
            behind = 0
            try:
                tracking = repo.active_branch.tracking_branch()
                if tracking:
                    commits_ahead = list(repo.iter_commits(f"{tracking}..HEAD"))
                    commits_behind = list(repo.iter_commits(f"HEAD..{tracking}"))
                    ahead = len(commits_ahead)
                    behind = len(commits_behind)
            except Exception as e:
                logger.warning(f"[VECTOR][git_bot] Could not determine ahead/behind: {e}")

            status = {
                "branch": branch,
                "modified": modified,
                "staged": staged,
                "untracked": list(untracked),
                "ahead": ahead,
                "behind": behind,
            }
            logger.info(f"[VECTOR][git_bot] Status on '{branch}': {len(modified)} modified, {len(staged)} staged, {len(untracked)} untracked")
            self.award_points(5, "get_status_success")
            return status
        except Exception as e:
            logger.error(f"[VECTOR][git_bot] get_status error: {e}")
            self.deduct_points(5, "get_status_failed")
            return {}

    async def commit(self, message: str, files: list = None, repo_path: str = ".") -> dict:
        """
        Stage files (or all modified/untracked) and create a commit.
        Returns {success: bool, hash: str, message: str}.
        RULE 3: commit_code is YELLOW — gateway is awaited directly (not fire-and-forget).
        RULE 8: reasoning chain stored on every commit.
        """
        try:
            repo = await asyncio.to_thread(self._get_repo, repo_path)
            if repo is None:
                return {"success": False, "hash": "", "message": "Repo not found"}

            if files:
                await asyncio.to_thread(repo.index.add, files)
                logger.info(f"[VECTOR][git_bot] Staged {len(files)} files: {files}")
            else:
                await asyncio.to_thread(repo.git.add, A=True)
                logger.info("[VECTOR][git_bot] Staged all changes (git add -A)")

            # Check if there's anything to commit
            has_staged = await asyncio.to_thread(lambda: bool(repo.index.diff("HEAD") or repo.untracked_files))
            if not has_staged:
                try:
                    diff_staged = await asyncio.to_thread(repo.git.diff, "--cached", "--name-only")
                    if not diff_staged:
                        logger.warning("[VECTOR][git_bot] Nothing to commit")
                        return {"success": False, "hash": "", "message": "Nothing to commit"}
                except Exception:
                    pass

            commit_obj = await asyncio.to_thread(repo.index.commit, message)
            commit_hash = commit_obj.hexsha[:8]
            logger.info(f"[VECTOR][git_bot] Committed {commit_hash}: {message}")
            self.award_points(20, "commit_success")

            # RULE 3 — await gateway directly so audit trail is guaranteed (not fire-and-forget)
            await self._gateway.execute(Action(
                action_type="commit_code",
                params={"hash": commit_hash, "message": message},
                proposed_by=self.name,
            ))

            # RULE 8 — store reasoning chain
            try:
                from core.memory.episodic import EpisodicMemory
                EpisodicMemory().store_chain(
                    situation=f"git_commit:{repo_path}",
                    goal_ids=["coding", "auto_commit"],
                    steps=["stage_files", "create_commit", "gateway_audit"],
                    action="commit_code",
                    outcome=commit_hash,
                    reward=1.0,
                )
            except Exception as _chain_err:
                logger.warning(f"[VECTOR][git_bot] store_chain failed: {_chain_err}")

            return {"success": True, "hash": commit_hash, "message": message}
        except Exception as e:
            logger.error(f"[VECTOR][git_bot] commit error: {e}")
            self.deduct_points(20, "commit_failed")
            return {"success": False, "hash": "", "message": str(e)}

    def get_recent_commits(self, n: int = 10, repo_path: str = ".") -> list:
        """
        Return last n commits as [{hash, message, author, date}].
        """
        try:
            repo = self._get_repo(repo_path)
            if repo is None:
                return []

            commits = []
            for c in list(repo.iter_commits("HEAD", max_count=n)):
                commits.append({
                    "hash": c.hexsha[:8],
                    "message": c.message.strip(),
                    "author": str(c.author),
                    "date": c.committed_datetime.isoformat(),
                })
            logger.info(f"[VECTOR][git_bot] Fetched {len(commits)} recent commits")
            return commits
        except Exception as e:
            logger.error(f"[VECTOR][git_bot] get_recent_commits error: {e}")
            return []

    def create_branch(self, name: str, repo_path: str = ".") -> dict:
        """
        Create and checkout a new branch.
        Returns {success: bool, branch: str, message: str}.
        """
        try:
            repo = self._get_repo(repo_path)
            if repo is None:
                return {"success": False, "branch": "", "message": "Repo not found"}

            new_branch = repo.create_head(name)
            new_branch.checkout()
            logger.info(f"[VECTOR][git_bot] Created and checked out branch '{name}'")
            self.award_points(10, "branch_created")
            return {"success": True, "branch": name, "message": f"Branch '{name}' created and checked out"}
        except Exception as e:
            logger.error(f"[VECTOR][git_bot] create_branch error: {e}")
            self.deduct_points(10, "branch_create_failed")
            return {"success": False, "branch": "", "message": str(e)}

    async def create_pr(self, title: str, body: str, base: str = "main") -> dict:
        """
        Create a GitHub PR using PyGithub. Reads GITHUB_TOKEN from CONFIG.
        push_github is RED — requires owner confirmation via gateway.
        Returns {url, number} or {error: ...}.
        """
        try:
            # Gate through permission gateway (RED — push_github)
            gate_result = await self._gateway.execute(Action(
                action_type="push_github",
                params={"title": title, "base": base},
                proposed_by=self.name,
            ))
            if not gate_result.approved:
                logger.warning(f"[VECTOR][git_bot] PR creation blocked by gateway: {gate_result.reason}")
                return {"error": f"Gateway blocked: {gate_result.reason}"}

            token = CONFIG["api_keys"].get("github_token", "")
            if not token:
                import os
                token = os.getenv("GITHUB_TOKEN", "")
            if not token:
                logger.error("[VECTOR][git_bot] GITHUB_TOKEN not configured")
                return {"error": "GITHUB_TOKEN not configured"}

            from github import Github
            g = Github(token)

            # Determine repo from current directory's remote URL
            try:
                repo = self._get_repo(".")
                if repo is None:
                    return {"error": "No git repo at '.'"}
                remote_url = repo.remotes.origin.url
                # Parse owner/repo from URL (https or ssh)
                # https://github.com/owner/repo.git  or  git@github.com:owner/repo.git
                if "github.com/" in remote_url:
                    parts = remote_url.split("github.com/")[-1].rstrip(".git").rstrip("/")
                elif "github.com:" in remote_url:
                    parts = remote_url.split("github.com:")[-1].rstrip(".git").rstrip("/")
                else:
                    return {"error": f"Cannot parse GitHub repo from remote URL: {remote_url}"}

                gh_repo = g.get_repo(parts)
                head_branch = repo.active_branch.name
            except Exception as e:
                logger.error(f"[VECTOR][git_bot] Could not determine remote repo: {e}")
                return {"error": str(e)}

            pr = gh_repo.create_pull(title=title, body=body, head=head_branch, base=base)
            logger.info(f"[VECTOR][git_bot] PR #{pr.number} created: {pr.html_url}")
            self.award_points(30, "pr_created")
            return {"url": pr.html_url, "number": pr.number}
        except Exception as e:
            logger.error(f"[VECTOR][git_bot] create_pr error: {e}")
            self.deduct_points(20, "pr_create_failed")
            return {"error": str(e)}


    async def generate_commit_message_vc(self, diff_summary: str) -> str:
        """
        Generate a semantic commit message via VectorCode.
        Falls back to generic message if VectorCode unavailable.
        """
        try:
            from integrations.vectorcode_bridge import get_bridge
            bridge = get_bridge()
            if not bridge.is_available():
                return f"auto: {diff_summary[:60]}"
            task = (
                f"Write a concise git commit message (one line, max 72 chars) for this change: {diff_summary[:300]}. "
                f"Follow conventional commits format: type(scope): description. "
                f"Reply with ONLY the commit message, nothing else."
            )
            result = await bridge.run_task(task, mode="run", timeout=60)
            if result.get("status") == "ok" and result.get("output"):
                msg = result["output"].strip().split("\n")[0][:72]
                return msg
        except Exception as e:
            logger.warning(f"[VECTOR][git_bot] VectorCode commit message failed: {e}")
        return f"auto: {diff_summary[:60]}"

    async def run(self, task: dict) -> dict:
        """Governor dispatch interface."""
        t = task.get("type", "")
        p = task.get("params", {})
        if t in ("commit_code", "git_commit"):
            return self.commit(p.get("message", "VECTOR auto-commit"), repo_path=p.get("repo", "."))
        if t in ("git_status", "check_git"):
            return self.get_status(p.get("repo", "."))
        if t in ("git_log", "recent_commits"):
            return {"commits": self.get_recent_commits(p.get("n", 5), p.get("repo", "."))}
        if t in ("create_branch",):
            return self.create_branch(p.get("name", "vector-branch"), p.get("repo", "."))
        if t in ("analyze_codebase", "gitnexus"):
            return await self.analyze_with_gitnexus(p.get("repo", "."))
        return {"status": "ok", "agent": self.name, "task": t}

    async def analyze_with_gitnexus(self, repo_path: str = ".") -> dict:
        """
        Use GitNexus to build a codebase knowledge graph and return impact analysis.
        GitNexus runs as an MCP server via npx — this calls it via subprocess for standalone use.
        For MCP-integrated use, GitNexus is available as an MCP tool in .mcp.json.
        """
        try:
            import subprocess
            result = subprocess.run(
                ["npx", "-y", "gitnexus@latest", "analyze", "--repo", repo_path, "--format", "json"],
                capture_output=True, text=True, timeout=60,
                cwd=repo_path,
            )
            if result.returncode == 0:
                import json
                try:
                    data = json.loads(result.stdout)
                    self.award_points(15, "gitnexus_analysis")
                    return {"status": "ok", "analysis": data}
                except Exception:
                    return {"status": "ok", "output": result.stdout[:2000]}
            else:
                logger.warning(f"[VECTOR][git_bot] GitNexus failed: {result.stderr[:200]}")
                return {"status": "error", "error": result.stderr[:200]}
        except FileNotFoundError:
            return {"status": "not_installed", "note": "Install Node.js to use GitNexus: npx gitnexus@latest"}
        except Exception as e:
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    import os
    # Use the VECTOR codebase repo itself for testing
    REPO_PATH = str(Path(__file__).parent.parent.parent.parent)

    bot = GitBot()

    # Smoke test 1: get_status
    status = bot.get_status(REPO_PATH)
    status_ok = isinstance(status, dict) and "branch" in status
    print(f"  get_status: branch={status.get('branch')}, modified={len(status.get('modified', []))}, "
          f"staged={len(status.get('staged', []))}, untracked={len(status.get('untracked', []))}")

    # Smoke test 2: get_recent_commits
    commits = bot.get_recent_commits(n=3, repo_path=REPO_PATH)
    commits_ok = isinstance(commits, list)
    print(f"  recent_commits ({len(commits)}): {[c['hash'] for c in commits]}")

    # Smoke test 3: agent state
    agent_ok = bot.health_points > 0 and bot.name == "GitBot"

    all_ok = status_ok and commits_ok and agent_ok
    print("✅ git_bot.py OK" if all_ok else "❌ FAILED")
