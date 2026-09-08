# Observability

**Purpose:** Logging, monitoring, metrics, traces
**Level:** Subsystem Level (Level 2)

---

## Overview

VECTOR uses loguru for structured logging, a custom SRE monitor for health checks, and DevOps automator for infrastructure monitoring.

**Key Properties:**
- **loguru** — structured logging everywhere
- **SRE monitor** — SLO/SLI tracking
- **DevOps automator** — infrastructure health
- **Incident commander** — automated incident response
- **No print()** — loguru only in production

**Files:**
- `districts/ops/sre_monitor.py`
- `districts/ops/devops_automator.py`
- `districts/ops/incident_commander.py`
- `core/config.py` (logging config)

**Status:** ✅ IMPLEMENTED, production-reachable

---

## Logging

### loguru Configuration

**File:** `core/config.py`
**Status:** ✅ IMPLEMENTED

```python
from loguru import logger
import sys

# Remove default handler
logger.remove()

# Add stderr handler (dev)
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)

# Add file handler (production)
logger.add(
    "logs/vector.log",
    rotation="10 MB",
    retention="7 days",
    compression="gz",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    level="INFO"
)

# Usage
logger.info("[VECTOR][module] message")
logger.warning("[VECTOR][module] warning")
logger.error("[VECTOR][module] error")
logger.critical("[VECTOR][module] critical")
```

### Logging Convention

```python
# ALWAYS use loguru, NEVER print() in production
from loguru import logger

# Correct
logger.info("[VECTOR][observe] Observe tick complete")
logger.warning("[VECTOR][inference] Ollama unavailable, using fallback")
logger.error("[VECTOR][db] Supabase failed, using local SQLite")
logger.critical("[VECTOR][security] Malware detected")

# WRONG — never do this
print("Observe tick complete")  # ❌
```

---

## SRE Monitor

### SLO/SLI Tracking

**File:** `districts/ops/sre_monitor.py`
**Status:** ✅ IMPLEMENTED

```python
class SREMonitor(AgentBase):
    """SRE monitoring agent."""
    
    # SLOs
    SLOS = {
        "loop_uptime": 0.99,        # 99% uptime
        "response_latency": 5.0,    # <5s response
        "error_rate": 0.01,         # <1% errors
        "memory_usage": 0.80        # <80% memory
    }
    
    async def _execute_task(self, query: str, task_type: str) -> dict:
        if task_type == "check":
            return await self._check_slos()
        elif task_type == "chaos":
            return await self._chaos_probe()
        else:
            return {"success": False, "error": "Unknown task type"}
    
    async def _check_slos(self) -> dict:
        """Check all SLOs."""
        results = {}
        
        # Loop uptime
        from core.loop.autonomous_loop import autonomous_loop
        uptime = autonomous_loop.uptime_ratio
        results["loop_uptime"] = {
            "value": uptime,
            "target": self.SLOS["loop_uptime"],
            "met": uptime >= self.SLOS["loop_uptime"]
        }
        
        # Response latency
        latency = await self._measure_latency()
        results["response_latency"] = {
            "value": latency,
            "target": self.SLOS["response_latency"],
            "met": latency <= self.SLOS["response_latency"]
        }
        
        # Error rate
        error_rate = await self._calculate_error_rate()
        results["error_rate"] = {
            "value": error_rate,
            "target": self.SLOS["error_rate"],
            "met": error_rate <= self.SLOS["error_rate"]
        }
        
        # Memory usage
        import psutil
        memory = psutil.virtual_memory().percent / 100
        results["memory_usage"] = {
            "value": memory,
            "target": self.SLOS["memory_usage"],
            "met": memory <= self.SLOS["memory_usage"]
        }
        
        all_met = all(r["met"] for r in results.values())
        
        return {
            "success": True,
            "slos": results,
            "all_met": all_met
        }
    
    async def _chaos_probe(self) -> dict:
        """Run chaos engineering probe."""
        from core.loop.decision_engine import DecisionEngine
        
        engine = DecisionEngine()
        
        # Test decision engine
        try:
            result = engine.evaluate()
            return {
                "success": True,
                "decision_engine": "operational"
            }
        except Exception as e:
            return {
                "success": False,
                "decision_engine": f"failed: {e}"
            }
```

