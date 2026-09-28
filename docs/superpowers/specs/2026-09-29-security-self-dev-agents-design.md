# Security Self-Development Agents Design

## Scope approval

The owner's 2026-09-29 approval note authorizes this security-district package.
The package remains defensive and analysis-only. In particular, no generated
patch may be applied or executed by these agents.

## Existing implementation matches

The selected `claude-security` coordinator and exploration roles already map
to the registered Security district pipeline: `ThreatScout`, `MalwareHunter`,
`NodeGuard`, `SkillSpector`, `ThreatDetectionEngineer`, `DetectionRules`,
`SIEMPipeline`, `AlertManager`, and `IncidentPlaybookRunner`. The selected scan
redactor maps to the registered `DataRedactor`. These implementations remain
authoritative; aliases would duplicate working detection and redaction logic.

No Solidity, Vyper, Move, Cairo, Foundry, Hardhat, Truffle, or Brownie source
exists in this worktree. A blockchain-security auditor would therefore have no
VECTOR-verifiable audit subject and will not be fabricated. It is reported as
`NEEDS_HUMAN`.

## New specialists

Eight bounded `AgentBase` subclasses will live in
`districts/security/security_specialists.py`:

- patch proposal generator;
- patch proposal verifier;
- scan inventory analyst;
- scan result loader;
- scan research verifier;
- scan coverage verifier;
- agent identity and trust analyst;
- automation governance analyst.

Each agent exposes a unique `<x>_brief` and `<x>_check` pair. Briefs declare
the evidence contract. Checks perform deterministic validation over
caller-supplied data: JSON parsing, hashing, unified-diff parsing, coverage
comparison, timestamp/scope checks, provenance checks, or governance control
scoring. Missing or unverifiable evidence produces `needs_human`.

The patch generator only constructs an in-memory unified-diff proposal from
explicit before/after text. The patch verifier only parses a proposal and
caller-supplied verification results. Neither class reads or writes a target
file, imports an execution library, runs tests or commands, invokes a shell,
applies a diff, commits, or merges. Outputs explicitly state that human or
PermissionGateway action is required.

## Routing and safety

All sixteen new actions have zero target/system/business-data mutation and zero
external effect, apart from standard successful-task `AgentBase` HP accounting,
so they are proposed as GREEN. They are new vocabulary entries, not changes to
existing tiers, and every entry is flagged in `core/config.py` and the package
report for independent review. Every action gets an exact Security district
route and manifest registration. Normal registry bootstrap makes the agents
available to the existing A2A bus; no separate inter-agent mechanism is added.

No new LLM call site is required. All checks are deterministic. Consequently,
RULE 1 has no new call site to satisfy.

## Verification

The focused test suite will verify complete and missing evidence behavior,
manifest importability, `AgentBase` inheritance, exact routes, exact permission
tiers, and the absence of filesystem-write or code-execution behavior in both
patch roles. The module's own `__main__` smoke check and the test file's own
`__main__` test runner will also be executed.
