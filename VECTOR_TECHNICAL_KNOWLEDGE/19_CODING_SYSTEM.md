# Coding System

**Purpose:** Coding autonomy, git integration  
**Level:** Subsystem Level (Level 2)

---

## Overview

VECTOR's coding district provides autonomous code generation, review, testing, and git operations.

**Key Properties:**
- **Code generation** — LLM-powered coding
- **Code review** — AST-based review
- **Git integration** — commit, push, pull
- **Permission-gated** — RED tier for pushes

**Files:** `districts/coding/`  
**Status:** ✅ IMPLEMENTED, production-reachable

---

## Coding Agents

### GitBot

**File:** `districts/coding/git_bot.py`  
**Status:** ✅ IMPLEMENTED

```python
class GitBot(AgentBase):
    """Git operations agent."""
    
    async def _execute_task(self, query: str, task_type: str) -> dict:
        if task_type == "commit":
            return await self._commit(query)
        elif task_type == "push":
            return await self._push(query)
        elif task_type == "pull":
            return await self._pull(query)
        else:
            return {"success": False, "error": "Unknown task type"}
    
    async def _commit(self, message: str) -> dict:
        """Git commit."""
        result = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True,
            text=True
        )
        
        return {
            "success": result.returncode == 0,
            "output": result.stdout
        }
    
    async def _push(self, branch: str = "main") -> dict:
        """Git push (RED tier)."""
        # Permission check happens in act_loop
        result = subprocess.run(
            ["git", "push", "origin", branch],
            capture_output=True,
            text=True
        )
        
        return {
            "success": result.returncode == 0,
            "output": result.stdout
        }
```

### CodeReviewer

**File:** `districts/coding/code_reviewer.py`  
**Status:** ✅ IMPLEMENTED

```python
class CodeReviewer(AgentBase):
    """Code review agent."""
    
    async def _execute_task(self, query: str, task_type: str) -> dict:
        if task_type == "review":
            return await self._review_code(query)
        else:
            return {"success": False, "error": "Unknown task type"}
    
    async def _review_code(self, file_path: str) -> dict:
        """Review code."""
        # Read file
        with open(file_path, 'r') as f:
            code = f.read()
        
        # Use LLM to review
        from core.inference.provider_client import chat
        
        prompt = f"""Review this code for bugs, style issues, and improvements:

{code}

Return JSON: {{"issues": [...], "suggestions": [...]}}
"""
        
        response = await chat([{"role": "user", "content": prompt}])
        
        try:
            review = json.loads(response.content)
            return {
                "success": True,
                "review": review
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
```

---

## Ponytail Guard

### Minimal-Code Enforcement

**File:** `core/inference/ponytail_guard.py`  
**Status:** ✅ IMPLEMENTED

```python
def inject_into_llm_call(prompt: str) -> str:
    """Inject ponytail decision ladder into coding LLM calls."""
    
    from ponytail.skills.ponytail import decision_ladder
    
    ladder = decision_ladder(intensity="full")
    
    return f"{ladder}\n\n{prompt}"
```

---

## Performance Characteristics

| Operation | Duration | Bottleneck |
|-----------|----------|------------|
| Code generation | 5-30s | LLM call |
| Code review | 3-15s | LLM call |
| Git commit | 100-500ms | Git |
| Git push | 1-5s | Network |

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `11_VECTOR_CITY.md` — Districts

---

**Last Updated:** 2026-08-12  
**Status:** ✅ COMPLETE
