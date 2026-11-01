"""Post-edit safety checks for VECTOR development tasks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from models import RiskLevel


@dataclass(frozen=True, slots=True)
class PostflightFinding:
    path: str
    risk: RiskLevel
    reason: str


@dataclass(frozen=True, slots=True)
class PostflightDecision:
    risk: RiskLevel
    requires_human: bool
    findings: tuple[PostflightFinding, ...]


class PostflightGuard:
    """Classify changed paths after an implementation step."""

    _EXACT_RULES: dict[str, tuple[RiskLevel, str]] = {
        "requirements.txt": (
            RiskLevel.HIGH,
            "Dependency manifest changed.",
        ),
        "pyproject.toml": (
            RiskLevel.HIGH,
            "Python project/dependency configuration changed.",
        ),
        "package.json": (
            RiskLevel.HIGH,
            "Node dependency manifest changed.",
        ),
        "package-lock.json": (
            RiskLevel.HIGH,
            "Node dependency lockfile changed.",
        ),
        "pnpm-lock.yaml": (
            RiskLevel.HIGH,
            "Node dependency lockfile changed.",
        ),
        "yarn.lock": (
            RiskLevel.HIGH,
            "Node dependency lockfile changed.",
        ),
        "poetry.lock": (
            RiskLevel.HIGH,
            "Python dependency lockfile changed.",
        ),
        "uv.lock": (
            RiskLevel.HIGH,
            "Python dependency lockfile changed.",
        ),
        ".env": (
            RiskLevel.CRITICAL,
            "Environment/credential file changed.",
        ),
        ".env.local": (
            RiskLevel.CRITICAL,
            "Environment/credential file changed.",
        ),
    }

    _PREFIX_RULES: tuple[
        tuple[str, RiskLevel, str],
        ...
    ] = (
        (
            ".github/workflows/",
            RiskLevel.HIGH,
            "CI/CD workflow changed.",
        ),
        (
            "migrations/",
            RiskLevel.CRITICAL,
            "Database migration changed.",
        ),
        (
            "alembic/",
            RiskLevel.CRITICAL,
            "Database migration changed.",
        ),
        (
            "deploy/",
            RiskLevel.CRITICAL,
            "Deployment configuration changed.",
        ),
        (
            "certs/",
            RiskLevel.CRITICAL,
            "Certificate/security material changed.",
        ),
        (
            "config/security/",
            RiskLevel.CRITICAL,
            "Security configuration changed.",
        ),
        (
            "core/security/",
            RiskLevel.CRITICAL,
            "Security subsystem changed.",
        ),
        (
            "core/auth/",
            RiskLevel.CRITICAL,
            "Authentication subsystem changed.",
        ),
        (
            "core/permissions/",
            RiskLevel.CRITICAL,
            "Permission subsystem changed.",
        ),
    )

    _SEGMENT_RULES: tuple[
        tuple[str, RiskLevel, str],
        ...
    ] = (
        (
            "permission_gateway",
            RiskLevel.CRITICAL,
            "Permission Gateway implementation changed.",
        ),
        (
            "authentication",
            RiskLevel.CRITICAL,
            "Authentication code changed.",
        ),
        (
            "authorization",
            RiskLevel.CRITICAL,
            "Authorization code changed.",
        ),
        (
            "credentials",
            RiskLevel.CRITICAL,
            "Credential-related path changed.",
        ),
        (
            "secrets",
            RiskLevel.CRITICAL,
            "Secret-handling path changed.",
        ),
        (
            "database",
            RiskLevel.HIGH,
            "Database-related code changed.",
        ),
        (
            "schema",
            RiskLevel.HIGH,
            "Schema-related code changed.",
        ),
    )

    def evaluate(
        self,
        changed_files: list[str],
    ) -> PostflightDecision:
        findings: list[PostflightFinding] = []

        highest = RiskLevel.LOW

        for raw_path in changed_files:
            normalized = self._normalize(raw_path)

            exact = self._EXACT_RULES.get(normalized)

            if exact is not None:
                risk, reason = exact

                findings.append(
                    PostflightFinding(
                        path=normalized,
                        risk=risk,
                        reason=reason,
                    )
                )

                highest = self._max_risk(
                    highest,
                    risk,
                )

            for prefix, risk, reason in self._PREFIX_RULES:
                if normalized.startswith(prefix):
                    findings.append(
                        PostflightFinding(
                            path=normalized,
                            risk=risk,
                            reason=reason,
                        )
                    )

                    highest = self._max_risk(
                        highest,
                        risk,
                    )

            segments = {
                segment.lower()
                for segment in PurePosixPath(
                    normalized
                ).parts
            }

            stem = PurePosixPath(
                normalized
            ).stem.lower()

            searchable = segments | {stem}

            for token, risk, reason in self._SEGMENT_RULES:
                if token in searchable:
                    findings.append(
                        PostflightFinding(
                            path=normalized,
                            risk=risk,
                            reason=reason,
                        )
                    )

                    highest = self._max_risk(
                        highest,
                        risk,
                    )

        deduped = self._dedupe(findings)

        return PostflightDecision(
            risk=highest,
            requires_human=highest in {
                RiskLevel.HIGH,
                RiskLevel.CRITICAL,
            },
            findings=tuple(deduped),
        )

    @staticmethod
    def _normalize(path: str) -> str:
        normalized = path.replace("\\", "/").strip()

        while normalized.startswith("./"):
            normalized = normalized[2:]

        return normalized.lower()

    @staticmethod
    def _dedupe(
        findings: list[PostflightFinding],
    ) -> list[PostflightFinding]:
        seen: set[
            tuple[str, RiskLevel, str]
        ] = set()

        result: list[PostflightFinding] = []

        for finding in findings:
            key = (
                finding.path,
                finding.risk,
                finding.reason,
            )

            if key in seen:
                continue

            seen.add(key)
            result.append(finding)

        return result

    @staticmethod
    def _max_risk(
        current: RiskLevel,
        candidate: RiskLevel,
    ) -> RiskLevel:
        order = {
            RiskLevel.LOW: 0,
            RiskLevel.MEDIUM: 1,
            RiskLevel.HIGH: 2,
            RiskLevel.CRITICAL: 3,
        }

        if order[candidate] > order[current]:
            return candidate

        return current


def _self_test() -> None:
    guard = PostflightGuard()

    safe = guard.evaluate(
        [
            "core/parser.py",
            "tests/test_parser.py",
        ]
    )

    assert safe.risk is RiskLevel.LOW
    assert not safe.requires_human
    assert safe.findings == ()

    dependency = guard.evaluate(
        [
            "package.json",
            "frontend/app.tsx",
        ]
    )

    assert dependency.risk is RiskLevel.HIGH
    assert dependency.requires_human
    assert any(
        finding.path == "package.json"
        for finding in dependency.findings
    )

    security = guard.evaluate(
        [
            "core/security/token_manager.py",
        ]
    )

    assert security.risk is RiskLevel.CRITICAL
    assert security.requires_human

    permission_gateway = guard.evaluate(
        [
            r"core\permission_gateway.py",
        ]
    )

    assert permission_gateway.risk is RiskLevel.CRITICAL
    assert permission_gateway.requires_human

    migration = guard.evaluate(
        [
            "migrations/0042_add_goal_index.py",
        ]
    )

    assert migration.risk is RiskLevel.CRITICAL
    assert migration.requires_human


if __name__ == "__main__":
    _self_test()