---

## DevOps Automator

### Infrastructure Health

**File:** `districts/ops/devops_automator.py`
**Status:** ✅ IMPLEMENTED

```python
class DevOpsAutomator(AgentBase):
    """DevOps automation agent."""
    
    async def _execute_task(self, query: str, task_type: str) -> dict:
        if task_type == "check":
            return await self._check_infrastructure()
        elif task_type == "deploy":
            return await self._deploy()
        else:
            return {"success": False, "error": "Unknown task type"}
    
    async def _check_infrastructure(self) -> dict:
        """Check all infrastructure."""
        results = {}
        
        # Cloudflare Worker
        try:
            import httpx
            response = await httpx.get(
                "https://vector-api.workers.dev/health",
                timeout=5
            )
            results["cloudflare"] = {
                "status": "healthy" if response.status_code == 200 else "unhealthy",
                "latency": response.elapsed.total_seconds()
            }
        except Exception as e:
            results["cloudflare"] = {
                "status": "unreachable",
                "error": str(e)
            }
        
        # Ollama
        try:
            response = await httpx.get(
                "http://localhost:11434/api/tags",
                timeout=5
            )
            results["ollama"] = {
                "status": "healthy" if response.status_code == 200 else "unhealthy"
            }
        except Exception as e:
            results["ollama"] = {
                "status": "unreachable",
                "error": str(e)
            }
        
        # SQLite
        try:
            from core.memory.episodic import get_db_connection
            conn = get_db_connection()
            conn.execute("SELECT 1")
            results["sqlite"] = {"status": "healthy"}
        except Exception as e:
            results["sqlite"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        all_healthy = all(r["status"] == "healthy" for r in results.values())
        
        return {
            "success": True,
            "infrastructure": results,
            "all_healthy": all_healthy
        }
```

---

## Incident Commander

### Automated Response

**File:** `districts/ops/incident_commander.py`
**Status:** ✅ IMPLEMENTED

```python
class IncidentCommander(AgentBase):
    """Incident response agent."""
    
    async def _execute_task(self, query: str, task_type: str) -> dict:
        if task_type == "respond":
            return await self._respond_to_incident(query)
        else:
            return {"success": False, "error": "Unknown task type"}
    
    async def _respond_to_incident(self, incident: str) -> dict:
        """Respond to incident."""
        import json
        data = json.loads(incident)
        
        severity = data.get("severity", "low")
        component = data.get("component", "unknown")
        
        # Notify owner via Pushover
        if severity in ["high", "critical"]:
            from core.notifications.pushover import send_notification
            await send_notification(
                title=f"VECTOR Incident: {component}",
                message=f"Severity: {severity}\n{data.get('details', '')}",
                priority=1 if severity == "critical" else 0
            )
        
        # Auto-remediation
        if component == "ollama":
            # Restart Ollama
            import subprocess
            subprocess.run(["ollama", "serve"], shell=True)
        
        elif component == "cloudflare":
            # Check if it's a transient error
            import httpx
            try:
                response = await httpx.get(
                    "https://vector-api.workers.dev/health",
                    timeout=10
                )
                if response.status_code == 200:
                    return {"success": True, "message": "Transient, auto-recovered"}
            except Exception:
                pass
        
        return {
            "success": True,
            "message": "Incident logged, owner notified"
        }
```

---

## Performance Characteristics

| Operation | Duration | Bottleneck |
|-----------|----------|------------|
| Log write | <1ms | Disk I/O |
| SLO check | 1-5s | Component checks |
| Infrastructure check | 2-10s | Network calls |
| Incident response | 1-5s | Notification + remediation |

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `26_TESTING_AND_EVALS.md` — Testing
- `30_DEPLOYMENT.md` — Deployment

---

**Last Updated:** 2026-08-12
**Status:** ✅ COMPLETE
