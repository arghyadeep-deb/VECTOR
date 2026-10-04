"""Regression for vectorcode/src/gateway/platforms/webhook.py.

Bugs fixed this cycle:

1. stdlib `logging` instead of loguru (CLAUDE.md rule 6) -- `import
   logging` + `logger = logging.getLogger(__name__)`, plus ~20
   printf-style (%s/%d/%r) placeholders that loguru's `{}`-style
   formatting silently fails to substitute.

2. CLI argument injection (CWE-88) in `_deliver_github_comment()`:
   `repo`/`pr_number` are rendered from the webhook POST payload via
   `_render_delivery_extra()` (whoever holds the route's HMAC secret
   controls the substituted values). `pr_number` was passed as a bare
   positional `gh pr comment <pr_number> --repo <repo> --body <content>`
   with no validation -- a value like "--repo=attacker/repo" could be
   parsed as a flag instead of the PR number, redirecting the comment.
   Fixed by requiring pr_number to be strictly digits and repo to match
   an owner/repo shape before ever reaching subprocess.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "vectorcode" / "src"))

import pytest

from gateway.config import PlatformConfig
from gateway.platforms.webhook import WebhookAdapter


def _adapter(**extra) -> WebhookAdapter:
    return WebhookAdapter(PlatformConfig(enabled=True, extra=extra))


def test_module_uses_loguru_not_stdlib_logging():
    import inspect
    from gateway.platforms import webhook
    src = inspect.getsource(webhook)
    assert "import logging" not in src
    assert "from loguru import logger" in src
    assert "%s" not in src and "%d" not in src and "%r" not in src


@pytest.mark.asyncio
async def test_github_comment_rejects_non_numeric_pr_number():
    adapter = _adapter()
    result = await adapter._deliver_github_comment(
        "hello",
        {"deliver_extra": {"repo": "owner/repo", "pr_number": "--repo=attacker/repo"}},
    )
    assert result.success is False
    assert "Invalid pr_number" in (result.error or "")


@pytest.mark.asyncio
async def test_github_comment_rejects_malformed_repo():
    adapter = _adapter()
    result = await adapter._deliver_github_comment(
        "hello",
        {"deliver_extra": {"repo": "--repo evil/repo", "pr_number": "42"}},
    )
    assert result.success is False
    assert "Invalid repo" in (result.error or "")


@pytest.mark.asyncio
async def test_github_comment_accepts_valid_numeric_pr_number(monkeypatch):
    adapter = _adapter()

    calls = {}

    def _fake_run(cmd, **kwargs):
        calls["cmd"] = cmd
        class _R:
            returncode = 0
            stderr = ""
        return _R()

    import gateway.platforms.webhook as webhook_mod
    monkeypatch.setattr(webhook_mod.subprocess, "run", _fake_run)

    result = await adapter._deliver_github_comment(
        "hello", {"deliver_extra": {"repo": "owner/repo", "pr_number": "42"}}
    )
    assert result.success is True
    assert calls["cmd"][3] == "42"
    assert calls["cmd"][4:6] == ["--repo", "owner/repo"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
