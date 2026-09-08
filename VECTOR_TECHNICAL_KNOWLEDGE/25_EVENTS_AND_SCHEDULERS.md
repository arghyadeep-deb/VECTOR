# Events and Schedulers

**Purpose:** APScheduler, event bus, scheduled tasks
**Level:** Subsystem Level (Level 2)

---

## Overview

VECTOR uses APScheduler for periodic tasks and an internal event bus for inter-component communication.

**Key Properties:**
- **APScheduler** — periodic task scheduling
- **Event bus** — pub/sub between components
- **2AM reflection** — daily consolidation
- **KIIT scraping** — daily schedule check
- **Hypothesis engine** — proactive insights every 4h

**Files:**
- `core/events/event_bus.py` (~150 lines)
- `core/scheduler/scheduler.py` (~200 lines)
- `core/loop/autonomous_loop.py` (schedule registration)

**Status:** ✅ IMPLEMENTED, production-reachable

---

## Event Bus

### Pub/Sub System

**File:** `core/events/event_bus.py`
**Status:** ✅ IMPLEMENTED

```python
import asyncio
from typing import Callable, Any

class EventBus:
    """Global event bus for inter-component communication."""
    
    def __init__(self):
        self._handlers = {}  # event_type → [handlers]
    
    def subscribe(self, event_type: str, handler: Callable):
        """Subscribe to event."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
    
    def unsubscribe(self, event_type: str, handler: Callable):
        """Unsubscribe from event."""
        if event_type in self._handlers:
            self._handlers[event_type].remove(handler)
    
    async def publish(self, event_type: str, data: Any = None):
        """Publish event to all subscribers."""
        if event_type not in self._handlers:
            return
        
        for handler in self._handlers[event_type]:
            try:
                await handler(data)
            except Exception as e:
                logger.error(f"[VECTOR][events] Handler error: {e}")

# Global instance
event_bus = EventBus()
```

### Event Types

```python
# Autonomous loop events
EVENT_OBSERVE_TICK = "observe.tick"
EVENT_THINK_TICK = "think.tick"
EVENT_ACT_TICK = "act.tick"
EVENT_REFLECT_TICK = "reflect.tick"

# Agent events
EVENT_AGENT_BIRTH = "agent.birth"
EVENT_AGENT_DEATH = "agent.death"
EVENT_AGENT_HP_CHANGE = "agent.hp_change"

# Goal events
EVENT_GOAL_ADDED = "goal.added"
EVENT_GOAL_COMPLETED = "goal.completed"
EVENT_GOAL_EXPIRED = "goal.expired"

# Memory events
EVENT_MEMORY_STORED = "memory.stored"
EVENT_MEMORY_CONSOLIDATED = "memory.consolidated"

# Communication events
EVENT_MESSAGE_RECEIVED = "message.received"
EVENT_MESSAGE_SENT = "message.sent"

# System events
EVENT_STARTUP = "system.startup"
EVENT_SHUTDOWN = "system.shutdown"
EVENT_ERROR = "system.error"
```

---

## Scheduler

### APScheduler Integration

**File:** `core/scheduler/scheduler.py`
**Status:** ✅ IMPLEMENTED

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

