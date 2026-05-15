<!-- VECTOR-INGESTED ASSET
  Source: C:\Users\Arghyadeep\Desktop\V.E.C.T.O.R\GitHub\sickn33_antigravity-awesome-skills\repo\skills\subagent-driven-development\code-quality-reviewer-prompt.md
  Personalized for VECTOR runtime — local Ollama, no paid APIs.
  Owner: Arghyadeep Deb
  Ingested: 2026-05-15T01:39:57+00:00
-->

# Code Quality Reviewer Prompt Template

Use this template when dispatching a code quality reviewer subagent.

**Purpose:** Verify implementation is well-built (clean, tested, maintainable)

**Only dispatch after spec compliance review passes.**

```
Task tool (superpowers:code-reviewer):
  Use template at requesting-code-review/code-reviewer.md

  WHAT_WAS_IMPLEMENTED: [from implementer's report]
  PLAN_OR_REQUIREMENTS: Task N from [plan-file]
  BASE_SHA: [commit before task]
  HEAD_SHA: [current commit]
  DESCRIPTION: [task summary]
```

**Code reviewer returns:** Strengths, Issues (Critical/Important/Minor), Assessment