class VectorScheduler:
    """Manage all scheduled tasks."""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._register_tasks()
    
    def _register_tasks(self):
        """Register all scheduled tasks."""
        
        # 2AM daily reflection
        self.scheduler.add_job(
            self._daily_reflection,
            CronTrigger(hour=2, minute=0),
            id="daily_reflection"
        )
        
        # KIIT schedule scraping (daily 6AM)
        self.scheduler.add_job(
            self._kiit_scrape,
            CronTrigger(hour=6, minute=0),
            id="kiit_scrape"
        )
        
        # Hypothesis engine (every 4h)
        self.scheduler.add_job(
            self._hypothesis_engine,
            IntervalTrigger(hours=4),
            id="hypothesis_engine"
        )
        
        # Synthesis bridge (every 30min)
        self.scheduler.add_job(
            self._synthesis_bridge,
            IntervalTrigger(minutes=30),
            id="synthesis_bridge"
        )
        
        # OAuth token refresh (every 30min)
        self.scheduler.add_job(
            self._oauth_refresh,
            IntervalTrigger(minutes=30),
            id="oauth_refresh"
        )
        
        # Market scanner (nightly 1AM)
        self.scheduler.add_job(
            self._market_scan,
            CronTrigger(hour=1, minute=0),
            id="market_scan"
        )
        
        # Agent culling (weekly Sunday 3AM)
        self.scheduler.add_job(
            self._agent_cull,
            CronTrigger(day_of_week="sun", hour=3, minute=0),
            id="agent_cull"
        )
    
    async def _daily_reflection(self):
        """Run daily reflection."""
        from core.loop.autonomous_loop import autonomous_loop
        await autonomous_loop.reflect_loop()
    
    async def _kiit_scrape(self):
        """Scrape KIIT schedule."""
        from districts.time_calendar.kiit_scraper import KIITScraper
        scraper = KIITScraper()
        await scraper.scrape()
    
    async def _hypothesis_engine(self):
        """Run hypothesis engine."""
        from core.brain.hypothesis_engine import HypothesisEngine
        engine = HypothesisEngine()
        await engine.generate_insights()
    
    async def _synthesis_bridge(self):
        """Run synthesis bridge."""
        from core.brain.synthesis_bridge import SynthesisBridge
        bridge = SynthesisBridge()
        await bridge.detect_patterns()
    
    async def _oauth_refresh(self):
        """Refresh expiring OAuth tokens."""
        from core.engine.oauth.refresh_scheduler import refresh_expiring_tokens
        await refresh_expiring_tokens()
    
    async def _market_scan(self):
        """Run market scanner."""
        from districts.startups.market_scanner import MarketScanner
        scanner = MarketScanner()
        await scanner.scan()
    
    async def _agent_cull(self):
        """Cull bottom-performing agents."""
        from core.city.evolution_engine import EvolutionEngine
        engine = EvolutionEngine()
        engine.cull_bottom()
    
    def start(self):
        """Start scheduler."""
        self.scheduler.start()
    
    def stop(self):
        """Stop scheduler."""
        self.scheduler.shutdown()

# Global instance
scheduler = VectorScheduler()
```

---

## Autonomous Loop Integration

### Loop Schedule Registration

**File:** `core/loop/autonomous_loop.py`
**Status:** ✅ IMPLEMENTED

```python
class AutonomousLoop:
    """Main autonomous loop."""
    
    async def run_forever(self):
        """Run all coroutines."""
        # Start scheduler
        scheduler.start()
        
        # Run coroutines
        await asyncio.gather(
            self.observe_loop(),
            self.think_loop(),
            self.act_loop(),
            self._scheduled_reflect()
        )
    
    async def _scheduled_reflect(self):
        """Wait for 2AM and run reflect."""
        while True:
            now = datetime.now()
            
            # Calculate time until 2AM
            target = now.replace(hour=2, minute=0, second=0, microsecond=0)
            if now.hour >= 2:
                target += timedelta(days=1)
            
            wait_seconds = (target - now).total_seconds()
            await asyncio.sleep(wait_seconds)
            
            # Run reflection
            await self.reflect_loop()
```

---

## Performance Characteristics

| Operation | Duration | Bottleneck |
|-----------|----------|------------|
| Event publish | <1ms | Memory access |
| Event handler | 1-500ms | Handler logic |
| Scheduler tick | <1ms | APScheduler |
| Job execution | varies | Task-specific |

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `05_AUTONOMOUS_LOOP.md` — Autonomous loop
- `14_REFLECTION.md` — Reflection system

---

**Last Updated:** 2026-08-12
**Status:** ✅ COMPLETE
